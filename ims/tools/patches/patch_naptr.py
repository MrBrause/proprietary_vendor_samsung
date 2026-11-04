#!/usr/bin/env python3
# patch_naptr.py — enable DNS/NAPTR P-CSCF discovery for the Telekom IMS profile by setting
# need_naptr_dns=true on the TMobile_DE profile(s) in res/raw/imsprofile.json. The modem never
# returns a P-CSCF in PCO (pcscf=[]), so this turns on the 3GPP DNS fallback over the IMS bearer.
#
#   cd ~/ims_pull/imsservice
#   python3 patch_naptr.py res/raw/imsprofile.json
#
import json, sys, os, io

path = sys.argv[1] if len(sys.argv) > 1 else "res/raw/imsprofile.json"
if not os.path.isfile(path):
    sys.exit("!! not found: " + path)

raw = io.open(path, encoding="utf-8").read()
data = json.loads(raw)

MNO = "TMobile_DE"
changed = []

def walk(o):
    if isinstance(o, dict):
        # a profile object for Telekom?
        if o.get("mnoname") == MNO or ("name" in o and "TMobile Germany" in str(o.get("name"))):
            if "need_naptr_dns" in o:
                old = o["need_naptr_dns"]
                if old is not True:
                    o["need_naptr_dns"] = True
                    changed.append((o.get("name"), o.get("pdn"), old, True))
            else:
                o["need_naptr_dns"] = True
                changed.append((o.get("name"), o.get("pdn"), "(absent)", True))
        for v in o.values():
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)

walk(data)

if not changed:
    print("!! no TMobile_DE profile matched — check mnoname in the file")
    sys.exit(2)

# backup once, then write compact (match original formatting style: no spaces)
if not os.path.exists(path + ".bak"):
    io.open(path + ".bak", "w", encoding="utf-8").write(raw)
io.open(path, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, separators=(",", ":")))

print("patched need_naptr_dns=true on %d Telekom profile(s):" % len(changed))
for name, pdn, old, new in changed:
    print("   name=%r pdn=%r  need_naptr_dns: %s -> %s" % (name, pdn, old, new))
print("backup:", path + ".bak")
