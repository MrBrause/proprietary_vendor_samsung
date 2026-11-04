package org.lineageos.heroimsbridge;

import android.os.Bundle;
import android.telephony.ims.ImsService;
import android.telephony.ims.feature.ImsFeature;
import android.telephony.ims.feature.MmTelFeature;
import android.telephony.ims.stub.ImsConfigImplBase;
import android.telephony.ims.stub.ImsFeatureConfiguration;
import android.telephony.ims.stub.ImsRegistrationImplBase;
import android.util.Log;
import android.util.SparseArray;

/**
 * AOSP-facing ImsService. ImsResolver binds this (the device framework overlay points
 * config_ims_mmtel_package here). We advertise MMTEL and hand AOSP a MmTelFeature,
 * an ImsRegistration, and an ImsConfig per slot. All real IMS work is delegated to
 * Samsung's com.sec.imsservice through {@link SamsungEngineBridge}.
 *
 * Single-SIM herolte => slotId 0 only.
 */
public class HeroImsService extends ImsService {
    private static final String TAG = "HeroImsService";

    private final SparseArray<HeroMmTelFeature> mMmTel = new SparseArray<>();
    private final SparseArray<ImsRegistrationImplBase> mReg = new SparseArray<>();
    private final SparseArray<ImsConfigImplBase> mConfig = new SparseArray<>();
    private SamsungEngineBridge mBridge;

    @Override
    public void onCreate() {
        super.onCreate();
        Log.i(TAG, "onCreate");
        mBridge = new SamsungEngineBridge(getApplicationContext());
        try { mBridge.start(); } catch (Throwable t) { Log.e(TAG, "bridge start failed", t); }
    }

    @Override
    public void onDestroy() {
        if (mBridge != null) mBridge.stop();
        super.onDestroy();
    }

    /** Tell AOSP which features we provide. herolte is single-SIM => slot 0. */
    @Override
    public ImsFeatureConfiguration querySupportedImsFeatures() {
        return new ImsFeatureConfiguration.Builder()
                .addFeature(0 /*slotId*/, ImsFeature.FEATURE_MMTEL)
                // .addFeature(0, ImsFeature.FEATURE_EMERGENCY_MMTEL) // add once stable
                .build();
    }

    @Override
    public MmTelFeature createMmTelFeature(int slotId) {
        Log.i(TAG, "createMmTelFeature slot=" + slotId);
        HeroMmTelFeature f = new HeroMmTelFeature(this, slotId, mBridge);
        mMmTel.put(slotId, f);
        mBridge.attachMmTel(slotId, f);
        // AOSP does NOT call onFeatureReady() for us on this build, so the feature
        // would stay STATE_UNAVAILABLE forever -> telephony logs "no ImsService
        // available" and MmTelFeature.notifyIncomingCall() throws
        // "Session is not available." (which used to crash the engine).
        // Mark the feature READY now so the framework completes the MMTEL
        // connection and sets the feature listener. Real VoLTE availability stays
        // gated by the VOICE capability we publish from the engine's registration.
        try {
            f.setFeatureState(ImsFeature.STATE_READY);
            Log.i(TAG, "MmTel forced STATE_READY slot=" + slotId);
        } catch (Throwable t) {
            Log.e(TAG, "setFeatureState(READY) failed", t);
        }
        mBridge.syncCapabilitiesToAosp(slotId);
        return f;
    }

    @Override
    public ImsRegistrationImplBase getRegistration(int slotId) {
        ImsRegistrationImplBase r = mReg.get(slotId);
        if (r == null) {
            r = new ImsRegistrationImplBase();
            mReg.put(slotId, r);
            mBridge.attachRegistration(slotId, r);
        }
        return r;
    }

    @Override
    public ImsConfigImplBase getConfig(int slotId) {
        ImsConfigImplBase c = mConfig.get(slotId);
        if (c == null) {
            c = new ImsConfigImplBase(); // defaults are fine; engine owns real config
            mConfig.put(slotId, c);
        }
        return c;
    }

    @Override
    public void enableIms(int slotId) {
        Log.i(TAG, "enableIms slot=" + slotId);
        mBridge.onAospEnableIms(slotId);
    }

    @Override
    public void disableIms(int slotId) {
        Log.i(TAG, "disableIms slot=" + slotId);
        mBridge.onAospDisableIms(slotId);
    }
}
