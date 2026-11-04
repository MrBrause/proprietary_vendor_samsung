#!/usr/bin/env python3
# fix_getpcscfip_linkprops.py
#
# Make RegistrationManagerBase.getPcscfIpAddress(task, iface, profile) return the
# IMS PDN's P-CSCF straight from AOSP LinkProperties, bypassing Samsung's
# governor/NAPTR post-processing that returns empty on LineageOS.
#
# WHY: tryRegister() calls getPcscfIpAddress() (String). On this engine build that
# method takes the good list from getPcscfAddresses()->readPcscfFromProperties()
# but then drops it in checkValidPcscfIp()/sendDnsQuery()/getCurrentPcscfIp() and
# returns "", so tryRegister logs "pcscf is null. return.." and never sends REGISTER.
# This injects an early return at the method prologue: read getPcscfServers() for
# the iface, set it on the task, prime the governor list, return the first address.
#
# Idempotent (marker-guarded) and safe to run repeatedly against the ORIGINAL smali.
# Run AFTER (or alongside) fix_pcscf_linkprops.py - they patch different methods.
#
#   python3 fix_getpcscfip_linkprops.py path/to/RegistrationManagerBase.smali
#
# A .bak is written next to the file on first run (kept outside ./imsservice if you
# prefer - this script only touches the file you pass it).

import sys, re, shutil, os

METHOD_SIG = (".method public getPcscfIpAddress("
              "Lcom/sec/internal/ims/imsservice/RegisterTask;"
              "Ljava/lang/String;"
              "Lcom/sec/ims/settings/ImsProfile;)Ljava/lang/String;")

BEGIN = "    # --- getpcscfip_from_linkprops BEGIN ---"
END   = "    # --- getpcscfip_from_linkprops END ---"

# .locals 27 -> p0=v27 (this), p1=v28 (task), p2=v29 (iface), p3=v30 (profile).
# Those high regs can't be encoded by most opcodes, so copy params into low regs
# via move-object/from16 and use only v0..v15 (identical constraint to the
# readPcscfFromProperties patch).
INJECT = """\
""" + BEGIN + """
    :gp_try_start
    new-instance v0, Ljava/util/ArrayList;
    invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V
    move-object/from16 v1, p2
    move-object/from16 v2, p0
    invoke-static {v1}, Landroid/text/TextUtils;->isEmpty(Ljava/lang/CharSequence;)Z
    move-result v3
    if-nez v3, :gp_done
    iget-object v3, v2, Lcom/sec/internal/ims/imsservice/RegistrationManagerBase;->mContext:Landroid/content/Context;
    if-eqz v3, :gp_done
    const-class v4, Landroid/net/ConnectivityManager;
    invoke-virtual {v3, v4}, Landroid/content/Context;->getSystemService(Ljava/lang/Class;)Ljava/lang/Object;
    move-result-object v3
    check-cast v3, Landroid/net/ConnectivityManager;
    if-eqz v3, :gp_done
    invoke-virtual {v3}, Landroid/net/ConnectivityManager;->getAllNetworks()[Landroid/net/Network;
    move-result-object v4
    if-eqz v4, :gp_done
    array-length v5, v4
    const/4 v6, 0x0
    :gp_loop
    if-ge v6, v5, :gp_check
    aget-object v7, v4, v6
    invoke-virtual {v3, v7}, Landroid/net/ConnectivityManager;->getLinkProperties(Landroid/net/Network;)Landroid/net/LinkProperties;
    move-result-object v8
    if-eqz v8, :gp_next
    invoke-virtual {v8}, Landroid/net/LinkProperties;->getInterfaceName()Ljava/lang/String;
    move-result-object v9
    if-eqz v9, :gp_next
    invoke-virtual {v9, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v9
    if-eqz v9, :gp_next
    invoke-virtual {v8}, Landroid/net/LinkProperties;->getPcscfServers()Ljava/util/List;
    move-result-object v8
    if-eqz v8, :gp_next
    invoke-interface {v8}, Ljava/util/List;->iterator()Ljava/util/Iterator;
    move-result-object v9
    :gp_addr_loop
    invoke-interface {v9}, Ljava/util/Iterator;->hasNext()Z
    move-result v10
    if-eqz v10, :gp_next
    invoke-interface {v9}, Ljava/util/Iterator;->next()Ljava/lang/Object;
    move-result-object v10
    check-cast v10, Ljava/net/InetAddress;
    invoke-virtual {v10}, Ljava/net/InetAddress;->getHostAddress()Ljava/lang/String;
    move-result-object v10
    if-eqz v10, :gp_addr_loop
    invoke-interface {v0, v10}, Ljava/util/List;->add(Ljava/lang/Object;)Z
    goto :gp_addr_loop
    :gp_next
    add-int/lit8 v6, v6, 0x1
    goto :gp_loop
    :gp_check
    invoke-interface {v0}, Ljava/util/List;->isEmpty()Z
    move-result v3
    if-nez v3, :gp_done
    const/4 v3, 0x0
    invoke-interface {v0, v3}, Ljava/util/List;->get(I)Ljava/lang/Object;
    move-result-object v3
    check-cast v3, Ljava/lang/String;
    move-object/from16 v4, p1
    invoke-virtual {v4, v3}, Lcom/sec/internal/ims/imsservice/RegisterTask;->setPcscfHostname(Ljava/lang/String;)V
    iget-object v5, v4, Lcom/sec/internal/ims/imsservice/RegisterTask;->mGovernor:Lcom/sec/internal/ims/imsservice/governor/RegistrationGovernor;
    if-eqz v5, :gp_log
    invoke-virtual {v5, v0}, Lcom/sec/internal/ims/imsservice/governor/RegistrationGovernor;->updatePcscfIpList(Ljava/util/List;)V
    :gp_log
    const-string/jumbo v6, "RegiMgrBase"
    new-instance v7, Ljava/lang/StringBuilder;
    invoke-direct {v7}, Ljava/lang/StringBuilder;-><init>()V
    const-string/jumbo v8, "PCSCFFIX(ip): return pcscf "
    invoke-virtual {v7, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-result-object v7
    invoke-virtual {v7, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-result-object v7
    const-string/jumbo v8, " iface="
    invoke-virtual {v7, v8}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-result-object v7
    invoke-virtual {v7, v1}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    move-result-object v7
    invoke-virtual {v7}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v7
    invoke-static {v6, v7}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I
    return-object v3
    :gp_try_end
    .catch Ljava/lang/Throwable; {:gp_try_start .. :gp_try_end} :gp_catch
    :gp_catch
    goto :gp_done
    :gp_done
""" + END + "\n"


def main():
    if len(sys.argv) != 2:
        print("usage: python3 fix_getpcscfip_linkprops.py RegistrationManagerBase.smali")
        sys.exit(2)
    path = sys.argv[1]
    src = open(path, encoding="utf-8").read()

    mstart = src.find(METHOD_SIG)
    if mstart < 0:
        print("ERROR: getPcscfIpAddress(RegisterTask;String;ImsProfile) not found - "
              "wrong file or different engine build.")
        sys.exit(1)

    mend = src.find("\n.end method", mstart)
    if mend < 0:
        print("ERROR: could not find end of method.")
        sys.exit(1)
    body = src[mstart:mend]

    if BEGIN in body:
        print("Already patched (marker present) - nothing to do.")
        return

    # insert right after the method's first .prologue line
    m = re.search(r"\n[ \t]*\.prologue[ \t]*\n", body)
    if not m:
        print("ERROR: no .prologue in getPcscfIpAddress - aborting to stay safe.")
        sys.exit(1)
    ins_at = mstart + m.end()

    shutil.copy2(path, path + ".bak")
    patched = src[:ins_at] + INJECT + src[ins_at:]
    open(path, "w", encoding="utf-8").write(patched)
    print("Patched getPcscfIpAddress: injected LinkProperties P-CSCF early-return.")
    print("Backup: " + path + ".bak")


if __name__ == "__main__":
    main()
