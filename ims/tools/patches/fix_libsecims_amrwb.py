#!/usr/bin/env python3
"""
fix_libsecims_amrwb.py — unlock AMR-WB (HD voice) in the Samsung IMS native lib.

SdpCreator::InitCodecs() builds the offered audio-codec vector. For each codec it
does: GetConfig<codec>() ; cmp wA,wB ; b.le <skip> ; <mov w1,#enum> ; mov w2,#-1 ;
mov x0,x19 ; bl SdpCreator::CodecCreate(AudioCodecName,EvsPresetType). The b.le skips
creating that codec. On this A21s engine the guard passes for AMR (enum 2) but SKIPS
AMR-WB (enum 4) and AMRBE-WB (enum 5), so wideband is never put in the SDP offer.

This NOPs the b.le that guards the AMR-WB (enum 4) and AMRBE-WB (enum 5) CodecCreate
calls, so they are created like AMR. We locate them by pattern (not fixed offsets) so
it works across rebuilds:
    <enum: 321e03e1 (orr w1,wzr,#4)  OR  528000a1 (mov w1,#5)>
    12800002 (mov w2,#-1)
    aa1303e0 (mov x0,x19)
then backtrack a few instructions to the nearest preceding b.le (0x54.....d) and NOP it.
AMR (enum 2 = 321f03e1) is NOT matched, so its guard is left intact.

NOTE: AMR-WB also needs its payload/mode params present in the engine's media config.
Those come from /system/csc/imsupdate.json (imsprofile_update: amrwb_mode, amrwboa_payload,
amrwbbe_payload). Both this patch AND that file are required for HD voice.

Usage: fix_libsecims_amrwb.py <libsec-ims.so>  [-o out.so]   (in-place if no -o)
"""
import sys, struct, argparse

NOP   = 0xd503201f
MOVW2 = 0x12800002   # mov w2, #-1
MOVX0 = 0xaa1303e0   # mov x0, x19
ENUMS = {0x321e03e1: "AMR-WB (enum 4)", 0x528000a1: "AMRBE-WB (enum 5)"}

def text_section(data):
    # minimal ELF64 section-header parse to find .text (addr, file off, size)
    e_shoff = struct.unpack_from("<Q", data, 0x28)[0]
    e_shentsize = struct.unpack_from("<H", data, 0x3a)[0]
    e_shnum = struct.unpack_from("<H", data, 0x3c)[0]
    e_shstrndx = struct.unpack_from("<H", data, 0x3e)[0]
    def sh(i):
        b = e_shoff + i*e_shentsize
        name, typ, flags, addr, off, size = struct.unpack_from("<IIQQQQ", data, b)
        return dict(name=name, addr=addr, off=off, size=size)
    strtab = sh(e_shstrndx)
    for i in range(e_shnum):
        s = sh(i)
        nm = data[strtab["off"]+s["name"]:data.index(b"\0", strtab["off"]+s["name"])]
        if nm == b".text":
            return s
    raise RuntimeError(".text not found")

def is_ble(word):          # b.le : 0x54 iiiiiii..0 1101 (cond=0xd)
    return (word & 0xff00001f) == 0x5400000d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lib"); ap.add_argument("-o", "--out")
    a = ap.parse_args()
    data = bytearray(open(a.lib, "rb").read())
    t = text_section(data)
    base, off, size = t["addr"], t["off"], t["size"]
    words = {}  # file offset -> word, for the .text range
    patched = []
    i = off
    end = off + size
    while i + 12 <= end:
        w0 = struct.unpack_from("<I", data, i)[0]
        if w0 in ENUMS:
            w1 = struct.unpack_from("<I", data, i+4)[0]
            w2 = struct.unpack_from("<I", data, i+8)[0]
            if w1 == MOVW2 and w2 == MOVX0:
                # backtrack up to 8 instrs for the guarding b.le
                for k in range(1, 9):
                    j = i - 4*k
                    if j < off: break
                    wj = struct.unpack_from("<I", data, j)[0]
                    if is_ble(wj):
                        struct.pack_into("<I", data, j, NOP)
                        patched.append((base + (j-off), ENUMS[w0]))
                        break
        i += 4
    if not patched:
        print("ERROR: no AMR-WB/AMRBE-WB guards found — wrong/changed binary?", file=sys.stderr)
        sys.exit(1)
    for va, name in patched:
        print(f"NOP b.le guard @ 0x{va:x}  ->  always create {name}")
    outp = a.out or a.lib
    open(outp, "wb").write(data)
    print(f"wrote {outp} ({len(patched)} guard(s) patched)")

if __name__ == "__main__":
    main()
