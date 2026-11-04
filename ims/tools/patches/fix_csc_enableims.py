#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_csc_enableims.py  -- herolte VoLTE bring-up

Problem: RegistrationManagerBase's startup profile-load path bails with
    "simSlot[0] IMS is disabled by CSC. Do not load profiles"
because ImsCscFeature.getBoolean(phoneId,"CscFeature_IMS_EnableIMS") returns false.
On LOS there is no Samsung CSC feature data, so SemCscFeature.getBoolean(...) -> false,
and no RegisterTask is ever built (no IMS PDN, no REGISTER).

Fix: short-circuit ImsCscFeature.getBoolean(String) to return true for the IMS-enable
feature key(s). Everything else passes through to the real SemCscFeature logic, so no
other feature flag is disturbed. getBoolean(I,String) for slot 0 delegates to this, so
single-SIM slot-0 is covered.

Usage:
    python3 fix_csc_enableims.py <apktool_out_dir_or_ImsCscFeature.smali>
Idempotent: re-running is a no-op (checks for the injected label).
"""
import os, sys, re

# Feature keys to force true. Start surgical with just the IMS-enable gate; add more
# here only if a later boot log shows another "disabled by CSC"-style gate.
FORCE_TRUE = [
    "CscFeature_IMS_EnableIMS",
]

LABEL = ":csc_force_passthrough"

def find_smali(root):
    if os.path.isfile(root) and root.endswith(".smali"):
        return [root]
    hits = []
    for dirpath, _dirs, files in os.walk(root):
        if "ImsCscFeature.smali" in files:
            hits.append(os.path.join(dirpath, "ImsCscFeature.smali"))
    return hits

def build_injection():
    # v0 is free at method entry (.locals 2). p1 = tag (String).
    lines = []
    for i, key in enumerate(FORCE_TRUE):
        passlbl = ":csc_next_%d" % i
        lines += [
            '    const-string/jumbo v0, "%s"' % key,
            '    invoke-virtual {p1, v0}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z',
            '    move-result v0',
            '    if-eqz v0, %s' % passlbl,
            '    const/4 v0, 0x1',
            '    return v0',
            '    %s' % passlbl,
        ]
    return "\n".join(lines) + "\n"

def patch(path):
    src = open(path, "r", encoding="utf-8").read()
    if LABEL in src or "csc_next_0" in src:
        print("  already patched: %s" % path)
        return False

    # Match the single-arg getBoolean(String)Z method and inject right after its
    # .prologue line (locals/params already declared; v0 is safe to use).
    sig = ".method public getBoolean(Ljava/lang/String;)Z"
    mstart = src.find(sig)
    if mstart < 0:
        print("  ERROR: getBoolean(String)Z not found in %s" % path)
        return False
    prologue = src.find(".prologue", mstart)
    mend = src.find(".end method", mstart)
    if prologue < 0 or prologue > mend:
        print("  ERROR: .prologue not found in getBoolean(String) of %s" % path)
        return False

    inj = "\n" + build_injection()
    eol = src.find("\n", prologue)
    patched = src[:eol+1] + inj + src[eol+1:]
    open(path, "w", encoding="utf-8").write(patched)
    print("  patched: %s  (forced true: %s)" % (path, ", ".join(FORCE_TRUE)))
    return True

def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    files = find_smali(root)
    if not files:
        print("No ImsCscFeature.smali found under %s" % root)
        sys.exit(1)
    any_done = False
    for f in files:
        any_done |= patch(f)
    print("done." if any_done else "nothing to do.")

if __name__ == "__main__":
    main()
