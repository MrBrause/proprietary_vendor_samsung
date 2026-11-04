#!/usr/bin/env python3
# Rename the RIL multiclient socket so it matches what the ported IMS engine dials.
#
#   libsec-ril.so  binds  "VND_Multiclient" / "VND_Multiclient2"   (newer firmware)
#   libsec-ims.so  dials  "Multiclient"     / "Multiclient2"       (the engine you ported)
#
# They came from different firmware versions, so on this build they never meet.
# This rewrites the RIL's hardcoded names to the engine's names IN PLACE
# (same byte length, null-terminated early), so rild binds @Multiclient(2) like
# stock and the engine connects DIRECTLY with its own credentials.
#
# Usage:  python3 fix_ril_multiclient_name.py /path/to/libsec-ril.so
# Keeps a .orig backup. Re-runnable (idempotent). Verify afterwards:
#   grep -c 'VND_Multiclient' libsec-ril.so   -> should be 0
#   (on device) netstat -lxp | grep -i multiclient  -> @Multiclient, owner rild

import sys, os, shutil

def patch(buf, old, new):
    assert len(new) <= len(old), "replacement must not be longer"
    padded = new + b"\x00" * (len(old) - len(new))
    count, i = 0, 0
    while True:
        j = buf.find(old, i)
        if j < 0:
            break
        buf[j:j + len(old)] = padded
        count += 1
        i = j + len(old)
    return count

def main():
    if len(sys.argv) != 2:
        print("usage: fix_ril_multiclient_name.py <libsec-ril.so>")
        sys.exit(2)
    path = sys.argv[1]
    if not os.path.exists(path + ".orig"):
        shutil.copy2(path, path + ".orig")
        print("backup ->", path + ".orig")
    buf = bytearray(open(path, "rb").read())

    # Patch the "2" variant FIRST so the shorter match can't clobber it.
    c2 = patch(buf, b"VND_Multiclient2", b"Multiclient2")
    c1 = patch(buf, b"VND_Multiclient",  b"Multiclient")
    print("patched VND_Multiclient2:", c2, " VND_Multiclient:", c1)

    if c1 == 0 and c2 == 0:
        # Maybe only the base literal exists and "2" is appended at runtime;
        # in that case c1>0 above already handled it. If BOTH are zero, nothing
        # matched - the blob may already be patched or use a different name.
        print("WARNING: no 'VND_Multiclient' found - nothing changed.")
    open(path, "wb").write(buf)
    print("wrote", path)

if __name__ == "__main__":
    main()
