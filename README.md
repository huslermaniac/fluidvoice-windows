# FluidVoice for Windows ⚜️

Open-source voice-to-text dictation for Windows, powered by OpenAI Whisper.  
This is a Windows port of [FluidVoice](https://github.com/altic-dev/FluidVoice) (originally macOS/Swift), built with ⚜️ in Québec, Canada.

> ⚠️ **Project Status:** The core dictation pipeline, model downloader, transparent overlay, and text injection features are working. However, this is an early port and not all features or advanced settings combinations have been entirely tested yet. Contributions, feedback, and bug reports are welcome!

---

## Features

- 🎙 **On-device transcription** — Whisper runs fully locally, no internet required
- ⌨ **Works in any app** — text is pasted directly into whatever window is focused
- ⚡ **Global hotkey** — hold or toggle from anywhere on your PC
- 🔔 **System tray** — lives in the taskbar tray, always accessible
- ✨ **AI Enhancement** — optional post-processing via OpenAI or Groq API
- 📋 **History & Stats** — local history of all transcriptions
- 🌙 **Dark mode UI** — beautiful customtkinter dark interface

---

## Requirements & Tested System Configurations

* **Operating System**: Windows 10 / 11 (**Tested & verified on Windows 11 Pro**)
* **Processor (CPU)**: Intel / AMD with AVX2 or AVX-512 (**Tested & verified on AMD Ryzen CPU**)
  * *Features automatic Zen-generation CPU optimizations (Zen 2+).*
* **Graphics (GPU)**: NVIDIA GPU with CUDA or AMD GPU / Vulkan (**Tested & verified on AMD GPU with Vulkan**)
  * *Features automated fallback to highly-optimized CPU path on Vulkan/ROCm configurations.*
* **Python**: Version 3.11 or newer
* **Microphone**: Any hardware input device
* **Disk Space**: ~150 MB for the default Base model (up to 3 GB for Large model configurations)

### Verified Test Rig Specs
* **OS**: Windows 11 Pro
* **CPU**: AMD Ryzen 9 3900XT (12 Cores, 24 Threads)
* **GPU**: ASUS ROG Strix Radeon RX 6700 XT (12GB VRAM)
* **RAM**: 64 GB DDR4 @ 3600MHz

---

## Quick Start

### 1. Install Python dependencies

```bat
pip install -r requirements.txt
```

### 2. Run the app

```bat
python3 main.py
```

A FluidVoice icon will appear in your **system tray** (bottom-right of taskbar).  
On first run, the onboarding wizard will walk you through choosing a model and setting a hotkey.

### 3. Start dictating

1. Click anywhere to focus your target app / text field
2. **Hold your hotkey** (default: `Ctrl + Alt + Space`) — the overlay shows "Listening…"
3. **Speak** — your words are transcribed
4. **Release** — text is pasted into the focused window instantly

---

## Models

| Model | Size | Speed | Accuracy |
|---|---|---|---|
| Tiny | ~75 MB | ⚡⚡⚡⚡ | Basic |
| **Base** (default) | ~150 MB | ⚡⚡⚡ | Good |
| Small | ~500 MB | ⚡⚡ | Better |
| Medium | ~1.5 GB | ⚡ | Great |
| Large v3 | ~3 GB | 🐌 | Best |
| Large v3 Turbo | ~1.6 GB | ⚡⚡ | Best |

Models are downloaded once on first use into `%APPDATA%\FluidVoice\models\`.

---

## Settings

Right-click the tray icon → **Open Settings** to configure:

- **Hotkey** — click "Record Hotkey" and press your desired shortcut
- **Recording Mode** — hold-to-record or toggle
- **Whisper Model** — change model size
- **Audio Device** — select your microphone
- **AI Enhancement** — add an OpenAI or Groq API key for smarter post-processing
- **Text Injection** — clipboard paste (recommended) or simulate typing
- **Start with Windows** — auto-launch at login

---

## AI Enhancement

Add your API key in Settings → AI tab.

| Provider | API key source | Default model |
|---|---|---|
| OpenAI | platform.openai.com | `gpt-4o-mini` |
| Groq | console.groq.com | `llama-3.1-8b-instant` |
| Custom | your endpoint | configurable |

---

## Build a standalone .exe

```bat
pip install pyinstaller
build.bat
```

Output: `dist\FluidVoice.exe` — a single portable executable.

---

## File locations

| Path | Purpose |
|---|---|
| `%APPDATA%\FluidVoice\settings.json` | All settings |
| `%APPDATA%\FluidVoice\history.json` | Transcription history |
| `%APPDATA%\FluidVoice\models\` | Downloaded Whisper models |

---

## Support & Donations

If this Windows port makes your dictation workflow easier and saves you time, consider supporting its development:

* **Ko-fi**: [ko-fi.com/huslermaniac](https://ko-fi.com/huslermaniac)
* **Buy Me a Coffee**: [buymeacoffee.com/huslermaniac](https://www.buymeacoffee.com/huslermaniac)
* **PayPal**: [paypal.me/huslermaniac](https://paypal.me/huslermaniac)

Every contribution is greatly appreciated!

---

## Attribution

Original macOS app by [altic-dev](https://github.com/altic-dev/FluidVoice), licensed GPLv3.  
This Windows port is an independent reimplementation using Python + faster-whisper + customtkinter.

---

## License

GPLv3 — see [LICENSE](LICENSE).
