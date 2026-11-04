#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_pcscf_linkprops.py  -- herolte VoLTE bring-up (final rung: P-CSCF plumbing)

After the CSC gate opened, the engine now builds a RegisterTask, brings up the
dedicated Telekom IMS PDN, and the modem DOES return the P-CSCF -- but AOSP hands
it to the engine inside android.net.LinkProperties (PcscfAddresses: [...]), while
Samsung's engine reads it from system properties:

    RegiMgrBase: readPcscfFromProperties: iface rmnet2
    RegiMgrBase<0>: getPcscfAddress: []
    RegiMgrBase<0>: tryRegister: pcscf is null. return..
    RegiMgrBase: registration failure due to empty p-cscf

readPcscfFromProperties(iface) builds names "ril.pcscf{v4,v6}.{gsm,cdma}<lastChar(iface)>.<idx>"
and SystemProperties.get()s them. Samsung's libsitril populates those on stock; the
AOSP RIL does not -- it only fills LinkProperties. So every read is empty.

Because the Telekom profile is PCO-based (isPcoUsed==true), getPcscfAddresses()
commits to readPcscfFromProperties and never falls back to the profile's static
pcscf list -- so there is no config-only workaround. We patch the read path.

Fix: at the TOP of readPcscfFromProperties(String iface), look up the live P-CSCF
from LinkProperties via ConnectivityManager (mContext), matched by interface name,
and return it if found. If nothing is found (or anything throws), fall through to
the original property-based logic untouched -- so behaviour on a real Samsung RIL
is unchanged. A Log.d("PCSCFFIX", ...) marker proves the patched path ran.

Usage:
    python3 fix_pcscf_linkprops.py <apktool_dir | RegistrationManagerBase.smali>
Re-runnable: strips any previous marker-delimited injection before re-injecting.

NOTE: the AOSP getter is LinkProperties.getPcscfServers() (NOT getPcscfServerAddresses,
which does not exist on A14 and triggers NoSuchMethodError). com.sec.imsservice runs as
uid system (1000) / privileged system app, so the @hide getPcscfServers() is callable.
The guard catches Ljava/lang/Throwable; (NOT just Exception) because NoSuchMethodError /
hidden-API link failures are Errors, not Exceptions -- on any such failure we fall through
to the original property logic instead of crashing the IMS service.
"""
import os, sys

CLASS   = "Lcom/sec/internal/ims/imsservice/RegistrationManagerBase;"
METHOD  = ".method private readPcscfFromProperties(Ljava/lang/String;)Ljava/util/List;"
BEGIN   = "    # --- pcscf_from_linkprops BEGIN ---"
END     = "    # --- pcscf_from_linkprops END ---"

INJECTION = """    # --- pcscf_from_linkprops BEGIN ---
    # NOTE: method is .locals 19 -> p0=v19, p1=v20, which many opcodes cannot encode.
    # Copy params into low regs (move-object/from16) and only ever use v0..v15.
    :lp_try_start
    new-instance v0, Ljava/util/ArrayList;
    invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V
    move-object/from16 v1, p1
    move-object/from16 v2, p0
    invoke-static {v1}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z
    move-result v3
    if-nez v3, :lp_done
    iget-object v3, v2, Lcom/sec/internal/ims/imsservice/RegistrationManagerBase;->mContext:Landroid/content/Context;
    if-eqz v3, :lp_done
    const-class v4, Landroid/net/ConnectivityManager;
    invoke-virtual {v3, v4}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;
    move-result-object v3
    check-cast v3, Landroid/net/ConnectivityManager;
    if-eqz v3, :lp_done
    invoke-virtual {v3}, Landroid/net/ConnectivityManager;->getAllNetworks()[Landroid/net/Network;
    move-result-object v4
    if-eqz v4, :lp_done
    array-length v5, v4
    const/4 v6, 0x0
    :lp_loop
    if-ge v6, v5, :lp_check
    aget-object v7, v4, v6
    invoke-virtual {v3, v7}, Landroid/net/ConnectivityManager;->getLinkProperties(Landroid/net/Network;)Landroid/net/LinkProperties;
    move-result-object v8
    if-eqz v8, :lp_next
    invoke-virtual {v8}, Landroid/net/LinkProperties;->getInterfaceName()Ljava/lang/String;
    move-result-object v9
    if-eqz v9, :lp_next
    invoke-virtual {v9, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v9
    if-eqz v9, :lp_next
    invoke-virtual {v8}, Landroid/net/LinkProperties;->getPcscfServers()Ljava/util/List;
    move-result-object v8
    if-eqz v8, :lp_next
    invoke-interface {v8}, Ljava/util/List;->iterator()Ljava/util/Iterator;
    move-result-object v9
    :lp_addr_loop
    invoke-interface {v9}, Ljava/util/Iterator;->hasNext()Z
    move-result v10
    if-eqz v10, :lp_next
    invoke-interface {v9}, Ljava/util/Iterator;->next()Ljava/lang/Object;
    move-result-object v10
    check-cast v10, Ljava/net/InetAddress;
    invoke-virtual {v10}, Ljava/net/InetAddress;->getHostAddress()Ljava/lang/String;
    move-result-object v10
    if-eqz v10, :lp_addr_loop
    invoke-interface {v0, v10}, Ljava/util/List;->add(Ljava/lang/Object;)Z
    goto :lp_addr_loop
    :lp_next
    add-int/lit8 v6, v6, 0x1
    goto :lp_loop
    :lp_check
    invoke-interface {v0}, Ljava/util/List;->isEmpty()Z
    move-result v3
    if-nez v3, :lp_done
    const-string/jumbo v3, "RegiMgrBase"
    new-instance v4, Ljava/lang/StringBuilder;
    invoke-direct {v4}, Ljava/lang/StringBuilder;-><init>()V
    const-string/jumbo v5, "PCSCFFIX: pcscf from LinkProperties iface="
    invoke-virtual {v4, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-result-object v4
    invoke-virtual {v4, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-result-object v4
    const-string/jumbo v5, " -> "
    invoke-virtual {v4, v5}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-result-object v4
    invoke-virtual {v4, v0}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;
    move-result-object v4
    invoke-virtual {v4}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v4
    invoke-static {v3, v4}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I
    return-object v0
    :lp_try_end
    .catch Ljava/lang/Throwable; {:lp_try_start .. :lp_try_end} :lp_catch
    :lp_catch
    goto :lp_done
    :lp_done
    # --- pcscf_from_linkprops END ---"""


def find_smali(root):
    if os.path.isfile(root) and root.endswith(".smali"):
        return [root]
    hits = []
    for dp, _d, fs in os.walk(root):
        if "RegistrationManagerBase.smali" in fs:
            hits.append(os.path.join(dp, "RegistrationManagerBase.smali"))
    return hits


def strip_old(lines):
    out, i, n = [], 0, len(lines)
    while i < n:
        if lines[i].strip() == BEGIN.strip():
            while i < n and lines[i].strip() != END.strip():
                i += 1
            i += 1  # skip END
            continue
        out.append(lines[i]); i += 1
    return out


def patch(path):
    lines = open(path, "r", encoding="utf-8").read().split("\n")
    lines = strip_old(lines)

    # locate the method
    try:
        mi = next(i for i, l in enumerate(lines) if l.strip() == METHOD.strip())
    except StopIteration:
        print("  skip (method not in this file): %s" % path); return False

    # find .prologue within the method
    pi = None
    for i in range(mi, len(lines)):
        if lines[i].strip() == ".end method":
            break
        if lines[i].strip() == ".prologue":
            pi = i; break
    if pi is None:
        print("  ERROR: .prologue not found in readPcscfFromProperties of %s" % path)
        return False

    # sanity: the method declares enough registers (.locals 19 in stock)
    for i in range(mi, pi):
        s = lines[i].strip()
        if s.startswith(".locals") or s.startswith(".registers"):
            try:
                cnt = int(s.split()[1])
                if cnt < 9:
                    print("  WARN: only %d regs declared; injection uses v0-v8" % cnt)
            except Exception:
                pass
            break

    new = lines[:pi+1] + INJECTION.split("\n") + lines[pi+1:]
    open(path, "w", encoding="utf-8").write("\n".join(new))
    print("  patched: %s  (readPcscfFromProperties now reads LinkProperties; log tag PCSCFFIX)" % path)
    return True


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    files = find_smali(root)
    if not files:
        print("No RegistrationManagerBase.smali found under %s" % root); sys.exit(1)
    done = False
    for f in files:
        done |= patch(f)
    print("done." if done else "nothing to do.")


if __name__ == "__main__":
    main()
