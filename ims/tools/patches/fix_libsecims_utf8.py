#!/usr/bin/env python3
# Repoint libsec-ims.so's UNUSED DT_NEEDED "libaudioclient.so" to our shim
# "libutf8_ims.so", which exports the one symbol A14 is missing: utf8_length.
# Length-preserving in-place .dynstr edit (new name <= old, NUL-padded).
# libsec-ims imports ZERO symbols from libaudioclient, so dropping it is safe.
import sys, os, shutil
OLD = b"libaudioclient.so\x00"
NEW = b"libutf8_ims.so\x00"
def main():
    p = sys.argv[1] if len(sys.argv) > 1 else "libsec-ims.so"
    assert len(NEW) <= len(OLD), "shim name too long"
    repl = NEW + b"\x00" * (len(OLD) - len(NEW))
    if not os.path.exists(p + ".orig"):
        shutil.copy2(p, p + ".orig"); print("backup ->", p + ".orig")
    buf = open(p, "rb").read()
    n = buf.count(OLD)
    print("occurrences of libaudioclient.so:", n)
    if n == 0:
        print("nothing to patch (already patched?)"); return
    assert n == 1, "unexpected: expected exactly 1"
    buf = buf.replace(OLD, repl)
    open(p, "wb").write(buf)
    print("patched", p, "-> DT_NEEDED now libutf8_ims.so")
if __name__ == "__main__": main()
