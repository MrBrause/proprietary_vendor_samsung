#!/usr/bin/env python3
# fix_clinit_tag.py — repair ServiceStateWrapper.<clinit>, whose quickened opcodes
# (invoke-virtual-quick vtable@57 + return-void-no-barrier) were left as NOPs by the
# deodex, producing a VerifyError. TAG is only a log tag, so set it to a literal.
#
#   cd ~/ims_pull/imsservice
#   python3 fix_clinit_tag.py
#
import re, glob, os, sys
f = None
for d in sorted(glob.glob("smali*")):
    p = os.path.join(d, "com/sec/internal/ims/util/os/ServiceStateWrapper.smali")
    if os.path.isfile(p): f = p; break
if not f: sys.exit("!! ServiceStateWrapper.smali not found")

src = open(f, encoding="utf-8").read()
good = (".method static constructor <clinit>()V\n"
        "    .registers 1\n\n"
        '    const-string v0, "ServiceStateWrapper"\n\n'
        "    sput-object v0, Lcom/sec/internal/ims/util/os/ServiceStateWrapper;->TAG:Ljava/lang/String;\n\n"
        "    return-void\n"
        ".end method\n")
new = re.sub(r'\.method static constructor <clinit>\(\)V.*?\.end method\n',
             good, src, count=1, flags=re.S)
if new == src:
    print("no change (clinit not matched or already fixed)")
else:
    open(f, "w", encoding="utf-8").write(new)
    print("patched <clinit> in", f)
