#!/usr/bin/env python3
# fix_force_switch.py — force DeviceConfigManager.queryImsSwitch to report enabled=1 for
# exactly ims / volte / mmtel / smsip (leaving rcs, options, presence, video types, etc.
# to their normal DB-backed path). This bypasses the missing VoLTE provisioning so the
# engine actually registers for MMTEL. Injects a short-circuit at the top of the per-name
# loop body, right before the existing `const-string/jumbo v3, "volte"` compare.
#
#   cd ~/ims_pull/imsservice   &&   python3 fix_force_switch.py
#
import re, glob, os, sys
f = None
for d in sorted(glob.glob("smali*")):
    p = os.path.join(d, "com/sec/internal/ims/imsservice/DeviceConfigManager.smali")
    if os.path.isfile(p): f = p; break
if not f: sys.exit("!! DeviceConfigManager.smali not found")
src = open(f, encoding="utf-8").read()

if ":force_on_q" in src:
    sys.exit("already patched (found :force_on_q)")

# locate the queryImsSwitch method
m = re.search(r'\.method public queryImsSwitch\(\[Ljava/lang/String;\)Landroid/database/Cursor;.*?\.end method\n',
              src, flags=re.S)
if not m:
    sys.exit("!! queryImsSwitch method not found")
method = m.group(0)

# anchor: the first `.line 771` + volte compare inside the method
anchor = re.search(r'\n(\s*)(\.line \d+\n\s*const-string/jumbo v3, "volte")', method)
if not anchor:
    anchor = re.search(r'\n(\s*)(const-string/jumbo v3, "volte")', method)
if not anchor:
    sys.exit("!! could not find the volte compare anchor in queryImsSwitch")
indent = anchor.group(1)

inj = "".join(indent + l + "\n" for l in [
    "# --- forced VoLTE switch: ims/volte/mmtel/smsip => 1 ---",
    'const-string/jumbo v3, "mmtel"',
    "invoke-virtual {v3, v1}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z",
    "move-result v3",
    "if-nez v3, :force_on_q",
    'const-string/jumbo v3, "smsip"',
    "invoke-virtual {v3, v1}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z",
    "move-result v3",
    "if-nez v3, :force_on_q",
    'const-string/jumbo v3, "volte"',
    "invoke-virtual {v3, v1}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z",
    "move-result v3",
    "if-nez v3, :force_on_q",
    'const-string/jumbo v3, "ims"',
    "invoke-virtual {v3, v1}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z",
    "move-result v3",
    "if-eqz v3, :no_force_q",
    ":force_on_q",
    "new-array v8, v10, [Ljava/lang/Object;",
    "aput-object v1, v8, v5",
    "invoke-static {v4}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;",
    "move-result-object v3",
    "aput-object v3, v8, v4",
    "invoke-virtual {v0, v8}, Landroid/database/MatrixCursor;->addRow([Ljava/lang/Object;)V",
    "goto/16 :goto_2",
    ":no_force_q",
])

new_method = method[:anchor.start()] + "\n" + inj + method[anchor.start()+1:]
new_src = src[:m.start()] + new_method + src[m.end():]
open(f, "w", encoding="utf-8").write(new_src)
print("patched queryImsSwitch in", f)
print("forced names: ims, volte, mmtel, smsip -> enabled=1")
