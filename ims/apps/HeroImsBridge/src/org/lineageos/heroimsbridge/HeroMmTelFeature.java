package org.lineageos.heroimsbridge;

import android.os.Bundle;
import android.telephony.ims.ImsCallProfile;
import android.telephony.ims.feature.CapabilityChangeRequest;
import android.telephony.ims.feature.MmTelFeature;
import android.telephony.ims.stub.ImsCallSessionImplBase;
import android.telephony.ims.stub.ImsRegistrationImplBase;
import android.util.Log;

/**
 * MmTelFeature AOSP talks to for VoLTE:
 *  - READY when the engine is alive,
 *  - publishes VoLTE capability when the engine reports mmtel registered,
 *  - MO calls via createCallSession -> bridge,
 *  - incoming calls surfaced by the bridge via deliverIncomingCall -> notifyIncomingCall.
 */
public class HeroMmTelFeature extends MmTelFeature {
    private static final String TAG = "HeroMmTel";

    private final HeroImsService mService;
    private final int mSlotId;
    private final SamsungEngineBridge mBridge;

    HeroMmTelFeature(HeroImsService svc, int slotId, SamsungEngineBridge bridge) {
        mService = svc; mSlotId = slotId; mBridge = bridge;
    }

    @Override
    public void onFeatureReady() {
        Log.i(TAG, "onFeatureReady slot=" + mSlotId);
        setFeatureState(STATE_READY);
        mBridge.syncCapabilitiesToAosp(mSlotId);
    }

    @Override public void onFeatureRemoved() {}

    @Override
    public boolean queryCapabilityConfiguration(int capability, int radioTech) {
        return mBridge.isCapabilityAvailable(mSlotId, capability, radioTech);
    }

    /**
     * The user "4G Calls" (VoLTE) toggle drives this. Propagate a VOICE enable/disable to the Samsung
     * engine (IImsService.enableVoLteByPhoneId); the engine then (de)registers MMTEL and our registration
     * listener re-publishes the VOICE capability accordingly. Disabling lets calls fall back to CS where
     * it exists (e.g. roaming). Other capabilities (video/UT) are left to the engine.
     */
    @Override
    public void changeEnabledCapabilities(CapabilityChangeRequest request, CapabilityCallbackProxy c) {
        if (request == null) return;
        // The "4G Calls" (VoLTE) toggle = VOICE over the CELLULAR techs (LTE / NR). The framework
        // ALSO pushes VOICE enable/disable for IWLAN (VoWiFi) and CROSS_SIM in the same request -
        // e.g. at boot it enables VOICE on LTE+NR but disables VOICE on IWLAN+CROSS_SIM because WFC
        // is off. Those are NOT the VoLTE toggle; reacting to them (the trailing IWLAN/CROSS_SIM
        // DISABLE) is what wrongly latched cs_only=1 after a reboot. So only cellular VOICE drives
        // the VoLTE enable/disable + cs_only prop; ignore IWLAN/CROSS_SIM here (VoWiFi is a separate
        // milestone with its own capability).
        for (CapabilityChangeRequest.CapabilityPair p : request.getCapabilitiesToEnable()) {
            if (p.getCapability() == MmTelCapabilities.CAPABILITY_TYPE_VOICE && isCellularTech(p.getRadioTech())) {
                Log.i(TAG, "changeEnabledCapabilities: ENABLE voice (radioTech=" + p.getRadioTech() + ")");
                mBridge.setVolteEnabled(true);
            }
        }
        for (CapabilityChangeRequest.CapabilityPair p : request.getCapabilitiesToDisable()) {
            if (p.getCapability() == MmTelCapabilities.CAPABILITY_TYPE_VOICE && isCellularTech(p.getRadioTech())) {
                Log.i(TAG, "changeEnabledCapabilities: DISABLE voice (radioTech=" + p.getRadioTech() + ")");
                mBridge.setVolteEnabled(false);
            }
        }
    }

    /** VoLTE lives on the cellular radio techs. IWLAN = VoWiFi, CROSS_SIM = cross-SIM calling;
     *  their VOICE enable/disable reflects WFC/cross-sim state, not the "4G Calls" toggle. */
    private static boolean isCellularTech(int radioTech) {
        return radioTech == ImsRegistrationImplBase.REGISTRATION_TECH_LTE
            || radioTech == ImsRegistrationImplBase.REGISTRATION_TECH_NR;
    }

    /** MO call. */
    @Override
    public ImsCallSessionImplBase createCallSession(ImsCallProfile profile) {
        Log.i(TAG, "createCallSession (MO)");
        return mBridge.createOutgoingCallSession(mSlotId, profile);
    }

    /**
     * MO entry point. The framework (ImsManager.createCallProfile <- ImsPhoneCallTracker.dialInternal)
     * calls this to build the AOSP ImsCallProfile for a new outgoing call. The base MmTelFeature
     * implementation returns null, which makes AOSP NPE on profile.setCallExtraInt(...) and crash the
     * com.android.phone process on every dial ("4G vanishes / thrown back to the UI"). Return a real,
     * minimal profile; AOSP fills in its own extras, then calls createCallSession() above.
     */
    @Override
    public ImsCallProfile createCallProfile(int callSessionType, int callType) {
        Log.i(TAG, "createCallProfile sessionType=" + callSessionType + " callType=" + callType);
        return new ImsCallProfile(callSessionType, callType);
    }

    // ---- helpers the bridge calls ----

    ImsCallProfile createCallProfileForIncoming() {
        // voice MMTEL profile for the incoming call UI
        return createCallProfile(ImsCallProfile.SERVICE_TYPE_NORMAL, ImsCallProfile.CALL_TYPE_VOICE);
    }

    void deliverIncomingCall(ImsCallSessionImplBase session, Bundle extras) {
        // A14 correlates the delivered session with AOSP's wrapper by callId, so use the
        // 3-arg form with the session's own id. Falls back to the 2-arg form if no id.
        String callId = session.getCallId();
        Log.i(TAG, "notifyIncomingCall callId=" + callId);
        if (callId != null && !callId.isEmpty()) {
            notifyIncomingCall(session, callId, extras);
        } else {
            notifyIncomingCall(session, extras);
        }
    }

    void publishCapabilities(MmTelCapabilities caps) {
        Log.i(TAG, "notifyCapabilitiesStatusChanged " + caps);
        notifyCapabilitiesStatusChanged(caps);
    }
}
