#!/usr/bin/env python3
"""
fix_multiclientd_audiowl.py — let Samsung's multiclientd accept the LineageOS audio HAL.

WHY: multiclientd authorizes each OEM client by reading /proc/<pid>/cmdline (argv[0]) and
strcmp-ing it against a hard-coded 26-entry whitelist; a match also checks the peer uid.
com.sec.imsservice (the IMS engine, uid system) is whitelisted -> VoLTE signalling works.
The herolte audio HAL (/vendor/bin/hw/android.hardware.audio.service.universal8890, uid
audioserver) is NOT in the list, so SetCallAudioPath / SetTwoMicControl / SetCallVolume are
rejected ("can't connect with oem client" -> "SetCallAudioPath: Not connected") and the modem's
uplink audio path / ACDB calibration / 2-mic are never programmed -> far-party "fizzle".

HOW: the audio HAL's argv[0] is 59 bytes and there is no 60-byte read-only cave to hold it, so
we RECLAIM table space. The whitelist's last 3 entries are India-only OEM clients
(com.expway.embmsserver, com.jio.myjio, com.jio.emiddleware) that never run on herolte. We:
  1) shrink the scan loop bound  cmp x23,#0x270 (26 entries) -> #0x228 (23 entries),
  2) NONE-out the 3 R_AARCH64_RELATIVE relocs for those entries' string pointers (so the loader
     won't overwrite the reclaimed bytes),
  3) write the audio-HAL argv[0] string into the freed 72-byte tail of the .data table,
  4) repoint the DONOR entry (default idx-14 samsung-positioning manager, also absent on herolte)
     to that string and set its uid field to AID_AUDIOSERVER (1041).
Everything is length-preserving: section sizes/offsets and all other relocations are untouched.

Usage: fix_multiclientd_audiowl.py <multiclientd> [-o out] [--cmd ARGV0] [--uid N] [--donor STR]
"""
import struct, sys, argparse

R_RELATIVE   = 1027
R_NONE       = 0
TABLE_VA     = 0xaad0
N_OLD        = 26
N_NEW        = 23          # drop the 3 trailing India-only entries
ENTRY        = 0x18
LOOP_CMP_VA  = 0x6cc4      # cmp x23, #0x270
CMP_OLD_WORD = 0xf109c2ff  # subs xzr, x23, #0x270
CMP_NEW_WORD = 0xf108a2ff  # subs xzr, x23, #0x228
DEF_DONOR = "com.samsung.android.samsungpositioning.manager"
DEF_CMD   = "/vendor/bin/hw/android.hardware.audio.service.universal8890"
DEF_UID   = 1041           # AID_AUDIOSERVER

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin"); ap.add_argument("-o","--out")
    ap.add_argument("--cmd",   default=DEF_CMD)
    ap.add_argument("--uid",   type=int, default=DEF_UID)
    ap.add_argument("--donor", default=DEF_DONOR)
    a = ap.parse_args()
    d = bytearray(open(a.bin,"rb").read())

    e_shoff = struct.unpack_from("<Q", d, 0x28)[0]
    she = struct.unpack_from("<H", d, 0x3a)[0]; shn = struct.unpack_from("<H", d, 0x3c)[0]
    shstrndx = struct.unpack_from("<H", d, 0x3e)[0]
    secs = []
    for i in range(shn):
        b = e_shoff + i*she
        nm,typ,fl,addr,off,size = struct.unpack_from("<IIQQQQ", d, b)
        secs.append(dict(nm=nm,typ=typ,addr=addr,off=off,size=size))
    sho = secs[shstrndx]["off"]
    for s in secs:
        e = d.index(b"\0", sho+s["nm"]); s["name"] = d[sho+s["nm"]:e].decode()
    def v2o(va):
        for s in secs:
            if s["addr"] and s["addr"] <= va < s["addr"]+s["size"]:
                return s["off"]+(va-s["addr"])
        raise ValueError(hex(va))
    def rdstr(va):
        o=v2o(va); return d[o:d.index(b"\0",o)].decode("latin1")

    # RELA table: r_offset -> file position of the 24-byte entry
    rela_pos = {}
    for s in secs:
        if s["typ"] == 4:
            for p in range(s["off"], s["off"]+s["size"], 24):
                r_off = struct.unpack_from("<Q", d, p)[0]; rela_pos[r_off] = p
    def addend_of(slot_va): return struct.unpack_from("<q", d, rela_pos[slot_va]+16)[0]

    # locate donor entry by its string
    donor = None
    for k in range(N_OLD):
        slot = TABLE_VA + k*ENTRY + 8
        if slot in rela_pos and (struct.unpack_from("<Q",d,rela_pos[slot]+8)[0] & 0xffffffff)==R_RELATIVE:
            if rdstr(addend_of(slot)) == a.donor: donor = k; break
    if donor is None: sys.exit("donor %r not found" % a.donor)

    # 1) shrink loop bound
    co = v2o(LOOP_CMP_VA)
    w = struct.unpack_from("<I", d, co)[0]
    if w != CMP_OLD_WORD:
        sys.exit("loop-bound insn mismatch at %#x: got %#x expected %#x" % (LOOP_CMP_VA,w,CMP_OLD_WORD))
    struct.pack_into("<I", d, co, CMP_NEW_WORD)

    # reclaimed region = the dropped entries' table tail
    freed_va = TABLE_VA + N_NEW*ENTRY               # 0xacf8
    region_end = TABLE_VA + N_OLD*ENTRY             # 0xad40 (= .data end)
    need = len(a.cmd) + 1
    avail = region_end - freed_va
    if need > avail: sys.exit("string %d > reclaimed %d bytes" % (need, avail))

    # scratch slot for the redirected relocs: 8-aligned, past the string, inside the region
    scratch = (freed_va + need + 7) & ~7
    if scratch + 8 > region_end:
        sys.exit("no room for reloc scratch (need=%d)" % need)

    # 2) the 3 dropped entries' string-pointer relocs point INTO the reclaimed region.
    #    They sit inside DT_RELACOUNT, so a type-blind loader would still apply them -> keep them
    #    RELATIVE but REDIRECT r_offset to the harmless scratch slot (addend 0). Whatever the loader
    #    writes lands on unused padding, never on the string.
    for k in range(N_NEW, N_OLD):
        slot = TABLE_VA + k*ENTRY + 8
        p = rela_pos[slot]
        struct.pack_into("<Q", d, p,    scratch)   # r_offset -> scratch
        struct.pack_into("<q", d, p+16, 0)         # addend 0 (keep type RELATIVE)

    # 3) write the string into the reclaimed tail (does not reach the scratch slot)
    fo = v2o(freed_va)
    d[fo:fo+(scratch-freed_va)] = (a.cmd.encode() + b"\0").ljust(scratch-freed_va, b"\0")

    # 4) repoint donor + set uid
    dslot = TABLE_VA + donor*ENTRY + 8
    struct.pack_into("<q", d, rela_pos[dslot]+16, freed_va)     # reloc addend -> string
    so = v2o(dslot)
    if struct.unpack_from("<Q", d, so)[0] != 0:
        struct.pack_into("<Q", d, so, freed_va)
    struct.pack_into("<i", d, v2o(TABLE_VA + donor*ENTRY), a.uid)  # uid field

    out = a.out or (a.bin + ".patched")
    open(out,"wb").write(d)
    print("donor entry #%d -> uid=%d cmdline=%r (string stored @%#x)" % (donor, a.uid, a.cmd, freed_va))
    print("loop 26->23 entries; dropped India-only OEM clients; wrote %s" % out)

if __name__ == "__main__":
    main()
