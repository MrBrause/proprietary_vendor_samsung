#!/usr/bin/env python3
# fix_arraycopy.py — rewrite calls to the hidden/non-public typed System.arraycopy
# overloads (arraycopy([B..), arraycopy([C..), arraycopy([Ljava/lang/Object;..), etc.)
# to the public generic arraycopy(Object,int,Object,int,int). On A14 the typed overloads
# are inaccessible -> IllegalAccessError; the generic one is public, identical behavior
# (ART intrinsifies both), and the 5-register invoke layout is unchanged.
#
#   cd ~/ims_pull/imsservice   &&   python3 fix_arraycopy.py .
#
import re, os, sys, glob
root = sys.argv[1] if len(sys.argv) > 1 else "."
dirs = [d for d in glob.glob(os.path.join(root, "smali*")) if os.path.isdir(d)]
if not dirs:
    # maybe we were pointed straight at a smali dir
    if os.path.isdir(os.path.join(root, "com")):
        dirs = [root]
    else:
        sys.exit("!! no smali*/ dirs under " + root)

GEN = "Ljava/lang/System;->arraycopy(Ljava/lang/Object;ILjava/lang/Object;II)V"
# typed 5-arg overloads: first arg begins with '[' ; generic begins with 'L' so it's excluded
pat = re.compile(r'Ljava/lang/System;->arraycopy\(\[[^)]*\)V')

nfiles = nsites = 0
for d in dirs:
    for dp, _, fns in os.walk(d):
        for fn in fns:
            if not fn.endswith(".smali"): continue
            p = os.path.join(dp, fn)
            s = open(p, encoding="utf-8", errors="replace").read()
            n = len(pat.findall(s))
            if n:
                open(p, "w", encoding="utf-8").write(pat.sub(GEN, s))
                nfiles += 1; nsites += n

print("fix_arraycopy: rewrote %d typed System.arraycopy call(s) in %d file(s)" % (nsites, nfiles))
# show which files (so we know StackIF was among them)
if nsites:
    for d in dirs:
        for dp, _, fns in os.walk(d):
            for fn in fns:
                if fn.endswith(".smali") and "arraycopy(Ljava/lang/Object;ILjava/lang/Object;II)V" in open(os.path.join(dp,fn),encoding="utf-8",errors="replace").read():
                    pass
print("done")
