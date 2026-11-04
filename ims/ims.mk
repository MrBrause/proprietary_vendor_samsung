# ====================================================================================
# vendor/samsung/ims/ims-volte.mk — herolte VoLTE SUPPLEMENT to jameskdev's vendor-ims.mk
# Inherit BOTH from device.mk, this one AFTER jameskdev's:
#     $(call inherit-product, vendor/samsung/ims/vendor-ims.mk)        # jameskdev base
#     $(call inherit-product, vendor/samsung/ims/ims-volte.mk)         # our VoLTE deltas
#
# Contains ONLY what jameskdev's vendor-ims.mk does NOT already install. Do NOT duplicate
# his lines (imsd, multiclientd, imsd.rc, multiclientd.rc, imsmanager.jar, imsmanager_library.xml,
# privapp-permissions-com.sec.imsservice.xml, the imsservice APK) — his makefile installs your
# EDITED on-disk files (slot2-commented multiclientd.rc, 8-perm privapp xml) and the engine APK.
# Soong namespace already declared by jameskdev — not re-declared here.
#
# NOT here (live elsewhere): mixer_paths (device/samsung/herolte); RIL .orig libs + reboot
# cs_only init action (universal8890-common); CarrierConfig stays pristine (RRO handles it).
# ====================================================================================

LOCAL_IMS := vendor/samsung/ims

# ------------------------------------------------------------------------------------
# Extra framework jars jameskdev doesn't ship  (imscoremanager = PATCHED build)
# ------------------------------------------------------------------------------------
PRODUCT_COPY_FILES += \
    $(LOCAL_IMS)/proprietary/system/framework/imscoremanager.jar:$(TARGET_COPY_OUT_SYSTEM)/framework/imscoremanager.jar \
    $(LOCAL_IMS)/proprietary/system/framework/secimshttpclient.jar:$(TARGET_COPY_OUT_SYSTEM)/framework/secimshttpclient.jar

# ------------------------------------------------------------------------------------
# Extra permissions / lib decls + the IMS feature flag
# ------------------------------------------------------------------------------------
PRODUCT_COPY_FILES += \
    $(LOCAL_IMS)/proprietary/system/etc/permissions/imscoremanager_library.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/permissions/imscoremanager_library.xml \
    $(LOCAL_IMS)/proprietary/system/etc/permissions/secimshttpclient_library.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/permissions/secimshttpclient_library.xml \
    $(LOCAL_IMS)/proprietary/system/etc/permissions/android.hardware.telephony.ims.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/permissions/android.hardware.telephony.ims.xml

# HeroImsBridge privapp allowlist (Signature|privileged perms: READ_PRIVILEGED_PHONE_STATE,
# MODIFY_PHONE_STATE, BIND_IMS_SERVICE, ...). WITHOUT this, system_server aborts on boot (bootloop).
# Source moved with the app from packages/apps/HeroImsBridge -> vendor/samsung/ims/apps/HeroImsBridge.
PRODUCT_COPY_FILES += \
    $(LOCAL_IMS)/apps/HeroImsBridge/privapp-permissions-org.lineageos.heroimsbridge.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/permissions/privapp-permissions-org.lineageos.heroimsbridge.xml

# ------------------------------------------------------------------------------------
# Engine app-local native libs  (/system/priv-app/imsservice/lib/arm64) — the engine loads
# THESE (confirmed via /proc/maps), not the /system/lib64 copies jameskdev installs.
# libsec-ims.so = fix_libsecims_utf8.py + fix_libsecims_amrwb.py PATCHED (md5 f715bf96).
# libu8len.so   = the utf8 shim (libsec-ims DT_NEEDED repointed to it).
# RECONCILE: also make jameskdev's proprietary/system/lib64/libsec-ims.so the PATCHED build,
#            so no stale unpatched copy sits in /system/lib64.
# ------------------------------------------------------------------------------------
IMS_A64 := $(LOCAL_IMS)/proprietary/system/priv-app/imsservice/lib/arm64
IMS_DST := $(TARGET_COPY_OUT_SYSTEM)/priv-app/imsservice/lib/arm64
PRODUCT_COPY_FILES += \
    $(IMS_A64)/libsec-ims.so:$(IMS_DST)/libsec-ims.so \
    $(IMS_A64)/libu8len.so:$(IMS_DST)/libu8len.so \
    $(IMS_A64)/libcurl2.so:$(IMS_DST)/libcurl2.so \
    $(IMS_A64)/libcutils.so:$(IMS_DST)/libcutils.so \
    $(IMS_A64)/libutils.so:$(IMS_DST)/libutils.so \
    $(IMS_A64)/libsslO.so:$(IMS_DST)/libsslO.so \
    $(IMS_A64)/libssl.so:$(IMS_DST)/libssl.so \
    $(IMS_A64)/libcryptoO.so:$(IMS_DST)/libcryptoO.so \
    $(IMS_A64)/libcrypto.so:$(IMS_DST)/libcrypto.so \
    $(IMS_A64)/libprotobuf-cpp-full-rtti.so:$(IMS_DST)/libprotobuf-cpp-full-rtti.so \
    $(IMS_A64)/libprotobuf-cpp-full.so:$(IMS_DST)/libprotobuf-cpp-full.so \
    $(IMS_A64)/libaresdns.so:$(IMS_DST)/libaresdns.so \
    $(IMS_A64)/libsecnativefeature.so:$(IMS_DST)/libsecnativefeature.so \
    $(IMS_A64)/libfloatingfeature.so:$(IMS_DST)/libfloatingfeature.so \
    $(IMS_A64)/libhardware_legacy.so:$(IMS_DST)/libhardware_legacy.so \
    $(IMS_A64)/libbase.so:$(IMS_DST)/libbase.so \
    $(IMS_A64)/libicuuc.so:$(IMS_DST)/libicuuc.so \
    $(IMS_A64)/libext2_uuid.so:$(IMS_DST)/libext2_uuid.so \
    $(IMS_A64)/libnativehelper.so:$(IMS_DST)/libnativehelper.so \
    $(IMS_A64)/libxml2.so:$(IMS_DST)/libxml2.so

# ------------------------------------------------------------------------------------
# CSC + IMS config  (/system/csc)   [WITHOUT customer.xml -> NO VoLTE at all]
# ------------------------------------------------------------------------------------
PRODUCT_COPY_FILES += \
    $(LOCAL_IMS)/proprietary/system/csc/customer.xml:$(TARGET_COPY_OUT_SYSTEM)/csc/customer.xml \
    $(LOCAL_IMS)/proprietary/system/csc/customer_cs.xml:$(TARGET_COPY_OUT_SYSTEM)/csc/customer_cs.xml \
    $(LOCAL_IMS)/proprietary/system/csc/imsupdate.json:$(TARGET_COPY_OUT_SYSTEM)/csc/imsupdate.json

# ------------------------------------------------------------------------------------
# Built from source in this repo (apps/ + overlays/)
# ------------------------------------------------------------------------------------
PRODUCT_PACKAGES += \
    HeroImsBridge \
    HeroImsConfigOverlay \
    HeroVolteAvailableOverlay \
    HeroCarrierVolteOverlay
