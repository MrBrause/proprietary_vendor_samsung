#!/usr/bin/env python3
# Neutralize calls to Samsung-only framework methods absent on LineageOS that
# throw NoSuchMethodError and crash the ported imsservice. For each configured
# method, rewrite every call site:
#     invoke-{virtual,...} {regs}, L<class>;-><method><descriptor>
#     [ .line / .local / .restart local / blank / comment lines ... ]   (debug info)
#     move-result vDEST            (optional, if the return value is used)
# into a safe constant (0 / false / null / 0L) in vDEST, correctly skipping any
# debug directives that baksmali places between the invoke and its move-result.
#
# Usage:  python3 fix_smali_samsung_api.py <decompiled_apk_dir>
# Add more (class, method, descriptor) tuples to METHODS as new ones surface.
import os, re, sys

METHODS = [
    ("Landroid/telephony/SubscriptionManager;", "getDefaultDataPhoneId", "()I"),
]

def const_for(ret, dest):
    if ret in ("I","Z","B","S","C","F"):
        return f"    const/16 {dest}, 0x0\n"
    if ret in ("J","D"):
        return f"    const-wide/16 {dest}, 0x0\n"
    return f"    const/4 {dest}, 0x0\n"   # object/array -> null

INV = re.compile(r'^\s*invoke-\w+(?:/range)?\s*\{[^}]*\},\s*(L[\w/$]+;)->(\w+)(\([^)]*\)\S+)\s*$')
MR  = re.compile(r'^\s*move-result(?:-wide|-object)?\s+(v\d+)\s*$')
def is_skippable(line):
    s = line.strip()
    return s == "" or s.startswith(".") or s.startswith("#")

def patch_file(path, specs):
    with open(path, "r", errors="surrogateescape") as f:
        lines = f.readlines()
    out, i, n = [], 0, 0
    while i < len(lines):
        m = INV.match(lines[i])
        if m and (m.group(1), m.group(2), m.group(3)) in specs:
            ret = m.group(3).split(")")[-1]
            # scan ahead for move-result, buffering skippable debug directives
            j = i + 1
            buf = []
            while j < len(lines) and is_skippable(lines[j]):
                buf.append(lines[j]); j += 1
            mr = MR.match(lines[j]) if j < len(lines) else None
            if mr:
                # drop the invoke, keep the intervening directives, turn move-result into const
                out.extend(buf)
                out.append(const_for(ret, mr.group(1)))
                i = j + 1
            else:
                # return value unused: drop only the invoke, keep everything else
                out.extend(buf)
                i = j
            n += 1
            continue
        out.append(lines[i]); i += 1
    if n:
        with open(path, "w", errors="surrogateescape") as f:
            f.writelines(out)
    return n

def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    specs = set(METHODS); total = 0
    for dp, _, fs in os.walk(root):
        for fn in fs:
            if fn.endswith(".smali"):
                c = patch_file(os.path.join(dp, fn), specs)
                if c:
                    print(f"{c:3d}  {os.path.join(dp, fn)}"); total += c
    print("total call sites patched:", total)
    if total == 0:
        print("WARNING: nothing matched")

if __name__ == "__main__":
    main()
