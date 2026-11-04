#!/usr/bin/env python3
# gen_gsma_stubs.py  —  generate resolvable smali stubs for com.gsma.services.rcs.*
#
# Run from the apktool output dir (the one that contains smali/ , smali_classes2/):
#     cd ~/ims_pull/imsservice
#     python3 gen_gsma_stubs.py
#
# It scans every smali*/ tree for references to Lcom/gsma/services/rcs...;, works out
# for each type whether it is an interface or a class (and whether an AIDL $Stub), and
# which members the real code actually touches, then writes one stub .smali per type into
# smali_classes3/ (a fresh dex so we don't overflow classes2.dex).
#
# The stubs only need to exist and expose the referenced members so the verifier/linker
# resolves them; every RCS runtime switch is off, so the real RCS code paths never run.
#
import os, re, sys, glob

ROOT = os.getcwd()
smali_dirs = sorted(d for d in glob.glob("smali*") if os.path.isdir(d))
if not smali_dirs:
    sys.exit("!! no smali*/ dirs here — run from the apktool output dir (has smali/).")
OUT = "smali_classes3"

TYPE = r'Lcom/gsma/services/rcs[A-Za-z0-9_/$]*;'
# member ref: L<type>;->name(args)ret   OR   L<type>;->name:fieldtype
MEMBER = re.compile(r'(L' + r'com/gsma/services/rcs[A-Za-z0-9_/$]*' + r';)->'
                    r'([A-Za-z0-9_<>$]+)'
                    r'(?:\(([^)]*)\)(\[*(?:L[^;]+;|[VZBSCIJFD]))|:(\[*(?:L[^;]+;|[VZBSCIJFD])))')
SUPER   = re.compile(r'^\.super\s+(L' + r'com/gsma/services/rcs[A-Za-z0-9_/$]*' + r';)')
IMPL    = re.compile(r'^\.implements\s+(L' + r'com/gsma/services/rcs[A-Za-z0-9_/$]*' + r';)')
NEWINST = re.compile(r'new-instance\s+[vp]\d+,\s+(L' + r'com/gsma/services/rcs[A-Za-z0-9_/$]*' + r';)')
ANYTYPE = re.compile(TYPE)

types = set()                      # every gsma type seen anywhere
supers = set(); newed = set(); implemented = set(); inviface = set()
# members[type] = dict keyed by (kind,name,sig) -> record
#   kind: 'sfield','ifield','smethod','vmethod','ctor'
members = {}

def add_member(t, kind, name, sig):
    members.setdefault(t, {})[(kind, name, sig)] = True

for d in smali_dirs:
    for dp, _, fns in os.walk(d):
        for fn in fns:
            if not fn.endswith(".smali"): continue
            p = os.path.join(dp, fn)
            with open(p, encoding="utf-8", errors="replace") as fh:
                for raw in fh:
                    line = raw.strip()
                    for m in ANYTYPE.findall(line):
                        types.add(m)
                    ms = SUPER.match(line);     supers.add(ms.group(1)) if ms else None
                    mi = IMPL.match(line);      implemented.add(mi.group(1)) if mi else None
                    for mn in NEWINST.findall(line): newed.add(mn)
                    is_inviface_line = line.startswith("invoke-interface")
                    for mo in MEMBER.finditer(line):
                        if is_inviface_line:
                            inviface.add(mo.group(1))   # only the method OWNER, not arg types
                        t = mo.group(1); name = mo.group(2)
                        args = mo.group(3); ret = mo.group(4); ftype = mo.group(5)
                        if ftype is not None:
                            # field
                            if line.startswith(("sget", "sput")):
                                add_member(t, "sfield", name, ftype)
                            else:
                                add_member(t, "ifield", name, ftype)
                        else:
                            sig = "(%s)%s" % (args, ret)
                            if name == "<init>":
                                add_member(t, "ctor", name, sig)
                            elif line.startswith("invoke-static"):
                                add_member(t, "smethod", name, sig)
                            else:
                                add_member(t, "vmethod", name, sig)

# make sure nested/outer owners of referenced members are in the type set
for t in list(members): types.add(t)

def is_interface(t):
    if t in supers or t in newed:      # extended or instantiated => class
        return False
    if t in implemented or t in inviface:
        return True
    return False

def ret_body(ret):
    # return default for a method whose return descriptor is `ret`
    if ret == "V":
        return "    return-void\n", 0
    if ret in ("J", "D"):
        return "    const-wide/16 v0, 0x0\n    return-wide v0\n", 2
    if ret in ("Z", "B", "S", "C", "I", "F"):
        return "    const/4 v0, 0x0\n    return v0\n", 1
    # object / array
    return "    const/4 v0, 0x0\n    return-object v0\n", 1

def emit(t):
    cls = t                                   # e.g. Lcom/gsma/services/rcs/.../Foo$Bar;
    inner = cls[1:-1]                          # com/.../Foo$Bar
    iface = is_interface(t)
    is_stub = inner.endswith("$Stub")
    sup = "Landroid/os/Binder;" if is_stub else "Ljava/lang/Object;"
    L = []
    if iface:
        L.append(".class public interface abstract %s" % cls)
        L.append(".super Ljava/lang/Object;")
    else:
        L.append(".class public %s" % cls)
        L.append(".super %s" % sup)
    L.append("")
    mem = members.get(t, {})
    # fields
    for (kind, name, sig) in mem:
        if kind == "sfield":
            L.append(".field public static %s:%s" % (name, sig))
        elif kind == "ifield":
            L.append(".field public %s:%s" % (name, sig))
    if any(k in ("sfield", "ifield") for (k, _, _) in mem):
        L.append("")
    # always give a concrete class a no-arg <init> (super call) so subclassing/new works
    emitted_ctor_noarg = False
    if not iface:
        L.append(".method public constructor <init>()V")
        L.append("    .locals 0")
        L.append("    invoke-direct {p0}, %s-><init>()V" % sup)
        L.append("    return-void")
        L.append(".end method")
        L.append("")
        emitted_ctor_noarg = True
    # referenced constructors (with args) -> call super()V, ignore args
    for (kind, name, sig) in mem:
        if kind != "ctor": continue
        if sig == "()V" and emitted_ctor_noarg:    # already have no-arg
            continue
        if iface:  # interfaces have no ctors
            continue
        L.append(".method public constructor <init>%s" % sig)
        L.append("    .locals 0")
        L.append("    invoke-direct {p0}, %s-><init>()V" % sup)
        L.append("    return-void")
        L.append(".end method")
        L.append("")
    # methods
    for (kind, name, sig) in mem:
        if kind not in ("smethod", "vmethod"): continue
        ret = sig[sig.rindex(")") + 1:]
        if iface:
            L.append(".method public abstract %s%s" % (name, sig))
            L.append(".end method")
            L.append("")
        else:
            static = " static" if kind == "smethod" else ""
            body, nloc = ret_body(ret)
            L.append(".method public%s %s%s" % (static, name, sig))
            L.append("    .locals %d" % nloc)
            L.append(body.rstrip("\n"))
            L.append(".end method")
            L.append("")
    path = os.path.join(OUT, inner + ".smali")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return iface, is_stub

ni = ncl = nstub = 0
for t in sorted(types):
    iface, is_stub = emit(t)
    if iface: ni += 1
    else:
        ncl += 1
        if is_stub: nstub += 1

print("gsma stub generation complete")
print("  output dir : %s/" % OUT)
print("  types      : %d  (interfaces=%d, classes=%d of which $Stub=%d)" % (len(types), ni, ncl, nstub))
print("  with members referenced: %d" % len(members))
print()
print("Spot-check CommonServiceConfiguration$Settings (needs CONTENT_URI):")
scp = os.path.join(OUT, "com/gsma/services/rcs/CommonServiceConfiguration$Settings.smali")
if os.path.exists(scp):
    with open(scp) as fh: print("".join("    " + l for l in fh))
else:
    print("    (not generated — check the reference scan)")
