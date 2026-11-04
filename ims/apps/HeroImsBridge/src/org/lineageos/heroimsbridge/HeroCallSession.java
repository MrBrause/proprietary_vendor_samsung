package org.lineageos.heroimsbridge;

import android.os.Message;
import android.os.RemoteException;
import android.telephony.ims.ImsCallProfile;
import android.telephony.ims.ImsReasonInfo;
import android.telephony.ims.ImsStreamMediaProfile;
import android.telephony.ims.ImsCallSessionListener;
import android.telephony.ims.stub.ImsCallSessionImplBase;
import android.util.Log;

import com.sec.ims.volte2.IImsCallSession;
import com.sec.ims.volte2.IImsCallSessionEventListener;
import com.sec.ims.volte2.data.CallProfile;

/**
 * Bridges ONE call: AOSP ImsCallSessionImplBase  <->  Samsung IImsCallSession.
 *
 * DOWN (AOSP -> engine): accept / reject / terminate / start / hold / resume / dtmf.
 * UP   (engine -> AOSP): via IImsCallSessionEventListener registered on the engine session,
 *                        translated to AOSP ImsCallSessionListener (mListener) callbacks.
 *
 * VERIFY-IN-TREE (cheap, no flash): the exact AOSP ImsCallSessionListener method names can
 * vary slightly by platform. Confirm these against frameworks/base
 * (android/telephony/ims/ImsCallSessionListener.java) in your LOS21 tree:
 *   callSessionInitiated(ImsCallProfile), callSessionInitiatingFailed(ImsReasonInfo),
 *   callSessionProgressing(ImsStreamMediaProfile), callSessionTerminated(ImsReasonInfo),
 *   callSessionHeld(ImsCallProfile), callSessionResumed(ImsCallProfile).
 * The down-path and the engine event capture are exact (from the smali you sent).
 */
public class HeroCallSession extends ImsCallSessionImplBase {
    private static final String TAG = "HeroCallSession";

    private final SamsungEngineBridge mBridge;
    private final IImsCallSession mEngine;   // Samsung session
    private final boolean mIncoming;
    private ImsCallSessionListener mListener; // AOSP up-path (set by framework via setListener)
    private ImsCallProfile mProfile;
    // AOSP's ImsCallSession wrapper reads getState() when it takes the call; if it returns
    // the default State.INVALID, ImsManager.takeCall() rejects the session as "not alive".
    // Start in a live, in-setup state (MT call is alerting), advance on engine events.
    private volatile int mState = ImsCallSessionImplBase.State.ESTABLISHING;

    HeroCallSession(SamsungEngineBridge bridge, IImsCallSession engine, boolean incoming,
            ImsCallProfile profile) {
        mBridge = bridge;
        mEngine = engine;
        mIncoming = incoming;
        mProfile = profile;
        try { mEngine.registerSessionEventListener(mEventListener); }
        catch (RemoteException e) { Log.e(TAG, "registerSessionEventListener", e); }
    }

    /** AOSP checks this for isAlive() during takeCall(); never return INVALID for a live call. */
    @Override
    public int getState() { return mState; }

    // The framework calls this to give us the listener to post events on.
    @Override
    public void setListener(ImsCallSessionListener listener) {
        mListener = listener;
    }

    @Override
    public String getCallId() {
        try { return String.valueOf(mEngine.getCallId()); }
        catch (RemoteException e) { return null; }
    }

    @Override
    public ImsCallProfile getCallProfile() { return mProfile; }

    @Override
    public ImsCallProfile getLocalCallProfile() { return mProfile; }

    // ---- DOWN: AOSP -> engine ----

    /** MO dial. */
    @Override
    public void start(String callee, ImsCallProfile profile) {
        Log.i(TAG, "start(MO) " + callee);
        try {
            CallProfile cp = mEngine.getCallProfile();   // engine pre-made the session's profile
            if (cp == null) cp = new CallProfile();
            cp.setDialingNumber(callee);
            cp.setDirection(CallProfile.DIRECTION_MO);
            mEngine.start(callee, cp);
        } catch (RemoteException e) { Log.e(TAG, "start", e); }
    }

    /** MT answer. Pass the engine's own incoming profile back — no guessing. */
    @Override
    public void accept(int callType, ImsStreamMediaProfile profile) {
        Log.i(TAG, "accept callType=" + callType);
        try { mEngine.accept(mEngine.getCallProfile()); }
        catch (RemoteException e) { Log.e(TAG, "accept", e); }
    }

    @Override
    public void reject(int reason) {
        Log.i(TAG, "reject " + reason);
        try { mEngine.reject(reason); } catch (RemoteException e) { Log.e(TAG, "reject", e); }
    }

    @Override
    public void terminate(int reason) {
        Log.i(TAG, "terminate " + reason);
        try { mEngine.terminate(reason); } catch (RemoteException e) { Log.e(TAG, "terminate", e); }
    }

    @Override
    public void hold(ImsStreamMediaProfile profile) {
        try { mEngine.hold(null); } catch (RemoteException e) { Log.e(TAG, "hold", e); }
        // TODO: map ImsStreamMediaProfile -> com.sec.ims.volte2.data.MediaProfile if needed.
    }

    @Override
    public void resume(ImsStreamMediaProfile profile) {
        try { mEngine.resume(); } catch (RemoteException e) { Log.e(TAG, "resume", e); }
    }

    @Override
    public void sendDtmf(char c, Message result) {
        try { mEngine.startDtmf(c); mEngine.stopDtmf(); }
        catch (RemoteException e) { Log.e(TAG, "sendDtmf", e); }
    }

    // ---- UP: engine -> AOSP (Samsung session events) ----

    private final IImsCallSessionEventListener.Stub mEventListener =
            new IImsCallSessionEventListener.Stub() {
        @Override public void onEstablished(int id) {
            Log.i(TAG, "engine onEstablished -> callSessionInitiated");
            mState = ImsCallSessionImplBase.State.ESTABLISHED;
            if (mListener != null) mListener.callSessionInitiated(mProfile);
        }
        @Override public void onEnded(int reason) {
            Log.i(TAG, "engine onEnded -> callSessionTerminated");
            mState = ImsCallSessionImplBase.State.TERMINATED;
            if (mListener != null)
                mListener.callSessionTerminated(new ImsReasonInfo(ImsReasonInfo.CODE_USER_TERMINATED, 0));
        }
        @Override public void onFailure(int reason) {
            mState = ImsCallSessionImplBase.State.TERMINATED;
            if (mListener != null)
                mListener.callSessionInitiatingFailed(new ImsReasonInfo(ImsReasonInfo.CODE_UNSPECIFIED, 0));
        }
        @Override public void onHeld(boolean a, boolean b) {
            if (mListener != null) mListener.callSessionHeld(mProfile);
        }
        @Override public void onResumed(boolean a) {
            if (mListener != null) mListener.callSessionResumed(mProfile);
        }
        @Override public void onEarlyMediaStarted(int id) {
            // 183 Session Progress WITH network early media (P-Early-Media active): the far
            // network streams the ringback/announcement over RTP. Tell the framework we're
            // progressing so it opens/plays the network audio (and does NOT also play a local tone).
            Log.i(TAG, "engine onEarlyMediaStarted -> callSessionProgressing (network early media)");
            if (mListener != null) mListener.callSessionProgressing(new ImsStreamMediaProfile());
        }
        @Override public void onRingingBack() {
            // 180 Ringing WITHOUT early media (DT reports IsEarlyMedia direction 0): the caller must
            // hear a LOCALLY generated ringback tone. Move the AOSP connection to ALERTING via
            // callSessionProgressing, BUT signal audioDirection=INACTIVE. A default ImsStreamMediaProfile
            // has mAudioDirection=DIRECTION_SEND_RECEIVE (3), which the framework reads as "active early
            // media is flowing" -> it then waits for NETWORK ringback audio and plays NO local tone
            // (= silence, since no early-media RTP exists). INACTIVE tells it there is no network audio,
            // so it generates the local ringback itself.
            Log.i(TAG, "engine onRingingBack -> callSessionProgressing (local ringback, INACTIVE)");
            if (mListener != null) {
                ImsStreamMediaProfile mp = new ImsStreamMediaProfile();
                mp.mAudioDirection = ImsStreamMediaProfile.DIRECTION_INACTIVE; // 0 = no early media
                mListener.callSessionProgressing(mp);
            }
        }
        // --- the rest: not needed for basic voice; no-op for now ---
        @Override public void onCalling() {}
        @Override public void onTrying() {}
        @Override public void onError(int a, String b, int c) {}
        @Override public void onForwarded() {}
        @Override public void onStopAlertTone() {}
        @Override public void onSwitched(int a) {}
        @Override public void onProfileUpdated(com.sec.ims.volte2.data.MediaProfile a,
                com.sec.ims.volte2.data.MediaProfile b) {}
        @Override public void onSessionUpdateRequested(int a, byte[] b) {}
        @Override public void onConferenceEstablished() {}
        @Override public void onConfParticipantHeld(int a, boolean b) {}
        @Override public void onConfParticipantResumed(int a, boolean b) {}
        @Override public void onParticipantAdded(int a) {}
        @Override public void onParticipantRemoved(int a) {}
        @Override public void onParticipantUpdated(int a, String[] b, int[] c) {}
        @Override public void onEPdgUnavailable(int a) {}
        @Override public void onEpdgStateChanged() {}
        @Override public void onTtyTextRequest(int a, byte[] b) {}
        @Override public void onUssdReceived(int a, int b, byte[] c) {}
        @Override public void onUssdResponse(int a) {}
    };
}
