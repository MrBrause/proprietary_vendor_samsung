# vendor/samsung/ims — PROVENANCE

Why this file exists: the installed IMS files are committed AS-IS (patched vendor blobs).
This manifest records, for each one, the pristine source + the exact transform (script) that
produced it, so the working state can be re-derived against a future pristine pull WITHOUT
re-guessing the order. The scripts live in tools/patches/ and are NOT part of the build.

Base upstream: github.com/jameskdev/android_samsung_imsservice (Galaxy A21s, Android 11).
The A21s engine + native drive the S7 Exynos-8890 modem unchanged (same RIL/modem family).

LEGEND: src = pristine input | script = transform in tools/patches/ | → md5 = result | path = install dest

====================================================================================
## Native libs  (install: /system/priv-app/imsservice/lib/arm64)
====================================================================================
libsec-ims.so
  src    : A21s libsec-ims.so            md5 a56cb950
  script : fix_libsecims_utf8.py   (length-preserving DT_NEEDED repoint libaudioclient.so -> libutf8_ims.so;
                                    restores the missing extern "C" utf8_length symbol gone on A14)
           fix_libsecims_amrwb.py  (NOP the two b.le guards in SdpCreator::InitCodecs so AMR-WB(4)/AMRBE-WB(5)
                                    are not skipped; pattern-based, survives rebuilds)
  → md5  : f715bf96
  note   : app-local lib (NOT /system/lib64); the engine loads it from priv-app/.../lib/arm64.

libu8len.so  (a.k.a. libutf8_ims.so)
  src    : built from tools/libutf8_ims/ source (tiny shim exporting ssize_t utf8_length)
  script : (compiled, not patched)
  path   : .../lib/arm64/libu8len.so   (fix_libsecims_utf8.py repoints libsec-ims DT_NEEDED to this)

libcurl2.so / libsslO.so / libcryptoO.so / libprotobuf-cpp-full{,-rtti}.so / libaresdns.so /
libsecnativefeature.so / libfloatingfeature.so
  src    : A21s engine prebuilts (ssl_out/ + lib64/), UNMODIFIED
  script : none (verbatim copies)
  TODO   : list the full set actually copied from imsservice/lib/arm64-v8a/. + their md5s.

====================================================================================
## Framework jars  (install: /system/framework)
====================================================================================
imscoremanager.jar
  src    : A21s imscoremanager.jar
  script : fix_clinit_*  (TODO: name the exact clinit/smali patches applied; what they fix)
           + the getDefaultDataPhoneId()I NoSuchMethodError fix (2 direct sites -> const 0)
           + fix_smali_samsung_api.py / fix_pcscf_linkprops.py / fix_csc_enableims.py (TODO: which apply to this jar)
  → file : imscoremanager_patched.jar
  pipeline: smali/baksmali via tree apktool.jar + Java launchers; zip-swap classes.dex.

imsmanager.jar
  src    : A21s imsmanager.jar
  script : TODO (verbatim, or which patch?)

secimshttpclient.jar
  src    : A21s secimshttpclient.jar  (from ims_stage1_jars/framework/)
  script : TODO (verbatim, or which patch?)

====================================================================================
## Engine APK  (install: /system/priv-app/imsservice/imsservice.apk)
====================================================================================
imsservice.apk
  src    : A21s com.sec.imsservice APK
  md5    : f0ef8e45  (engine-only; the AOSP relay app was dropped from the release — HeroImsBridge replaces it)
  script : TODO (dex patches applied to the APK itself, if any, vs only to its libs/jars)
  privapp: needs privapp-permissions-com.sec.imsservice.xml with 8 perms (3 added for A14: MONITOR_DEFAULT_SMS_PACKAGE,
           CONNECTIVITY_USE_RESTRICTED_NETWORKS, BIND_IMS_SERVICE) or A14 bootloops.

====================================================================================
## Daemons + init  (install: /system/bin, /system/etc/init)
====================================================================================
imsd            : stock_imsd/imsd (A21s), verbatim.  rc: imsd.rc.
multiclientd    : jameskdev-repo A21s binary, UNPATCHED.  md5 a08abd64.
                  (The A1 whitelist patch fix_multiclientd_audiowl.py is SHELVED — do NOT bake it;
                   it causes echo+overdrive on herolte. Keep stock.)
multiclientd.rc : jameskdev rc with the slot2 trigger COMMENTED OUT (kills the -c 2 crash-loop spam):
                    #on property:ril.halservice.registered.slot2=true
                    #   start multiclient-daemon1

====================================================================================
## CSC + IMS config  (install: /system/csc)
====================================================================================
customer.xml    : GENERIC/carrier-agnostic. One <NetworkInfo> per MCCMNC (~456 from mnomap.json) ->
                  <NetworkName>IMS</NetworkName>; one <Setting> keyed "IMS": EnableVoLTE=true,
                  Voice_Domain_Preference_EUTRAN=imspsvoicepreferred, SS_Domain_Preference=ps_only_psregied,
                  EnableSMSoverIP=true. (generated; see tools/)  TODO: note the generator.
customer_cs.xml : same but VoLTE OFF (reboot hard-disable target for the 4G toggle).
imsupdate.json  : AMR-WB known-good (TMobile_DE: enable_evs_codec:false, amrwb_mode "0,1,2",
                  amrwboa 104, amrwbbe 98, dtmf_wb 102). Agnostic variant targets "default"/"DEFAULT".
                  (EVS: add "EVS" to audio_codec to offer SWB — not enabled yet.)

====================================================================================
## Built-from-source (NOT blobs — live as source in this repo)
====================================================================================
apps/HeroImsBridge/     : v13b. AOSP ImsService relay -> Samsung engine. Key fixes: v3 createCallProfile
                          override, v12 cs_only latch only on CELLULAR radioTech, v13b onRingingBack ->
                          callSessionProgressing(DIRECTION_INACTIVE) = local ringback tone.
overlays/HeroImsConfigOverlay      : com.android.phone  config_ims_mmtel_package = org.lineageos.heroimsbridge
overlays/HeroVolteAvailableOverlay : android(framework-res) config_device_volte_available + config_carrier_volte_available = true
overlays/HeroCarrierVolteOverlay   : com.android.carrierconfig vendor.xml (carrier_volte_available_bool etc.)
                          All isStatic=true, priority 9999, product_specific.

====================================================================================
## Lives in universal8890-common, NOT here (shared SoC/codec/RIL)
====================================================================================
mixer_paths_0.xml  : DSP-bypass (incall_wb-handset-mic: ASRC1IN1L/R Input DSP3.1 -> ISRC2DEC1). TRACK A fix.
libsec-ril.so / libsecril-client.so (+ -dsds) : the UNRENAMED .orig (Blocker 7 — rild must keep @Multiclient).
init.samsungexynos8890.rc : reboot hard-disable action (persist.sys.heroims.cs_only=1 -> bind-mount customer_cs.xml).
