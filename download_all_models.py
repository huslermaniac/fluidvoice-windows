"""
download_all_models.py — FluidVoice Windows
Helper script to download all Whisper models into the local project directory
before packaging the project into a standalone, offline portable .exe.
"""

import sys
import os
from pathlib import Path

# Ensure local project is on PATH
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

# Create local "models" folder inside project root
LOCAL_MODELS_DIR = PROJECT_ROOT / "models"
LOCAL_MODELS_DIR.mkdir(exist_ok=True)

# Temporarily override settings module models path before imports
import settings
settings.MODELS_DIR = LOCAL_MODELS_DIR

from transcription import transcription_service, WHISPER_MODELS

print("==================================================")
print("  FluidVoice Offline Model Downloader")
print(f"  Target Local Directory: {LOCAL_MODELS_DIR}")
print("==================================================")

for key, info in WHISPER_MODELS.items():
    print(f"\n[+] Fetching {info['label']} (~{info['size_mb']} MB)...")
    try:
        def _progress(msg: str):
            print(f"  > {msg}", end="\r")

        transcription_service.load_model(model_name=key, on_progress=_progress)
        print(f"\n[✓] {info['label']} downloaded successfully!")
    except Exception as e:
        print(f"\n[✗] Failed to download {info['label']}: {e}")

print("\n==================================================")
print("  All models ready! You can now run build.bat.")
print("==================================================")
