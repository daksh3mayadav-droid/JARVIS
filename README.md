# JARVIS AI Assistant

```
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
         Just A Rather Very Intelligent System
                   — TARS Edition
```

A fully local, 100% free autonomous AI assistant for Windows 11, inspired by
**TARS** from *Interstellar* and **JARVIS** from *Iron Man*. Runs entirely on
your machine — no cloud, no subscriptions, no telemetry.

---

## 🎯 Target Hardware

| Component | Spec |
|-----------|------|
| **CPU** | AMD Ryzen 5 5600H (6c/12t) |
| **GPU** | NVIDIA GTX 1650 (4GB VRAM) |
| **RAM** | 16 GB |
| **OS** | Windows 11 |
| **Storage** | SSD |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│                        main.py                           │
│                  (Boot & Orchestrator)                   │
└───────────┬──────────────────────────┬───────────────────┘
            │                          │
     ┌──────▼──────┐           ┌───────▼───────┐
     │  core/      │           │  interface/   │
     │  brain.py   │◄─────────►│  text_interface│
     │  memory.py  │           │  gui.py       │
     │  planner.py │           └───────────────┘
     │  safety.py  │
     └──────┬──────┘
            │
    ┌───────┼────────────────┐
    │       │                │
┌───▼──┐ ┌──▼────┐ ┌────────▼──────┐
│voice/│ │vision/│ │   system/     │
│wake  │ │screen │ │ controller    │
│word  │ │capture│ │ file_manager  │
│listen│ │ocr    │ │ process_mgr   │
│speak │ │analyz │ │ app_launcher  │
└──────┘ └───────┘ │ windows_nav   │
                   │ hardware_info │
                   └───────────────┘
                          │
                   ┌──────▼──────┐
                   │ automation/ │
                   │task_automator│
                   │browser_ctrl │
                   └─────────────┘
```

---

## ✨ Features

### 🧠 Intelligence
- **Local LLM** via [Ollama](https://ollama.com) — `phi` (2.7B, fast on GTX 1650) or `mistral:instruct` (7B)
- Intent classification: system_control, file_ops, app_launch, information, settings, automation, vision
- Multi-step autonomous task planning with progress reporting
- Persistent SQLite memory — learns your preferences and patterns
- Conversation context window (last 20 messages)

### 🎤 Voice
- **Wake word**: Say "Jarvis" — continuous background listener (~2-5% CPU)
- Offline STT via [Vosk](https://alphacephei.com/vosk/) — no internet required
- Text-to-speech via `pyttsx3` — offline, no API keys
- Audio beep + visual indicator on wake word detection

### 👁️ Vision
- Real-time screen capture via `mss`
- OCR via **EasyOCR** (GPU-accelerated on GTX 1650) with `pytesseract` fallback
- UI element detection, error/dialog detection, frame change detection
- Active window title monitoring

### 💻 System Control
- Mouse: click, double-click, right-click, drag, scroll
- Keyboard: type with human-like timing, hotkeys, key combinations
- Window: switch, minimize, maximize, close
- Full Windows 11 settings navigation via `ms-settings:` URIs
- Toggle WiFi, Bluetooth, Night Light; control Volume & Brightness

### 📁 File Management
- Browse, search, create, copy, move, rename, delete
- SQLite-backed file index for instant search
- Folder watching with `watchdog`
- Recycle Bin integration (safe delete)
- Disk usage analysis

### 🤖 Automation
- Record & replay mouse/keyboard sequences
- Scheduled tasks (one-time or recurring)
- Built-in templates: `cleanup_downloads`, etc.
- Browser automation: open URLs, Google search, tab management

### 🎭 TARS Personality
- Dry, concise, slightly sarcastic responses
- Configurable humor level (0-100%)
- Context-aware wit (different for file ops, app launch, errors, etc.)
- Serious mode for critical operations

---

## 🚀 Quick Start

### One-Click Setup (Windows)
```batch
git clone https://github.com/daksh3mayadav-droid/JARVIS.git
cd JARVIS
setup.bat
```

`setup.bat` will:
1. Check Python 3.10+
2. Create virtual environment
3. Install all pip dependencies
4. Install Ollama (if missing)
5. Download `phi` LLM model (~1.6 GB)
6. Download Vosk speech model (~40 MB)
7. Verify CUDA / GTX 1650
8. Run initial system scan

### Manual Setup
```bash
# 1. Create venv
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install PyTorch with CUDA (GTX 1650)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 4. Install Ollama from https://ollama.com
# Then pull a model:
ollama pull phi

# 5. Download Vosk model
# From: https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
# Extract to: models/vosk-model-small-en-us-0.15/

# 6. Launch JARVIS
python main.py
```

---

## 🗣️ Usage Examples

### Voice (after wake word)
```
"Jarvis, open Chrome"
"Jarvis, what's my CPU usage?"
"Jarvis, find all PDF files in my Downloads folder"
"Jarvis, take a screenshot"
"Jarvis, open WiFi settings"
"Jarvis, set volume to 60"
"Jarvis, search YouTube for lo-fi music"
"Jarvis, what's running on my GPU?"
```

### Text (type in terminal)
```
>> open notepad
>> status
>> settings bluetooth
>> find report.pdf
>> help
```

---

## ⚙️ Configuration (`config.yaml`)

```yaml
jarvis:
  name: "JARVIS"
  wake_word: "jarvis"      # Change to any word
  humor_level: 75          # 0 = serious, 100 = maximum TARS

llm:
  provider: "groq"         # Options: "groq", "gemini", "ollama"
  groq_api_key: ""         # Get from https://console.groq.com
  temperature: 0.7

voice:
  enabled: true
  rate: 175                # Speech rate (words per minute)
  volume: 0.9              # 0.0 - 1.0

system:
  safe_mode: true          # false = no confirmation for risky actions
```

---

## 🤖 LLM Provider Setup

JARVIS supports three LLM providers. Edit `config.yaml` to choose:

### Groq (Recommended — Free & Fastest)
1. Get a free API key at https://console.groq.com
2. Set in `config.yaml`:
   ```yaml
   llm:
     provider: "groq"
     groq_api_key: "gsk_your_key_here"
   ```

### Google Gemini (Free Tier Available)
1. Get an API key at https://aistudio.google.com/apikey
2. Set in `config.yaml`:
   ```yaml
   llm:
     provider: "gemini"
     gemini_api_key: "your_key_here"
   ```

### Ollama (Local, Offline)
1. Install Ollama: https://ollama.com
2. Pull a model: `ollama pull gemma2:2b`
3. Set in `config.yaml`:
   ```yaml
   llm:
     provider: "ollama"
     model: "gemma2:2b"
   ```

| Provider | Response Time | Cost | Requires Internet |
|----------|--------------|------|-------------------|
| **Groq** | ~200ms | Free tier | Yes |
| **Google Gemini** | ~300ms | Free tier | Yes |
| Ollama (local) | 3–15 seconds | Free | No |

---

## 📁 Project Structure

```
JARVIS/
├── main.py                      # Boot & orchestrator
├── config.yaml                  # Central configuration
├── requirements.txt             # All dependencies
├── setup.bat                    # Windows one-click setup
│
├── core/
│   ├── brain.py                 # LLM reasoning engine
│   ├── memory.py                # SQLite persistent memory
│   ├── planner.py               # Autonomous task planner
│   └── safety.py                # Risk classifier
│
├── vision/
│   ├── screen_capture.py        # Real-time screen capture
│   ├── screen_analyzer.py       # UI/text/error detection
│   └── ocr_engine.py            # EasyOCR + Tesseract
│
├── voice/
│   ├── listener.py              # Vosk offline STT
│   ├── speaker.py               # pyttsx3 TTS
│   └── wake_word.py             # Background wake word detector
│
├── system/
│   ├── controller.py            # Mouse/keyboard/window control
│   ├── file_manager.py          # Full filesystem ops
│   ├── process_manager.py       # Process/resource monitor
│   ├── app_launcher.py          # App scanner & launcher
│   ├── windows_navigator.py     # Windows 11 settings nav
│   └── hardware_info.py         # Hardware specs & monitoring
│
├── interface/
│   ├── text_interface.py        # Rich terminal UI
│   └── gui.py                   # System tray + overlay
│
├── automation/
│   ├── task_automator.py        # Record/replay/schedule
│   └── browser_control.py      # Browser automation
│
├── utils/
│   ├── logger.py                # Rotating file + Rich console
│   ├── helpers.py               # Utilities (config, retry, fuzzy)
│   └── tars_personality.py      # TARS wit engine
│
├── data/                        # Runtime data (auto-created)
│   ├── jarvis_memory.db         # SQLite memory
│   ├── file_index.db            # File index
│   └── screenshots/             # Captured screenshots
│
├── logs/                        # Log files (auto-created)
│   ├── jarvis.log
│   ├── actions.log
│   └── errors.log
│
└── models/                      # AI models (downloaded by setup.bat)
    └── vosk-model-small-en-us-0.15/
```

---

## 🔒 Safety System

| Level | Examples | Behaviour |
|-------|----------|-----------|
| **SAFE** | Open apps, read files, screenshots | Auto-executes |
| **RISKY** | Move files, install, settings changes | Single confirmation |
| **DANGEROUS** | Delete files, kill processes, shutdown | Double confirmation with timeout |

Set `safe_mode: false` in `config.yaml` to skip RISKY confirmations.

---

## 💰 Cost

| Component | Cost |
|-----------|------|
| Ollama | Free |
| phi / mistral LLM | Free (local) |
| Vosk STT | Free (offline) |
| pyttsx3 TTS | Free (offline) |
| All Python packages | Free / open-source |
| **Total** | **$0** |

---

## 📜 License

MIT License — free to use, modify, and distribute.