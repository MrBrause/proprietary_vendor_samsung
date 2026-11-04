# HeroImsBridge — integration (herolte / LOS21)

AOSP ImsService that relays to the Samsung engine (com.sec.imsservice) so the dialer rings and
routes VoLTE. The engine does all SIP/IPsec/AKA and is already REGISTERED; this is just the
AOSP-facing ImsService that ImsResolver binds (config_ims_mmtel_package -> org.lineageos.heroimsbridge,
which the herolte overlay already sets).

## AIDL reconciled against THIS engine build (imsmanager.jar, Oct 2026 f0ef8e45)
- IImsService.registerImsRegistrationListenerForSlot(IImsRegistrationListener,int) / getRegistrationInfoByPhoneId(int) — OK
- IImsRegistrationListener.onRegistered(ImsRegistration) / onDeregistered(ImsRegistration,ImsRegistrationError) — OK
- IVolteService.registerForCallStateEventForSlot(int,IImsCallEventListener) / getPendingSession(String) / createSession(CallProfile) — OK
- IImsCallEventListener (19 methods) and IImsCallSessionEventListener (26 methods) — Stubs match EXACTLY
- IImsCallSession down-path (accept/reject/terminate/start/hold/resume/startDtmf/stopDtmf/getCallId/getCallProfile/registerSessionEventListener) — OK
- FIXED vs the old source: createCallProfile is (int serviceType, int callType); there is no CALL_TYPE_VOICE,
  the voice type is CALL_TYPE_AUDIO = 1. Now calls createCallProfile(0, 1). (MO path only.)
- getPendingSession IGNORES its String arg and returns the engine's single mIncomingCallSession, so the
  incoming path is robust regardless of the key the engine passes. (Former soft spot: resolved.)

## Install / wire
1. Drop this dir at packages/apps/HeroImsBridge/.
2. PRODUCT_PACKAGES += HeroImsBridge   (in device/samsung/herolte/*.mk)
3. privapp-permissions-org.lineageos.heroimsbridge.xml -> /system/etc/permissions/ (PRODUCT_COPY_FILES,
   or bake into system_ext/etc/permissions).
4. config_ims_mmtel_package is ALREADY = org.lineageos.heroimsbridge in the Telephony overlay. Leave it.
   If you set a runtime carrier override earlier, clear it: adb shell cmd phone cc clear-values -s 0
5. imsmanager / imscoremanager / secimshttpclient shared-lib jars: you currently push these post-flash.
   HeroImsBridge <uses-library imsmanager> needs imsmanager + its <library> registration present when the
   app is scanned. For a clean flash, bake imsmanager.jar + its /system(_ext)/etc/permissions <library>
   entry into the ROM (same as the engine needs). If that's awkward, use the static_libs variant in
   Android.bp (bundles the AIDL into the APK; no runtime shared-lib dependency).

## Quick on-device test WITHOUT a full build (fastest validation)
HeroImsBridge must be platform-signed; to try it before baking into the tree, sign the built APK with your
platform key and push it:
  adb root; adb remount
  adb push HeroImsBridge.apk /system/priv-app/HeroImsBridge/HeroImsBridge.apk
  adb push privapp-permissions-org.lineageos.heroimsbridge.xml /system/etc/permissions/
  adb reboot
(Ensure imsmanager.jar + its <library> registration are pushed too, as you already do.)

## Expect in logcat
  adb logcat -b all | grep -iE 'ImsResolver|HeroIms|HeroBridge|HeroMmTel|HeroCallSession|notifyIncomingCall|no ImsService'
- ImsResolver BINDS org.lineageos.heroimsbridge; HeroImsService onCreate; createMmTelFeature -> STATE_READY
- HeroBridge registration listener attached on secims; isImsRegistered true after engine registers; VoLTE icon
- incoming call -> "HeroBridge onIncomingCall" -> "HeroMmTel notifyIncomingCall" -> phone RINGS with accept UI
- answer -> engine.accept -> two-way audio
