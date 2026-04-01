@echo off
setlocal enabledelayedexpansion
title JARVIS Setup - HP Pavilion Gaming 15

echo.
echo  ================================================================================
echo   JARVIS AI ASSISTANT - ONE-CLICK SETUP
echo   Optimized for: HP Pavilion Gaming 15 (Ryzen 5 5600H / GTX 1650 / Windows 11)
echo  ================================================================================
echo.

:: ─── Check Python 3.10+ ───────────────────────────────────────────────────────
echo [1/9] Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)

if !PY_MAJOR! LSS 3 (
    echo [ERROR] Python 3.10+ required. Found !PYVER!
    pause
    exit /b 1
)
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 10 (
    echo [ERROR] Python 3.10+ required. Found !PYVER!
    pause
    exit /b 1
)
echo [OK] Python !PYVER! detected.

:: ─── Create Virtual Environment ───────────────────────────────────────────────
echo.
echo [2/9] Creating virtual environment...
if exist "venv" (
    echo [INFO] Virtual environment already exists. Skipping creation.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)

:: Activate venv
call venv\Scripts\activate.bat
echo [OK] Virtual environment activated.

:: ─── Install Requirements ──────────────────────────────────────────────────────
echo.
echo [3/9] Installing Python packages (this may take several minutes)...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [WARNING] Some packages may have failed. Trying one-by-one...
    for /f "skip=1 tokens=*" %%p in (requirements.txt) do (
        if not "%%p"=="" (
            if not "%%p:~0,1%"=="#" (
                pip install "%%p" --quiet 2>nul
            )
        )
    )
)
echo [OK] Python packages installed.

:: ─── Install PyTorch with CUDA for GTX 1650 ───────────────────────────────────
echo.
echo [4/9] Installing PyTorch with CUDA support (GTX 1650 - CUDA 12.1)...
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 --quiet
if errorlevel 1 (
    echo [WARNING] CUDA PyTorch failed. Installing CPU version as fallback...
    pip install torch torchvision --quiet
)
echo [OK] PyTorch installed.

:: ─── Install Ollama ────────────────────────────────────────────────────────────
echo.
echo [5/9] Checking Ollama installation...
where ollama >nul 2>&1
if errorlevel 1 (
    echo [INFO] Ollama not found. Downloading installer...
    powershell -Command "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile 'OllamaSetup.exe'"
    if exist "OllamaSetup.exe" (
        echo [INFO] Running Ollama installer...
        OllamaSetup.exe /S
        del OllamaSetup.exe
        echo [OK] Ollama installed.
    ) else (
        echo [WARNING] Could not download Ollama. Install manually from https://ollama.com
    )
) else (
    echo [OK] Ollama already installed.
)

:: ─── Pull LLM Model ────────────────────────────────────────────────────────────
echo.
echo [6/9] Pulling LLM model (mistral - recommended for instruction following)...
echo [INFO] This downloads ~4.1GB. Please wait...
start "" /B ollama serve >nul 2>&1
timeout /t 3 /nobreak >nul
ollama pull mistral
if errorlevel 1 (
    echo [WARNING] mistral model failed. Trying phi as fallback...
    ollama pull phi
    if errorlevel 1 (
        echo [WARNING] Could not pull models. Start Ollama manually and run: ollama pull mistral
    ) else (
        echo [OK] phi model ready (fallback).
        :: Update config to use phi
        powershell -Command "(Get-Content config.yaml) -replace 'model: .mistral.', 'model: \"phi\"' | Set-Content config.yaml"
    )
) else (
    echo [OK] mistral model ready.
)

:: ─── Download Vosk Model ───────────────────────────────────────────────────────
echo.
echo [7/9] Downloading Vosk speech recognition model...
set VOSK_MODEL_DIR=models\vosk-model-small-en-us-0.15
if exist "%VOSK_MODEL_DIR%" (
    echo [OK] Vosk model already present.
) else (
    mkdir models 2>nul
    echo [INFO] Downloading vosk-model-small-en-us-0.15 (~40MB)...
    powershell -Command "Invoke-WebRequest -Uri 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip' -OutFile 'models\vosk_model.zip'"
    if exist "models\vosk_model.zip" (
        powershell -Command "Expand-Archive -Path 'models\vosk_model.zip' -DestinationPath 'models' -Force"
        del "models\vosk_model.zip"
        echo [OK] Vosk model downloaded and extracted.
    ) else (
        echo [WARNING] Could not download Vosk model. Download manually from:
        echo           https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
        echo           Extract to: models\vosk-model-small-en-us-0.15\
    )
)

:: ─── Verify GPU / CUDA ─────────────────────────────────────────────────────────
echo.
echo [8/9] Verifying CUDA / GTX 1650...
python -c "import torch; print('[OK] CUDA available:', torch.cuda.is_available()); print('[OK] GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None (CPU mode)')" 2>nul
if errorlevel 1 (
    echo [WARNING] Could not verify CUDA. GPU acceleration may not be active.
)

:: ─── Initial System Scan ───────────────────────────────────────────────────────
echo.
echo [9/9] Running initial system scan...
python -c "
import sys, os
sys.path.insert(0, '.')
try:
    from utils.helpers import get_config
    print('[OK] Config loaded successfully')
except Exception as e:
    print('[WARNING] Config check failed:', e)

try:
    import psutil
    cpu = psutil.cpu_count()
    ram = round(psutil.virtual_memory().total / (1024**3), 1)
    print(f'[OK] System: {cpu} CPU threads, {ram}GB RAM detected')
except Exception as e:
    print('[WARNING] psutil check failed:', e)
" 2>nul

:: ─── Create necessary directories ─────────────────────────────────────────────
mkdir data 2>nul
mkdir logs 2>nul
mkdir models 2>nul

:: ─── Final Summary ─────────────────────────────────────────────────────────────
echo.
echo  ================================================================================
echo   SETUP COMPLETE!
echo  ================================================================================
echo.
echo  To start JARVIS:
echo    1. Activate the virtual environment:  venv\Scripts\activate
echo    2. Start Ollama service:               ollama serve
echo    3. Launch JARVIS:                      python main.py
echo.
echo  Voice Mode:
echo    - Say "Jarvis" to activate listening
echo    - Speak your command
echo    - JARVIS will respond and execute
echo.
echo  Text Mode:
echo    - Type directly in the terminal
echo    - Press Enter to send
echo.
echo  Quick Commands:
echo    "Jarvis, open Chrome"
echo    "Jarvis, what's my CPU usage?"
echo    "Jarvis, find all PDF files on my desktop"
echo    "Jarvis, take a screenshot"
echo    "Jarvis, open Windows settings"
echo.
echo  ================================================================================
echo.
pause
