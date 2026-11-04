#!/usr/bin/env python3
# fix_networkcountryiso.py — TelephonyManagerWrapper.getNetworkCountryIso(I) reflectively
# calls TelephonyManager.getNetworkCountryIso(int), which on A14 is a SLOT index; callers
# pass a subId (1) -> "invalid slot index 1" -> crash. Network country is network-global,
# so just delegate to the no-arg getNetworkCountryIso(). Ignores the subId/slot arg.
#
#   cd ~/ims_pull/imsservice
#   python3 fix_networkcountryiso.py
#
import re, glob, os, sys
f = None
for d in sorted(glob.glob("smali*")):
    p = os.path.join(d, "com/sec/internal/ims/util/os/TelephonyManagerWrapper.smali")
    if os.path.isfile(p): f = p; break
if not f: sys.exit("!! TelephonyManagerWrapper.smali not found")

src = open(f, encoding="utf-8").read()
good = (".method public getNetworkCountryIso(I)Ljava/lang/String;\n"
        "    .locals 1\n"
        '    .param p1, "subId"    # I\n\n'
        "    # A14: the int overload is a SLOT index, not a subId. On single-SIM just use\n"
        "    # the no-arg network country, avoiding invalid-slot IllegalArgumentException.\n"
        "    iget-object v0, p0, Lcom/sec/internal/ims/util/os/TelephonyManagerWrapper;->mImpl:Landroid/telephony/TelephonyManager;\n\n"
        "    invoke-virtual {v0}, Landroid/telephony/TelephonyManager;->getNetworkCountryIso()Ljava/lang/String;\n\n"
        "    move-result-object v0\n\n"
        "    return-object v0\n"
        ".end method\n")
# target ONLY the (I) overload, not the no-arg one
new = re.sub(r'\.method public getNetworkCountryIso\(I\)Ljava/lang/String;.*?\.end method\n',
             good, src, count=1, flags=re.S)
if new == src:
    print("no change (method not matched or already fixed)")
else:
    open(f, "w", encoding="utf-8").write(new)
    print("patched getNetworkCountryIso(I) in", f)
