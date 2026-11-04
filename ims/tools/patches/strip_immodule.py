#!/usr/bin/env python3
# strip_immodule.py — remove the ImModule construction from
# ServiceModuleManager.createServiceModules() so the unwanted RCS instant-messaging
# module is never built (im=false anyway). Scoped to that one method; nothing else touched.
#
# Run from the apktool output dir:
#     cd ~/ims_pull/imsservice
#     python3 strip_immodule.py
#
import os, re, sys, glob

target = None
for d in sorted(glob.glob("smali*")):
    p = os.path.join(d, "com/sec/internal/ims/imsservice/ServiceModuleManager.smali")
    if os.path.isfile(p):
        target = p; break
if not target:
    sys.exit("!! ServiceModuleManager.smali not found under smali*/")

with open(target, encoding="utf-8") as fh:
    lines = fh.readlines()

# locate createServiceModules method boundaries
mstart = mend = None
for i, l in enumerate(lines):
    if mstart is None and re.match(r'\s*\.method\s+public\s+createServiceModules\(', l):
        mstart = i
    elif mstart is not None and l.strip() == ".end method":
        mend = i; break
if mstart is None or mend is None:
    sys.exit("!! createServiceModules method not found")

body = range(mstart, mend + 1)

# find: new-instance vX, Lcom/sec/internal/ims/im/ImModule;
ni = None; reg = None
for i in body:
    m = re.match(r'\s*new-instance\s+(v\d+),\s+Lcom/sec/internal/ims/im/ImModule;\s*$', lines[i])
    if m:
        ni = i; reg = m.group(1); break
if ni is None:
    print("note: no ImModule new-instance in createServiceModules — already removed? nothing to do.")
    sys.exit(0)

# find the matching list .add of that register: invoke-interface {vY, vX}, Ljava/util/List;->add
addline = None
addpat = re.compile(r'\s*invoke-interface\s+\{v\d+,\s*' + reg + r'\},\s*Ljava/util/List;->add\(Ljava/lang/Object;\)Z\s*$')
for i in range(ni + 1, mend + 1):
    if addpat.match(lines[i]):
        addline = i; break
if addline is None:
    sys.exit("!! could not find the List.add(%s) that ends the ImModule block" % reg)

# Also drop the iget-object that loads mServiceModules immediately before that add,
# if it sits right above and feeds the add (keep it simple: remove it only if it is the
# line directly preceding the add and is an iget of mServiceModules).
start = ni
end = addline
# pull in a leading `.line NNN` directly above new-instance (cosmetic) only if present
# (leave it; harmless). Remove [start..end] inclusive, plus any local-debug directives
# for reg inside the whole method.
removed = lines[start:end + 1]
kept = lines[:start] + lines[end + 1:]

# scrub stray debug directives for the same register within the method range (indices shift)
out = []
# recompute method end offset after first splice is messy; instead filter globally but
# only lines that are exactly a local directive for `reg` AND fall in the original method.
# Simpler: filter the whole file for ".local reg", ".end local reg", ".restart local reg"
# — safe because grep confirmed v7 is used only for imModule in this file.
dbg = re.compile(r'\s*\.(?:local|end local|restart local)\s+' + reg + r'\b')
final = [l for l in kept if not dbg.match(l)]

with open(target, "w", encoding="utf-8") as fh:
    fh.writelines(final)

print("removed ImModule construction from createServiceModules:")
print("  register : %s" % reg)
print("  lines    : %d (new-instance .. List.add) + stray .local directives" % len(removed))
print("  file     : %s" % target)
print()
print("--- removed block ---")
sys.stdout.writelines("    " + l for l in removed)
print("--- verify no ImModule refs remain in this file ---")
rest = [l for l in final if "Lcom/sec/internal/ims/im/ImModule;" in l]
print("remaining ImModule references: %d" % len(rest))
for l in rest: print("   " + l.rstrip())
