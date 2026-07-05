"""
transcription.py — FluidVoice Windows
faster-whisper integration: model download, loading, and transcription.
Equivalent of FluidAudio + WhisperProvider + NemotronProvider on macOS.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from settings import settings, MODELS_DIR


SAMPLE_RATE = 16000

# ---------------------------------------------------------------------------
# Model catalogue (mirrors FluidVoice macOS model list)
# ---------------------------------------------------------------------------

WHISPER_MODELS: dict[str, dict] = {
    "tiny": {
        "label": "Whisper Tiny",
        "description": "Fastest, ~75 MB. Good for quick notes.",
        "size_mb": 75,
        "accuracy": "Basic",
        "speed": "⚡⚡⚡⚡",
    },
    "base": {
        "label": "Whisper Base  (Recommended)",
        "description": "Fast, ~150 MB. Best starting point for most users.",
        "size_mb": 150,
        "accuracy": "Good",
        "speed": "⚡⚡⚡",
    },
    "small": {
        "label": "Whisper Small",
        "description": "Balanced, ~500 MB. Better accuracy.",
        "size_mb": 500,
        "accuracy": "Better",
        "speed": "⚡⚡",
    },
    "distil-small.en": {
        "label": "Distil Small (English only)",
        "description": "Fast & accurate English, ~340 MB.",
        "size_mb": 340,
        "accuracy": "Better",
        "speed": "⚡⚡⚡",
    },
    "medium": {
        "label": "Whisper Medium",
        "description": "High accuracy, ~1.5 GB.",
        "size_mb": 1500,
        "accuracy": "Great",
        "speed": "⚡",
    },
    "distil-large-v3": {
        "label": "Distil Large v3  (Best balance)",
        "description": "Best accuracy at 6x speed of large, ~1.5 GB.",
        "size_mb": 1500,
        "accuracy": "Best",
        "speed": "⚡⚡",
    },
    "large-v3": {
        "label": "Whisper Large v3",
        "description": "Maximum accuracy, ~3 GB. Slowest on CPU.",
        "size_mb": 3000,
        "accuracy": "Best",
        "speed": "🐌",
    },
}


# ---------------------------------------------------------------------------
# Hardware Detection  (GPU + CPU brand / instruction sets)
# ---------------------------------------------------------------------------

def detect_hardware() -> dict:
    """
    Probe the full hardware picture:
      GPU  — CUDA (NVIDIA), ROCm (AMD), Vulkan, OpenVINO (Intel)
      CPU  — brand, AVX2, AVX-512 support
    Returns a unified info dict.
    """
    info: dict = {
        # GPU
        "cuda": False,
        "rocm": False,
        "vulkan": False,
        "openvino": False,
        # CPU
        "cpu": True,
        "cpu_brand": "Unknown",   # "AMD" | "Intel" | "Apple" | "ARM" | "Unknown"
        "cpu_name": "",
        "avx2": False,
        "avx512": False,
        "is_amd_cpu": False,
        "is_intel_cpu": False,
    }

    # ------------------------------------------------------------------
    # CPU brand & instruction sets
    # ------------------------------------------------------------------
    try:
        import platform
        cpu_name = platform.processor() or ""
        info["cpu_name"] = cpu_name
        low = cpu_name.lower()
        if "amd" in low or "ryzen" in low or "epyc" in low or "athlon" in low:
            info["cpu_brand"] = "AMD"
            info["is_amd_cpu"] = True
        elif "intel" in low or "core" in low or "xeon" in low or "celeron" in low:
            info["cpu_brand"] = "Intel"
            info["is_intel_cpu"] = True
        elif "arm" in low or "apple" in low or "qualcomm" in low:
            info["cpu_brand"] = "ARM"
    except Exception:
        pass

    # AVX2 / AVX-512 via cpuinfo (optional) or ctranslate2
    try:
        import ctranslate2  # type: ignore[import]
        cpu_types = ctranslate2.get_supported_compute_types("cpu")
        # CTranslate2 exposes AVX2-dependent int8 only when AVX2 is present
        info["avx2"] = "int8" in cpu_types
        # AVX-512 exposes int8_float16 on supported hardware
        info["avx512"] = "int8_float16" in cpu_types
    except Exception:
        pass

    # Fallback AVX detection via cpuinfo library (optional)
    try:
        import cpuinfo  # type: ignore[import]
        flags = cpuinfo.get_cpu_info().get("flags", [])
        info["avx2"] = info["avx2"] or "avx2" in flags
        info["avx512"] = info["avx512"] or any(f.startswith("avx512") for f in flags)
        if not info["cpu_name"]:
            info["cpu_name"] = cpuinfo.get_cpu_info().get("brand_raw", "")
    except Exception:
        pass

    # ------------------------------------------------------------------
    # GPU — CUDA (NVIDIA)
    # ------------------------------------------------------------------
    try:
        import ctranslate2  # type: ignore[import]
        if "int8" in ctranslate2.get_supported_compute_types("cuda"):
            info["cuda"] = True
    except Exception:
        pass

    if not info["cuda"]:
        try:
            import torch  # type: ignore[import]
            info["cuda"] = torch.cuda.is_available()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # GPU — ROCm (AMD)
    # ------------------------------------------------------------------
    try:
        import torch  # type: ignore[import]
        if hasattr(torch.version, "hip") and torch.version.hip:
            info["rocm"] = True
        elif torch.cuda.is_available():
            dev = torch.cuda.get_device_name(0).lower()
            if any(k in dev for k in ("amd", "radeon", "vega", "navi", "rdna")):
                info["rocm"] = True
    except Exception:
        pass

    if not info["rocm"]:
        try:
            import ctypes
            ctypes.cdll.LoadLibrary("amdhip64.dll")
            info["rocm"] = True
        except Exception:
            pass

    # ------------------------------------------------------------------
    # GPU — Vulkan
    # ------------------------------------------------------------------
    try:
        import ctypes
        ctypes.cdll.LoadLibrary("vulkan-1.dll")
        info["vulkan"] = True
    except Exception:
        pass

    # ------------------------------------------------------------------
    # OpenVINO (Intel iGPU / Arc)
    # ------------------------------------------------------------------
    try:
        import openvino  # type: ignore[import]  # noqa: F401
        info["openvino"] = True
    except Exception:
        pass

    return info


# Cached result so we only probe once per session
_hw: dict | None = None

def get_hardware() -> dict:
    """Return cached hardware info (probed once on first call)."""
    global _hw
    if _hw is None:
        _hw = detect_hardware()
        brand = _hw["cpu_brand"]
        avx = "AVX-512" if _hw["avx512"] else ("AVX2" if _hw["avx2"] else "no-AVX")
        gpu_backends = [k for k in ("cuda", "rocm", "vulkan", "openvino") if _hw[k]]
        print(f"[Hardware] CPU: {brand} ({avx})  |  GPU: {gpu_backends or ['none detected']}")
    return _hw


# keep old name as alias for backwards compat
def detect_gpu_devices() -> dict[str, bool]:
    hw = get_hardware()
    return {k: hw[k] for k in ("cuda", "rocm", "vulkan", "openvino", "cpu")}


def _detect_amd_zen_generation(cpu_name: str) -> int:
    """
    Estimate AMD Zen generation from CPU model string.
    Returns: 1=Zen1, 2=Zen2, 3=Zen3, 4=Zen4, 5=Zen5, 0=unknown/non-AMD.

    Zen generation → instruction set support:
      Zen 1  (Ryzen 1000 / EPYC Naples)   : AVX2
      Zen 2  (Ryzen 3000 / EPYC Rome)     : AVX2, full 256-bit FPU  ← Zen 2+
      Zen 3  (Ryzen 5000 / EPYC Milan)    : AVX2 + improved IPC
      Zen 4  (Ryzen 7000 / EPYC Genoa)    : AVX2 + AVX-512
      Zen 5  (Ryzen 9000 / EPYC Turin)    : AVX2 + AVX-512 + improved throughput
    """
    n = cpu_name.lower()

    # EPYC server chips
    if "epyc" in n:
        if any(x in n for x in ("9", "genoa", "bergamo", "siena")):
            return 4
        if any(x in n for x in ("7003", "milan", "7002", "rome")):
            return 3 if "7003" in n or "milan" in n else 2
        if any(x in n for x in ("7001", "naples")):
            return 1
        return 3  # safe default for unknown EPYC

    # Threadripper
    if "threadripper" in n:
        if "7000" in n or "7900" in n or "7960" in n or "7970" in n:
            return 4
        if "5000" in n or "pro 5" in n:
            return 3
        if "3000" in n or "pro 3" in n:
            return 2
        return 2

    # Ryzen desktop / mobile — parse the 4-digit model number
    import re
    m = re.search(r"ryzen\s+\d+\s+(\d{4})", n)
    if m:
        model = int(m.group(1))
        if model >= 9000:
            return 5
        if model >= 7000:
            return 4
        if model >= 5000:
            return 3
        if model >= 3000:
            return 2
        if model >= 1000:
            return 1

    # Ryzen mobile APU naming (e.g. 7845HX, 6900HX, 5800H, 4800H, 3700U)
    m2 = re.search(r"(\d{4})[a-z]{1,3}", n)
    if m2:
        model = int(m2.group(1))
        if model >= 7800:
            return 4
        if model >= 5800:
            return 3
        if model >= 4600:
            return 2
        if model >= 3000:
            return 2
        if model >= 2000:
            return 1

    return 0  # non-AMD or unrecognised


def resolve_device_and_compute(
    device: str, compute_type: str
) -> tuple[str, str]:
    """
    Resolve 'auto' device/compute_type to the best concrete values for this
    machine, with AMD Zen-generation-aware CPU optimisation.

    CTranslate2 compute types (fastest → slowest on CPU):
      int8_float16  AMD Zen 4+ / Intel Sapphire Rapids (AVX-512 required)
      int8          AMD Zen 2+ / Intel Haswell+ (AVX2 required) ← sweet spot
      float16       GPU only
      float32       safe fallback, any x86
    """
    hw = get_hardware()

    # ----------------------------------------------------------------
    # Resolve device
    # ----------------------------------------------------------------
    if device == "auto":
        if hw["cuda"] or hw["rocm"]:
            device = "cuda"
        else:
            device = "cpu"
    elif device == "rocm":
        if hw["rocm"]:
            device = "cuda"
        else:
            print("[Transcription] ROCm requested but not detected. Falling back to CPU.")
            device = "cpu"
    elif device == "cuda":
        if not hw["cuda"]:
            print("[Transcription] CUDA GPU requested but not detected. Falling back to CPU.")
            device = "cpu"
    elif device in ("vulkan", "openvino"):
        # Not natively supported by CTranslate2 — use CPU optimised path
        print(f"[Transcription] '{device}' backend not in CTranslate2 standard build — "
              "using optimised CPU path instead. "
              "For native Vulkan, install whisper.cpp.")
        device = "cpu"

    # ----------------------------------------------------------------
    # Resolve compute type
    # ----------------------------------------------------------------
    # If we fell back to CPU, force 'auto' compute type to resolve to CPU optimal (int8/int8_float16)
    if device == "cpu" and compute_type == "float16":
        compute_type = "auto"

    if compute_type == "auto":
        if device == "cuda":
            compute_type = "float16"          # Best GPU balance

        else:  # CPU path
            if hw["avx512"]:
                # Zen 4 / Zen 5 / Intel Sapphire Rapids
                compute_type = "int8_float16"
            elif hw["avx2"]:
                # Zen 2+ / Zen 3 / Intel Haswell+ — this is THE sweet spot
                compute_type = "int8"
            else:
                # Older CPUs without AVX2 — safe fallback
                compute_type = "float32"

            # Log what we picked and why
            if hw["is_amd_cpu"]:
                zen = _detect_amd_zen_generation(hw["cpu_name"])
                zen_str = f"Zen {zen}" if zen else "unknown gen"
                print(f"[Transcription] AMD CPU ({zen_str}) → compute_type={compute_type}")
            else:
                avx_str = "AVX-512" if hw["avx512"] else ("AVX2" if hw["avx2"] else "no-AVX")
                print(f"[Transcription] {hw['cpu_brand']} CPU ({avx_str}) → compute_type={compute_type}")

    return device, compute_type


def get_recommended_compute_for_cpu() -> str:
    """
    Returns the recommended CTranslate2 compute type for the current CPU.
    Used by the Settings UI to display a helpful hint.
    """
    hw = get_hardware()
    if hw["avx512"]:
        zen = _detect_amd_zen_generation(hw["cpu_name"])
        if zen >= 4:
            return "int8_float16 (AMD Zen 4+ / AVX-512)"
        return "int8_float16 (AVX-512)"
    if hw["avx2"]:
        zen = _detect_amd_zen_generation(hw["cpu_name"])
        if zen >= 2:
            return f"int8 (AMD Zen {zen} / AVX2)"
        return "int8 (AVX2)"
    return "float32 (safe fallback — no AVX2)"


# ---------------------------------------------------------------------------
# TranscriptionService
# ---------------------------------------------------------------------------



class TranscriptionService:
    """
    Manages the faster-whisper model lifecycle and transcription.
    Lazy-loads the model on first use to keep startup fast.
    """

    def __init__(self) -> None:
        self._model = None
        self._model_name: str | None = None
        self._lock = threading.Lock()
        self._loading = False
        self.on_progress_callback: Callable[[str], None] | None = None

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def load_model(
        self,
        model_name: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        """Load (or reload) the Whisper model. Blocks until complete."""
        from faster_whisper import WhisperModel  # type: ignore[import]

        name = model_name or settings.model_name
        raw_device = settings.model_device
        raw_compute = settings.model_compute_type
        
        # Resolve 'auto' / ROCm / Vulkan backends to concrete, supported CTranslate2 values
        device, compute_type = resolve_device_and_compute(raw_device, raw_compute)

        with self._lock:
            if self._model is not None and self._model_name == name:
                return  # Already loaded
            self._loading = True

        if on_progress:
            on_progress(f"Loading {WHISPER_MODELS.get(name, {}).get('label', name)}…")

        # faster-whisper downloads to HF cache by default;
        # we point it to our models dir for a clean install.
        cache_dir = str(MODELS_DIR)

        try:
            try:
                model = WhisperModel(
                    name,
                    device=device,
                    compute_type=compute_type,
                    download_root=cache_dir,
                )
            except Exception as gpu_err:
                # If GPU failed, check if we can fall back to CPU
                if device == "cuda":
                    print(f"[Transcription] GPU loading failed ({gpu_err}). Falling back to CPU...")
                    if on_progress:
                        on_progress("GPU fail. Falling back to CPU...")
                    
                    # Force CPU resolution
                    device, compute_type = resolve_device_and_compute("cpu", "auto")
                    
                    model = WhisperModel(
                        name,
                        device=device,
                        compute_type=compute_type,
                        download_root=cache_dir,
                    )
                else:
                    raise gpu_err

            with self._lock:
                self._model = model
                self._model_name = name
                self._loading = False
            if on_progress:
                on_progress("Model ready.")
        except Exception as e:
            with self._lock:
                self._loading = False
            raise RuntimeError(f"Failed to load model '{name}': {e}") from e

    def ensure_model_loaded(self) -> None:
        """Load the configured model if not already loaded."""
        if self._model is None or self._model_name != settings.model_name:
            self.load_model()

    def unload_model(self) -> None:
        with self._lock:
            self._model = None
            self._model_name = None

    @property
    def is_model_loaded(self) -> bool:
        return self._model is not None

    @property
    def current_model_name(self) -> str | None:
        return self._model_name

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def transcribe(
        self,
        audio: np.ndarray,
        on_progress: Callable[[str], None] | None = None,
        fast_mode: bool = False,
    ) -> str:
        """
        Transcribe a float32 numpy array (16 kHz mono) and return the text.
        Raises RuntimeError if audio is too short or transcription fails.
        """
        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            return ""  # Too short — ignore

        with self._lock:
            self.ensure_model_loaded()
            model = self._model

        if on_progress:
            on_progress("Transcribing…")

        try:
            lang = settings.language  # None = auto-detect
            with self._lock:
                if fast_mode:
                    # Optimized greedy decoding parameters for real-time preview (no retry loops)
                    segments, _info = model.transcribe(
                        audio,
                        language=lang,
                        beam_size=1,
                        best_of=1,
                        temperature=0.0,
                        compression_ratio_threshold=None,
                        log_prob_threshold=None,
                        no_speech_threshold=None,
                        vad_filter=True,
                        vad_parameters=dict(min_silence_duration_ms=250),
                    )
                else:
                    # High-accuracy beam search for the final pasted text
                    segments, _info = model.transcribe(
                        audio,
                        language=lang,
                        beam_size=5,
                        vad_filter=True,
                        vad_parameters=dict(min_silence_duration_ms=300),
                    )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text
        except Exception as e:
            raise RuntimeError(f"Transcription failed: {e}") from e

    # ------------------------------------------------------------------
    # Background load helper
    # ------------------------------------------------------------------

    def load_model_async(
        self,
        model_name: str | None = None,
        on_done: Callable[[bool, str], None] | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> threading.Thread:
        """Load model in a background thread. on_done(success, message)."""
        def _worker():
            try:
                self.load_model(model_name=model_name, on_progress=on_progress)
                if on_done:
                    on_done(True, "Model loaded.")
            except Exception as e:
                if on_done:
                    on_done(False, str(e))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t


# ---------------------------------------------------------------------------
# AI Enhancement (OpenAI-compatible)
# ---------------------------------------------------------------------------

def enhance_with_ai(text: str) -> str:
    """
    Post-process transcribed text via an OpenAI-compatible API.
    Returns original text if enhancement is disabled or fails.
    """
    if not settings.ai_enhancement_enabled or not settings.ai_api_key:
        return text

    try:
        import httpx  # type: ignore[import]

        provider = settings.ai_provider
        base_url = settings.ai_base_url

        if not base_url:
            if provider == "openai":
                base_url = "https://api.openai.com/v1"
            elif provider == "groq":
                base_url = "https://api.groq.com/openai/v1"
            else:
                base_url = "https://api.openai.com/v1"

        headers = {
            "Authorization": f"Bearer {settings.ai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.ai_model,
            "messages": [
                {"role": "system", "content": settings.ai_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
        }

        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        enhanced = data["choices"][0]["message"]["content"].strip()
        return enhanced if enhanced else text

    except Exception as e:
        print(f"[AI Enhancement] Failed: {e}")
        return text


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

transcription_service = TranscriptionService()
