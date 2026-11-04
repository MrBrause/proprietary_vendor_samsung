package org.lineageos.heroimsbridge;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.RemoteException;
import android.os.ServiceManager;
import android.telephony.ims.ImsCallProfile;
import android.telephony.ims.ImsReasonInfo;
import android.telephony.ims.feature.MmTelFeature.MmTelCapabilities;
import android.telephony.ims.stub.ImsCallSessionImplBase;
import android.telephony.ims.stub.ImsRegistrationImplBase;
import android.util.Log;
import android.util.SparseArray;

import com.sec.ims.IImsService;
import com.sec.ims.IImsRegistrationListener;
import com.sec.ims.ImsRegistration;
import com.sec.ims.ImsRegistrationError;
import com.sec.ims.volte2.IVolteService;
import com.sec.ims.volte2.IImsCallSession;
import com.sec.ims.volte2.IImsCallEventListener;
import com.sec.ims.volte2.data.CallProfile;
import com.sec.ims.volte2.data.ImsCallInfo;

/**
 * THE SEAM — Samsung engine (com.sec.imsservice) <-> AOSP.
 * Registration via "secims"/IImsService; calls via VolteService2/IVolteService.
 */
public class SamsungEngineBridge {
    private static final String TAG = "HeroBridge";
    private static final String SECIMS = "secims";
    private static final int SLOT = 0;
    // Verified against this engine's imsmanager.jar: there is no CALL_TYPE_VOICE; the voice/audio
    // call type is CALL_TYPE_AUDIO = 1. IVolteService.createCallProfile(int serviceType, int callType)
    // -> the engine only setCallType(callType) and ignores serviceType; phoneId is implicit (single-SIM).
    private static final int SERVICE_TYPE_DEFAULT = 0;
    private static final int CALL_TYPE_AUDIO = 1;
    private static final ComponentName VOLTE_SVC = new ComponentName(
            "com.sec.imsservice", "com.sec.internal.ims.imsservice.VolteService2");

    private final Context mContext;
    private final Handler mH = new Handler(Looper.getMainLooper());
    private final SparseArray<HeroMmTelFeature> mMmTel = new SparseArray<>();
    private final SparseArray<ImsRegistrationImplBase> mReg = new SparseArray<>();

    private IImsService mImsService;
    private IVolteService mVolte;
    private volatile boolean mVolteRegistered = false;
    // User "4G Calls" toggle. The engine's mmtel switch is force-held by the CSC (EnableVoLTE=true) and
    // re-asserts on any config reload, so we honor the toggle HERE: when off we stop reporting the VOICE
    // capability to AOSP (-> outgoing calls use CS, the roaming case) without churning the engine/PDN.
    // Default true; AOSP re-applies the saved setting via changeEnabledCapabilities after boot.
    private volatile boolean mVoiceUserEnabled = true;

    SamsungEngineBridge(Context ctx) { mContext = ctx; }

    void start() {
        try { connectImsService(); } catch (Throwable t) { Log.e(TAG, "connectImsService failed", t); }
        try { bindVolteService(); } catch (Throwable t) { Log.e(TAG, "bindVolteService failed", t); }
    }

    void stop() {
        try { if (mImsService != null) mImsService.unregisterImsRegistrationListenerForSlot(mRegListener, SLOT); } catch (Exception ignore) {}
        try { if (mVolte != null) mVolte.deregisterForCallStateEventForSlot(SLOT, mCallListener); } catch (Exception ignore) {}
        try { mContext.unbindService(mVolteConn); } catch (Exception ignore) {}
    }

    void attachMmTel(int s, HeroMmTelFeature f) { mMmTel.put(s, f); }
    void attachRegistration(int s, ImsRegistrationImplBase r) { mReg.put(s, r); }
    void onAospEnableIms(int s) {}
    void onAospDisableIms(int s) {}

    /**
     * Honor the user "4G Calls"/VoLTE toggle: tell the engine to enable/disable VoLTE. The engine then
     * (de)registers MMTEL and fires the registration listener, which re-publishes the AOSP VOICE cap.
     */
    void setVolteEnabled(boolean on) {
        // Soft-disable: gate the reported VOICE capability only. When off, AOSP routes OUTGOING calls over
        // CS; INCOMING still arrives over VoLTE and is presented normally (the engine stays registered).
        // We deliberately do NOT try to deregister the engine:
        //  - flipping the mmtel service switch is re-forced by the CSC (EnableVoLTE=true) within seconds,
        //  - suspendRegister() only pauses future re-registration (IRAT), it does NOT tear down the live
        //    session -> the network keeps sending VoLTE but the call is no longer presented => LOST call.
        // So soft-disable is the safe, correct behavior (and the sensible roaming default: force outgoing
        // to classic, never miss an incoming call).
        mVoiceUserEnabled = on;
        // Persist the choice for the reboot-based HARD disable: device init bind-mounts the VoLTE-off CSC
        // (/system/csc/customer_cs.xml) over customer.xml when this prop is "1", so after a reboot the
        // engine never registers IMS and INCOMING also falls back to CS. Needs a property_contexts entry
        // + set_prop sepolicy (trivial on permissive). Harmless if the prop/init wiring isn't present.
        try {
            android.os.SystemProperties.set("persist.sys.heroims.cs_only", on ? "0" : "1");
        } catch (Throwable t) {
            Log.w(TAG, "set persist.sys.heroims.cs_only failed (needs set_prop sepolicy): " + t);
        }
        Log.i(TAG, "user 4G-Calls -> " + on + " (soft now: gate VOICE cap; hard on reboot via cs_only prop)");
        syncCapabilitiesToAosp(SLOT);
    }

    // ---------- registration (secims / IImsService) ----------

    private void connectImsService() {
        IBinder b = ServiceManager.getService(SECIMS);
        if (b == null) { mH.postDelayed(this::connectImsService, 1000); return; } // engine not up yet
        mImsService = IImsService.Stub.asInterface(b);
        try {
            mImsService.registerImsRegistrationListenerForSlot(mRegListener, SLOT);
            ImsRegistration[] cur = mImsService.getRegistrationInfoByPhoneId(SLOT);
            updateRegistration(SLOT, cur != null && cur.length > 0,
                    ImsRegistrationImplBase.REGISTRATION_TECH_LTE);
            Log.i(TAG, "registration listener attached on secims");
        } catch (RemoteException e) {
            Log.e(TAG, "register reg listener failed", e);
            mH.postDelayed(this::connectImsService, 2000);
        }
    }

    private final IImsRegistrationListener.Stub mRegListener = new IImsRegistrationListener.Stub() {
        @Override public void onRegistered(ImsRegistration reg) {
            updateRegistration(SLOT, true, ImsRegistrationImplBase.REGISTRATION_TECH_LTE);
        }
        @Override public void onDeregistered(ImsRegistration reg, ImsRegistrationError err) {
            updateRegistration(SLOT, false, ImsRegistrationImplBase.REGISTRATION_TECH_LTE);
        }
    };

    void updateRegistration(int slot, boolean registered, int tech) {
        mVolteRegistered = registered;
        ImsRegistrationImplBase reg = mReg.get(slot);
        if (reg != null) {
            if (registered) reg.onRegistered(tech);
            else reg.onDeregistered(new ImsReasonInfo(ImsReasonInfo.CODE_UNSPECIFIED, 0, ""));
        }
        syncCapabilitiesToAosp(slot);
    }

    void syncCapabilitiesToAosp(int slot) {
        HeroMmTelFeature m = mMmTel.get(slot);
        if (m == null) return;
        MmTelCapabilities caps = new MmTelCapabilities();
        if (mVolteRegistered && mVoiceUserEnabled) caps.addCapabilities(MmTelCapabilities.CAPABILITY_TYPE_VOICE);
        m.publishCapabilities(caps);
    }

    /**
     * STATIC capability configuration asked by AOSP via MmTelFeature.queryCapabilityConfiguration.
     * This is reached by ImsMmTelManager.isSupported(CAPABILITY_TYPE_VOICE, WWAN), which Settings'
     * Enhanced4gBasePreferenceController uses as "isEnabledByPlatform" to decide whether to SHOW the
     * "4G Calls" toggle at all. It must report whether the device CAN do VoLTE, NOT whether it is
     * registered right now. Report VOICE as supported unconditionally, so the toggle stays visible
     * even while the engine is de-registered (e.g. cs_only=1 / user turned VoLTE off) — otherwise the
     * toggle disappears and the user can never turn VoLTE back on (chicken-and-egg).
     *
     * LIVE availability (is VoLTE usable right NOW, which Telecom uses to route a call CS vs IMS) is a
     * DIFFERENT signal, published via notifyCapabilitiesStatusChanged in syncCapabilitiesToAosp(), and
     * stays correctly gated on mVolteRegistered && mVoiceUserEnabled.
     */
    boolean isCapabilityAvailable(int slot, int capability, int radioTech) {
        return capability == MmTelCapabilities.CAPABILITY_TYPE_VOICE;
    }

    // ---------- calls (VolteService2 / IVolteService) ----------

    private void bindVolteService() {
        try {
            boolean ok = mContext.bindService(new Intent().setComponent(VOLTE_SVC),
                    mVolteConn, Context.BIND_AUTO_CREATE);
            Log.i(TAG, "bindService VolteService2 -> " + ok);
        } catch (Throwable t) {
            // e.g. SecurityException if uid/exported mismatch; don't take down the ImsService.
            Log.e(TAG, "bindService VolteService2 threw (call path unavailable, registration still live)", t);
        }
    }

    private final ServiceConnection mVolteConn = new ServiceConnection() {
        @Override public void onServiceConnected(ComponentName n, IBinder b) {
            mVolte = IVolteService.Stub.asInterface(b);
            try { mVolte.registerForCallStateEventForSlot(SLOT, mCallListener); Log.i(TAG, "call listener attached"); }
            catch (RemoteException e) { Log.e(TAG, "register call listener failed", e); }
        }
        @Override public void onServiceDisconnected(ComponentName n) { mVolte = null; }
    };

    /** MO call. */
    ImsCallSessionImplBase createOutgoingCallSession(int slot, ImsCallProfile aospProfile) {
        if (mVolte == null) { Log.w(TAG, "createOutgoingCallSession: VolteService not bound"); return null; }
        try {
            CallProfile cp = mVolte.createCallProfile(SERVICE_TYPE_DEFAULT, CALL_TYPE_AUDIO); // (serviceType, callType)
            IImsCallSession s = mVolte.createSession(cp);
            return new HeroCallSession(this, s, /*incoming*/ false, aospProfile);
        } catch (RemoteException e) { Log.e(TAG, "createOutgoingCallSession", e); return null; }
    }

    /** Service-level call events from the engine. onIncomingCall is the ring trigger. */
    private final IImsCallEventListener.Stub mCallListener = new IImsCallEventListener.Stub() {
        @Override public void onIncomingCall(ImsCallInfo info, String s) {
            // CRITICAL: this is a synchronous binder callback FROM the engine
            // (com.sec.imsservice). Any exception that escapes here is marshaled
            // back across the binder and crashes the engine process. So nothing
            // may throw out of this method - catch Throwable, never just RemoteException.
            try {
                Log.i(TAG, "engine onIncomingCall s=" + s);
                HeroMmTelFeature m = mMmTel.get(SLOT);
                if (m == null || mVolte == null) { Log.w(TAG, "no MmTel/Volte for incoming"); return; }
                // The String arg is the pending-session key the engine just created.
                IImsCallSession es = mVolte.getPendingSession(s);
                if (es == null) { Log.w(TAG, "getPendingSession(" + s + ") null"); return; }
                ImsCallProfile aosp = m.createCallProfileForIncoming();
                // Caller ID: the engine passes the originating number as `s`. AOSP's
                // ImsPhoneConnection reads EXTRA_OI for the number and EXTRA_OIR for its
                // presentation; without them the incoming VoLTE call shows no number. Strip any
                // tel:/sip: scheme + @domain, and mark presentation allowed so the number displays.
                if (s != null && !s.isEmpty()) {
                    String oi = s;
                    if (oi.startsWith("tel:") || oi.startsWith("sip:")) oi = oi.substring(4);
                    int at = oi.indexOf('@');
                    if (at > 0) oi = oi.substring(0, at);
                    aosp.setCallExtra(ImsCallProfile.EXTRA_OI, oi);
                    aosp.setCallExtraInt(ImsCallProfile.EXTRA_OIR,
                            ImsCallProfile.OIR_PRESENTATION_NOT_RESTRICTED);
                }
                HeroCallSession hs = new HeroCallSession(SamsungEngineBridge.this, es, true, aosp);
                m.deliverIncomingCall(hs, new Bundle());
            } catch (Throwable t) {
                // Most likely MmTelFeature.notifyIncomingCall() throwing
                // IllegalStateException("Session is not available.") because AOSP
                // has not set the MMTEL listener yet (feature not READY/connected).
                // Swallow it so the Samsung engine is never taken down by us.
                Log.e(TAG, "onIncomingCall failed (engine protected from crash)", t);
            }
        }
        @Override public void onIncomingPreAlerting(ImsCallInfo info, String s) {}
        @Override public void onCallStarted(ImsCallInfo info) {}
        @Override public void onCallTrying(ImsCallInfo info) {}
        @Override public void onCallRinging(ImsCallInfo info) {}
        @Override public void onCallRingingBack(ImsCallInfo info) {}
        @Override public void onCallEstablished(ImsCallInfo info) {}
        @Override public void onCallEnded(ImsCallInfo info, int reason) {}
        @Override public void onCallHeld(ImsCallInfo info, boolean a, boolean b) {}
        @Override public void onCallResumed(ImsCallInfo info) {}
        @Override public void onCallModified(ImsCallInfo info) {}
        @Override public void onCallModifyRequested(ImsCallInfo info, int a) {}
        @Override public void onConferenceParticipantAdded(ImsCallInfo info, String p) {}
        @Override public void onConferenceParticipantRemoved(ImsCallInfo info, String p) {}
        @Override public void onDedicatedBearerEvent(ImsCallInfo info, int a, int b) {}
        @Override public void onRtpLossRateNoti(int a, float b, float c, int d) {}
        @Override public void onVideoAvailable(ImsCallInfo info) {}
        @Override public void onVideoHeld(ImsCallInfo info) {}
        @Override public void onVideoResumed(ImsCallInfo info) {}
    };
}
