import logging
import threading
from utils.handler import logger
from utils.handler import run_ffmpeg
from config import SAFE_MODEL_DIR
from config import TEMP_DIR
from utils.handler import cleanup_files
from concurrent.futures import TimeoutError as FuturesTimeoutError
import os
import numpy as np
import noisereduce as nr
import soundfile as sf
import shutil

_df_model = None
_df_state = None
_df_sr    = None
_df_lock  = threading.Lock()

# ─── Noice reduction hanlders ────────────────────────────────────────────────────────
try:
    # Patch get_commit_hash BEFORE importing df.enhance so any import-time
    # call is also neutralised.
    import df.utils as _df_utils_pre
    _df_utils_pre.get_commit_hash = lambda: ""

    from df.enhance import enhance, init_df
    from df import config as df_config
    import torch

    DEEPFILTER_AVAILABLE = True
    logging.getLogger(__name__).info("DeepFilterNet detected and available.")

except ImportError:
    DEEPFILTER_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "DeepFilterNet (df package) not installed — 'strong' preset will fall back to "
        "SpectralNR + RNNoise only. Install with: pip install deepfilternet"
    )
    

def _get_df_model():
    global _df_model, _df_state, _df_sr
    if not DEEPFILTER_AVAILABLE:
        raise RuntimeError("DeepFilterNet is not installed. Run: pip install deepfilternet")
    with _df_lock:
        if _df_model is None:
            logger.info("[DeepFilter] Loading model (first use)...")
            # SafePopen is permanently active so any git calls inside
            # init_df() are safely swallowed without raising WinError 2.
            #
            # init_df() return signature differs across df versions:
            #   older : (model, state, sample_rate_int)
            #   newer : (model, state, model_name_str)  ← DeepFilterNet3+
            #
            # Never rely on the third element for SR. Always read it from
            # df_state.sr which is set during init and is always an integer.
            _df_model, _df_state, _ = init_df()
            _df_sr = int(_df_state.sr())
            logger.info(f"[DeepFilter] Model ready. Native SR={_df_sr}Hz")
    return _df_model, _df_state, _df_sr

# ==============================
# PIPELINE STEPS
# ==============================

def step1_to_mono_wav(input_path: str, output_path: str):
    """
    Convert any input → 48kHz mono 16-bit PCM WAV.
    Pure format normalisation — no filtering, preserves original signal.
    48kHz is the native SR for both DeepFilterNet and RNNoise — no
    resampling penalty occurs in later steps.
    """
    command = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=mono",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", output_path
    ]
    run_ffmpeg(command, "Step1-ToMonoWAV")
    
    
    
def _find_noise_sample(data: np.ndarray, rate: int) -> np.ndarray:
    """
    Find the quietest 500ms window in the file for use as noise reference.
    Scans the entire signal with 100ms hops — far more reliable than using
    the file start, where the speaker may already be talking.
    """
    sample_len = int(rate * 0.5)
    if len(data) < sample_len * 2:
        return data[max(0, len(data) - int(rate * 0.3)):]

    hop      = int(rate * 0.1)
    best_rms = float("inf")
    best_seg = data[-sample_len:]

    for start in range(0, len(data) - sample_len, hop):
        seg = data[start : start + sample_len]
        rms = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))
        if rms < best_rms:
            best_rms = rms
            best_seg = seg

    logger.info(f"[NoiseProfile] Quietest window RMS={best_rms:.6f}")
    return best_seg
    
    
def step2_spectral_denoise(input_path: str, output_path: str, profile: dict):
    """
    Spectral noise subtraction via noisereduce.

    Runs first in all presets to eliminate the stationary noise floor
    (HVAC hum, electrical hiss, steady-state broadband noise). Clearing
    this before neural models run means DeepFilterNet and RNNoise focus
    only on complex/non-stationary noise.

    Pass behaviour:
      Pass 1: full-resolution STFT (n_fft=2048) against quietest window
      Pass 2 (extreme only): finer STFT (n_fft=1024) against residual noise
                              re-estimated from the pass-1 output

    blend_original: fraction of dry signal mixed back — the single most
    important safeguard against over-processing. Guarantees natural voice
    timbre regardless of how aggressive the NR parameters are.
    """
    data, rate = sf.read(input_path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)

    dry          = data.copy()
    noise_sample = _find_noise_sample(data, rate)
    passes       = profile["passes"]
    prop         = profile["prop_decrease"]
    blend        = profile["blend_original"]

    logger.info(f"[Step2] passes={passes} prop_decrease={prop} blend_original={blend}")

    current = data
    for p in range(1, passes + 1):
        logger.info(f"[Step2] Spectral NR pass {p}/{passes}")

        if p == 1:
            noise_ref   = noise_sample
            n_fft       = 2048
            win_length  = 2048
            hop_length  = 512
            time_const  = 2.0
            freq_smooth = 150
            time_smooth = 80
        else:
            # Re-estimate noise from already-reduced signal for a tighter second pass
            noise_ref   = _find_noise_sample(current, rate)
            n_fft       = 1024
            win_length  = 1024
            hop_length  = 256
            time_const  = 1.0
            freq_smooth = 100
            time_smooth = 60

        current = nr.reduce_noise(
            y=current,
            sr=rate,
            y_noise=noise_ref,
            prop_decrease=prop,
            stationary=False,
            n_fft=n_fft,
            win_length=win_length,
            hop_length=hop_length,
            time_constant_s=time_const,
            freq_mask_smooth_hz=freq_smooth,
            time_mask_smooth_ms=time_smooth,
        )

    # Blend dry signal back — preserves natural timbre, prevents over-processing
    output = current * (1.0 - blend) + dry * blend

    # Normalise to 0.95 peak to prevent clipping in downstream steps
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.95

    sf.write(output_path, (output * 32767).astype(np.int16), rate, subtype="PCM_16")
    logger.info("[Step2] Spectral denoise done.")
    

def step3_deepfilter(input_path: str, output_path: str, profile: dict):
    """
    DeepFilterNet neural enhancement — Step 3 (strong/extreme preset only).

    Position in pipeline: AFTER SpectralNR, BEFORE RNNoise.

    CRITICAL FIX — WHY WE BYPASS load_audio() AND save_audio():
      DeepFilterNet's load_audio() and save_audio() both use torchaudio's
      backend internally. On Windows, torchaudio resolves the ffmpeg binary
      through its own registry — completely separate from the system PATH
      that subprocess uses. This causes [WinError 2] (file not found) even
      when ffmpeg is perfectly accessible via subprocess.

      Fix: we use soundfile to read the WAV → convert to torch tensor manually
      → call enhance() → convert tensor back to numpy → write with soundfile.
      This eliminates torchaudio's ffmpeg dependency entirely for I/O while
      still using DeepFilterNet's full neural enhancement.

    SafePopen fix:
      init_df() calls `git` at model-load time on some builds.  _SafePopen
      is installed permanently (at module level) so it is always active when
      this function runs — no local patching needed here.

    df_atten_lim_db:
      Hard ceiling on suppression. 25dB is conservative because SpectralNR
      has already handled the stationary floor — no need to push DF harder.
    """
    if not DEEPFILTER_AVAILABLE:
        logger.warning(
            "[Step3-DeepFilter] Package not installed — skipping. "
            "Strong preset degraded to SpectralNR + RNNoise only. "
            "Install with: pip install deepfilternet"
        )
        shutil.copy2(input_path, output_path)
        return

    atten_lim = profile.get("df_atten_lim_db", 25)
    logger.info(f"[Step3-DeepFilter] Starting. atten_lim_db={atten_lim}")

    try:
        model, df_state, sr = _get_df_model()

        # ── Read audio with soundfile (bypasses torchaudio ffmpeg backend) ──
        # Step1 guarantees input is 48kHz mono PCM WAV — matches DF's native SR.
        # If somehow SR differs, resample with numpy before tensor conversion.
        audio_np, file_sr = sf.read(input_path, dtype="float32")

        if audio_np.ndim > 1:
            audio_np = audio_np.mean(axis=1)  # stereo → mono (safety)

        if file_sr != sr:
            # Resample if needed — should never happen since Step1 outputs 48kHz
            import librosa
            audio_np = librosa.resample(audio_np, orig_sr=file_sr, target_sr=sr)
            logger.warning(f"[Step3-DeepFilter] Resampled {file_sr}Hz → {sr}Hz")

        # ── Convert numpy [T] → torch tensor [1, T] (DF expects [C, T]) ──
        audio_tensor = torch.from_numpy(audio_np).unsqueeze(0)  # [1, T]

        # ── Override attenuation limit without mutating global config state ──
        # df.enhance() accepts atten_lim_db as a keyword arg in newer versions.
        # Older versions require mutating df_config. Try the clean way first.
        try:
            enhanced_tensor = enhance(
                model, df_state, audio_tensor,
                atten_lim_db=atten_lim,
            )
        except TypeError:
            # Older df API — fall back to config mutation
            original_atten = None
            try:
                original_atten = df_config.get("attenuation_limit_db", None)
                df_config.set("attenuation_limit_db", atten_lim)
                enhanced_tensor = enhance(model, df_state, audio_tensor)
            finally:
                try:
                    if original_atten is not None:
                        df_config.set("attenuation_limit_db", original_atten)
                except Exception:
                    pass

        # ── Convert tensor [1, T] or [T] → numpy [T] ──
        enhanced_np = enhanced_tensor.squeeze().cpu().numpy()

        # ── Normalise to 0.95 peak to prevent clipping ──
        peak = np.max(np.abs(enhanced_np))
        if peak > 0:
            enhanced_np = enhanced_np / peak * 0.95

        # ── Write with soundfile (bypasses torchaudio ffmpeg backend) ──
        sf.write(output_path, (enhanced_np * 32767).astype(np.int16), sr, subtype="PCM_16")

        logger.info("[Step3-DeepFilter] Done.")

    except Exception as e:
        logger.error(f"[Step3-DeepFilter] Error ({e}) — falling back to SpectralNR output.")
        shutil.copy2(input_path, output_path)
        

def step4_rnnoise(input_path: str, output_path: str, profile: dict):
    """
    RNNoise neural denoiser — Step 4 (normal and strong presets).

    Position in pipeline:
      normal: directly after SpectralNR — primary neural denoiser
      strong: after DeepFilterNet — lightweight residual cleanup

    Filter chain:
      highpass(80Hz)  — removes sub-bass rumble before neural pass
      arnndn          — RNNoise inference
      afftdn          — FFT gate for remaining stationary residuals
      EQ (1kHz, 3kHz) — restores body warmth and consonant clarity
                         that neural denoising tends to slightly soften
    """
    nf    = profile["afftdn_nf"]
    boost = profile["voice_boost_db"]

    filter_chain = (
        f"highpass=f=80:poles=2,"
        f"arnndn=m=cb.rnnn,"
        f"afftdn=nf={nf}:nt=w,"
        f"equalizer=f=1000:width_type=o:width=2:g={boost},"
        f"equalizer=f=3000:width_type=o:width=1.5:g={boost}"
    )

    command = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", filter_chain,
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", output_path
    ]
    run_ffmpeg(command, "Step4-RNNoise", cwd=SAFE_MODEL_DIR)
    

def step5_loudnorm(input_path: str, output_path: str, profile: dict):
    """
    Final loudness normalisation and dynamic processing — Step 5 (all presets).

    All presets:
      agate     — noise gate between words (conservative threshold per preset)
      compand   — light compression to even out voice dynamics
      loudnorm  — EBU R128 broadcast standard (-16 LUFS, LRA 11, -1.5 TP)
      alimiter  — hard brick-wall limiter to prevent output clipping

    Strong preset additionally:
      lowpass(8kHz)  — tames residual hiss above voice range
      EQ dip (7kHz)  — gentle de-esser, prevents over-bright sibilance
      adeclick       — removes click/pop artefacts from processing frame edges
    """
    gate_t = profile["gate_threshold"]
    gate_r = profile["gate_ratio"]

    if profile["passes"] >= 2:
        filter_chain = (
            f"lowpass=f=8000:poles=2,"
            f"agate=threshold={gate_t}:ratio={gate_r}:attack=10:release=300,"
            f"equalizer=f=7000:width_type=o:width=1.5:g=-2,"
            f"compand=attacks=0.05:decays=0.3:"
            f"points=-80/-80|-35/-35|-15/-10|0/-5:soft-knee=6,"
            f"adeclick=w=55:o=50,"
            f"loudnorm=I=-16:LRA=11:TP=-1.5,"
            f"alimiter=level_in=1:level_out=0.99:limit=0.99:attack=5:release=50"
        )
    else:
        filter_chain = (
            f"agate=threshold={gate_t}:ratio={gate_r}:attack=20:release=500,"
            f"compand=attacks=0.1:decays=0.5:"
            f"points=-80/-80|-35/-35|-15/-10|0/-5:soft-knee=6,"
            f"loudnorm=I=-16:LRA=11:TP=-1.5,"
            f"alimiter=level_in=1:level_out=0.99:limit=0.99:attack=5:release=50"
        )

    command = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", filter_chain,
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", output_path
    ]
    run_ffmpeg(command, "Step5-Loudnorm+Dynamics")
    
# ==============================
# PIPELINE ORCHESTRATOR
# ==============================

def process_audio(input_path: str, output_path: str, profile: dict):
    """
    Crystal Clear Audio Pipeline

    ┌──────────┬──────────────────────────────────────────────────────────────────┐
    │ Preset   │ Pipeline                                                         │
    ├──────────┼──────────────────────────────────────────────────────────────────┤
    │ light    │ Step1(Mono) → Step2(SpectralNR 40%) → Step5(Loudnorm)            │
    │ normal   │ Step1 → Step2(SpectralNR 60%) → Step4(RNNoise) → Step5          │
    │ strong   │ Step1 → Step2(SpectralNR 75%×2) → Step3(DeepFilter 25dB) →      │
    │          │         Step4(RNNoise) → Step5(+cleanup)                         │
    └──────────┴──────────────────────────────────────────────────────────────────┘

    Each stage targets a specific noise class:
      SpectralNR    — stationary floor (hiss, hum, HVAC)
      DeepFilterNet — complex non-stationary noise (crowd, music, reverb)
      RNNoise       — broadband residuals and transient artefacts
      Loudnorm      — dynamics, gating, broadcast loudness standard

    Temp files:
      s1 — mono WAV (Step1)
      s2 — spectral NR output (Step2)
      s3 — DeepFilterNet output (Step3, strong only)
      s4 — RNNoise output (Step4, normal + strong)
    """
    uid = os.path.basename(input_path).split("_")[0]
    s1  = os.path.join(TEMP_DIR, f"{uid}_s1.wav")
    s2  = os.path.join(TEMP_DIR, f"{uid}_s2.wav")
    s3  = os.path.join(TEMP_DIR, f"{uid}_s3.wav")
    s4  = os.path.join(TEMP_DIR, f"{uid}_s4.wav")

    try:
        logger.info(
            f"Pipeline start — preset profile: passes={profile['passes']} "
            f"prop={profile['prop_decrease']} blend={profile['blend_original']} "
            f"deepfilter={profile['deepfilter']} rnnoise={profile['rnnoise']}"
        )

        # ── Step 1: Format normalise to 48kHz mono WAV ────────────────────────
        step1_to_mono_wav(input_path, s1)

        # ── Step 2: Spectral noise reduction (all presets) ────────────────────
        step2_spectral_denoise(s1, s2, profile)

        if profile["deepfilter"]:
            # ── strong: SpectralNR → DeepFilterNet → RNNoise ──────────────────
            step3_deepfilter(s2, s3, profile)
            step4_rnnoise(s3, s4, profile)
            step5_loudnorm(s4, output_path, profile)

        elif profile["rnnoise"]:
            # ── normal: SpectralNR → RNNoise ──────────────────────────────────
            step4_rnnoise(s2, s4, profile)
            step5_loudnorm(s4, output_path, profile)

        else:
            # ── light: SpectralNR only ─────────────────────────────────────────
            step5_loudnorm(s2, output_path, profile)

        logger.info("Pipeline complete — output ready.")

    finally:
        cleanup_files(s1, s2, s3, s4)
