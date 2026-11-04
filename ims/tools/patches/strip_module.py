#!/usr/bin/env python3
# strip_module.py — remove one or more ServiceModule constructions from
# ServiceModuleManager.createServiceModules(). Each module is matched by its class path.
#
#   cd ~/ims_pull/imsservice
#   python3 strip_module.py com/sec/internal/ims/gls/GlsModule
#   python3 strip_module.py com/sec/internal/ims/gls/GlsModule com/sec/internal/ims/euc/EucModule
#
# For each module it removes the block:  new-instance vX, L<module>;  ...  List.add(vX)
# and scrubs .local/.end local/.restart local for vX. It REFUSES (warns, skips) if vX is
# referenced anywhere else in the method after the add — that means the module also feeds a
# binder/other wiring and needs a hand edit, so we don't silently break it.
#
import os, re, sys, glob

if len(sys.argv) < 2:
    sys.exit("usage: python3 strip_module.py com/sec/internal/ims/<pkg>/<Module> [more...]")
modules = [m.strip().lstrip("L").rstrip(";") for m in sys.argv[1:]]

p = None
for d in sorted(glob.glob("smali*")):
    c = os.path.join(d, "com/sec/internal/ims/imsservice/ServiceModuleManager.smali")
    if os.path.isfile(c):
        p = c; break
if not p:
    sys.exit("!! ServiceModuleManager.smali not found")

with open(p, encoding="utf-8") as fh:
    lines = fh.readlines()

def method_bounds(lines):
    s = e = None
    for i, l in enumerate(lines):
        if s is None and re.match(r'\s*\.method\s+public\s+createServiceModules\(', l):
            s = i
        elif s is not None and l.strip() == ".end method":
            e = i; break
    return s, e

for mod in modules:
    s, e = method_bounds(lines)
    if s is None:
        sys.exit("!! createServiceModules not found")
    ni = reg = None
    for i in range(s, e + 1):
        m = re.match(r'\s*new-instance\s+(v\d+),\s+L' + re.escape(mod) + r';\s*$', lines[i])
        if m:
            ni, reg = i, m.group(1); break
    if ni is None:
        print("skip %s: no new-instance in createServiceModules (already removed?)" % mod)
        continue
    addpat = re.compile(r'\s*invoke-interface\s+\{v\d+,\s*' + reg + r'\},\s*Ljava/util/List;->add\(Ljava/lang/Object;\)Z\s*$')
    add = None
    for i in range(ni + 1, e + 1):
        if addpat.match(lines[i]):
            add = i; break
    if add is None:
        print("!! skip %s: List.add(%s) not found — layout differs, needs hand edit" % (mod, reg))
        continue
    # safety: is reg used again AFTER the add, within the method?
    tail_uses = [i for i in range(add + 1, e + 1)
                 if re.search(r'\b' + reg + r'\b', lines[i])
                 and not re.match(r'\s*\.(?:end )?local\b', lines[i])]
    if tail_uses:
        print("!! skip %s: register %s is used again after the add (feeds a binder/other wiring)." % (mod, reg))
        for i in tail_uses[:6]:
            print("     L%d: %s" % (i + 1, lines[i].strip()))
        print("   -> needs a hand edit; tell me and I'll handle this one specially.")
        continue
    block = lines[ni:add + 1]
    lines = lines[:ni] + lines[add + 1:]
    dbg = re.compile(r'\s*\.(?:local|end local|restart local)\s+' + reg + r'\b')
    lines = [l for l in lines if not dbg.match(l)]
    print("removed %s  (reg %s, %d lines)" % (mod, reg, len(block)))

with open(p, "w", encoding="utf-8") as fh:
    fh.writelines(lines)

# report any leftover references to the removed modules anywhere in this file
print("--- leftover references in ServiceModuleManager.smali ---")
for mod in modules:
    n = sum(1 for l in lines if ("L" + mod + ";") in l)
    print("  %s : %d" % (mod, n))
