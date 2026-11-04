# HeroImsBridge — AOSP ImsService shim for Samsung com.sec.imsservice (herolte / LOS21)

Makes LineageOS telephony see the Samsung IMS engine so the dialer rings and routes VoLTE.
The engine does all SIP/IPsec/AKA and is REGISTERED; this module is the AOSP ImsService
that AOSP binds and that relays to the engine.

## Status — registration DONE, calls IMPLEMENTED (needs a build + a couple of in-tree checks)
- `HeroImsService` / `HeroMmTelFeature`: advertise MMTEL, go READY, publish VoLTE capability.
- `SamsungEngineBridge`:
  - REGISTRATION: `ServiceManager.getService("secims")` -> `IImsService` ->
    `registerImsRegistrationListenerForSlot` -> mirrors onRegistered/onDeregistered to AOSP.
  - CALLS: binds `VolteService2` -> `IVolteService` ->
    `registerForCallStateEventForSlot(0, IImsCallEventListener)`;
    `onIncomingCall(ImsCallInfo, String s)` -> `getPendingSession(s)` -> wrap -> notifyIncomingCall.
  - MO: `createCallProfile` + `createSession` on IVolteService.
- `HeroCallSession`: ImsCallSessionImplBase <-> IImsCallSession. accept(=engine.accept(its own
  profile)), reject/terminate/hold/resume/dtmf down; engine IImsCallSessionEventListener up
  (onEstablished->callSessionInitiated, onEnded->callSessionTerminated, ...).

## Build-time assumptions to confirm (cheap: grep the tree, no flash)
1. AOSP `ImsCallSessionListener` method names (frameworks/base android/telephony/ims/
   ImsCallSessionListener.java): callSessionInitiated/InitiatingFailed/Progressing/Terminated/
   Held/Resumed. Adjust HeroCallSession if your tree differs.
2. `CALL_TYPE_VOICE = 1` in SamsungEngineBridge — confirm Samsung's voice call-type constant
   (grep the engine for createCallProfile callers / a CallProfile CALL_TYPE_* enum).
3. `onIncomingCall`'s String `s` is assumed to be the `getPendingSession(String)` key. If instead
   it's the number and the session is fetched by id, use `getSessionByCallId(info.getCallId())`
   (needs ImsCallInfo getters — send ImsCallInfo.smali if so).
These are the only soft spots; everything else is from the smali you sent.

## ROM wiring
1. `packages/apps/HeroImsBridge/`.
2. `PRODUCT_PACKAGES += HeroImsBridge`.
3. Samsung jar(s) at `prebuilt/imsmanager.jar` (+ whatever holds com.sec.ims.volte2.* and
   com.sec.ims.volte2.data.* — the `./imgr` jar you found). See Android.bp `secims-prebuilt`.
   These compile the bridge AND must match the engine's classes for Binder marshalling.
4. Framework overlay: `config_ims_mmtel_package = org.lineageos.heroimsbridge`.
5. Keep `/system/etc/permissions/android.hardware.telephony.ims.xml`.
6. Platform-signed + privileged; install to /system/priv-app/.

## Test
```
adb shell logcat -b all -d | grep -iE 'ImsResolver|HeroIms|HeroBridge|isImsRegistered|notifyIncomingCall'
```
Expect: ImsResolver BINDS org.lineageos.heroimsbridge, feature READY, isImsRegistered=true after the
engine registers, VoLTE icon up; then an incoming call -> `HeroBridge onIncomingCall` ->
`notifyIncomingCall` -> phone RINGS with accept UI. Answer -> engine.accept -> audio.
```
