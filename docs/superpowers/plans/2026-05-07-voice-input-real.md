# SenseVoice Real API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mock API with a real SenseVoice-Small inference server running on the local GTX 1660 Ti (6GB VRAM), while keeping the mock as a test fallback.

**Architecture:** The existing `api.py` already loads the real model. We add a unified launcher (`run_server.py`) that selects real vs mock mode via env var, add startup health checks, VRAM guards, Windows batch scripts, and a real-model test. The client gets an API connectivity check on startup.

**Tech Stack:** Python 3.10+, PyTorch, FastAPI, Uvicorn, ModelScope, FunASR, SenseVoiceSmall, pynput, sounddevice, pystray, requests.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `api.py` | Modify | FastAPI app with real model loading; add mock env check, startup health check, VRAM guard |
| `run_server.py` | Create | Unified launcher: reads `SENSEVOICE_MOCK`, starts real or mock server |
| `start_server.bat` | Create | Windows launcher for real server (venv + uvicorn) |
| `start_mock.bat` | Create | Windows launcher for mock server (venv + uvicorn) |
| `test_api_real.py` | Create | Verify real model loads on GPU/CPU and inference returns text |
| `voice_input_client.py` | Modify | Add API connectivity check on startup with tray tooltip warning |

---

### Task 1: Unified Server Launcher (`run_server.py`)

**Files:**
- Create: `run_server.py`

**Context:** Currently there is no single entry point. `api.py` and `mock_api.py` are separate files. We need one launcher that picks the right mode.

- [ ] **Step 1: Write `run_server.py`**

```python
"""Unified launcher for SenseVoice API server.

Environment:
    SENSEVOICE_MOCK=1  -> launch mock_api.py
    SENSEVOICE_DEVICE  -> cuda device (default: cuda:0, fallback cpu)
"""
import os
import sys
import uvicorn

MOCK = os.getenv("SENSEVOICE_MOCK", "0") == "1"
HOST = os.getenv("SENSEVOICE_HOST", "127.0.0.1")
PORT = int(os.getenv("SENSEVOICE_PORT", "50000"))

if MOCK:
    print("[Launcher] MOCK mode enabled. Starting mock API...")
    app_module = "mock_api:app"
else:
    print("[Launcher] REAL mode. Starting SenseVoice API...")
    app_module = "api:app"

if __name__ == "__main__":
    uvicorn.run(app_module, host=HOST, port=PORT, log_level="info")
```

- [ ] **Step 2: Verify launcher syntax**

Run: `python -m py_compile run_server.py`
Expected: No output (success).

- [ ] **Step 3: Commit**

```bash
git add run_server.py
git commit -m "feat: add unified server launcher for real/mock mode"
```

---

### Task 2: Windows Batch Scripts

**Files:**
- Create: `start_server.bat`
- Create: `start_mock.bat`

**Context:** User is on Windows 11. Batch scripts make startup one double-click away.

- [ ] **Step 1: Write `start_server.bat`**

```batch
@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run: python -m venv .venv
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
set SENSEVOICE_MOCK=0
set SENSEVOICE_DEVICE=cuda:0
python run_server.py
pause
```

- [ ] **Step 2: Write `start_mock.bat`**

```batch
@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run: python -m venv .venv
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
set SENSEVOICE_MOCK=1
python run_server.py
pause
```

- [ ] **Step 3: Commit**

```bash
git add start_server.bat start_mock.bat
git commit -m "feat: add Windows batch launchers for real and mock server"
```

---

### Task 3: Modify `api.py` — Mock Env Check, Health Check, VRAM Guard

**Files:**
- Modify: `api.py`

**Context:** The existing `api.py` loads the model unconditionally at import time. We need to:
1. Allow `SENSEVOICE_MOCK=1` to short-circuit to mock logic (so `run_server.py` can use one module).
2. Add a `/health` endpoint.
3. Add VRAM guard (`empty_cache()` after inference).
4. Add warm-up inference on startup.

- [ ] **Step 1: Modify imports and mock short-circuit**

Replace the top of `api.py` (lines 1-33) with:

```python
import os, re
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from typing_extensions import Annotated
from typing import List
from enum import Enum
from io import BytesIO

TARGET_FS = 16000

# Mock mode short-circuit -----------------------------------------------------
if os.getenv("SENSEVOICE_MOCK", "0") == "1":
    from mock_api import app  # re-export mock app
    import uvicorn
    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=50000)
    raise SystemExit(0)  # stop further execution when imported as module
# -----------------------------------------------------------------------------

import torch
import torchaudio
from model import SenseVoiceSmall
from funasr.utils.postprocess_utils import rich_transcription_postprocess


class Language(str, Enum):
    auto = "auto"
    zh = "zh"
    en = "en"
    yue = "yue"
    ja = "ja"
    ko = "ko"
    nospeech = "nospeech"


device = os.getenv("SENSEVOICE_DEVICE", "cuda:0")
model_dir = "iic/SenseVoiceSmall"

# VRAM guard settings
torch.backends.cudnn.benchmark = False

print(f"[SenseVoice] Loading model from {model_dir} on {device} ...")
try:
    m, kwargs = SenseVoiceSmall.from_pretrained(model=model_dir, device=device)
    m.eval()
    print("[SenseVoice] Model loaded successfully.")
except Exception as e:
    print(f"[SenseVoice] Failed to load on {device}: {e}")
    device = "cpu"
    print(f"[SenseVoice] Falling back to CPU ...")
    m, kwargs = SenseVoiceSmall.from_pretrained(model=model_dir, device=device)
    m.eval()
    print("[SenseVoice] Model loaded on CPU.")

regex = r"<\|.*\|>"

app = FastAPI()
```

- [ ] **Step 2: Add health endpoint and warm-up**

Insert after `app = FastAPI()` (new lines):

```python
@app.get("/health")
async def health():
    return {"status": "ok", "device": device, "model": model_dir}


# Warm-up inference to trigger lazy initialisation
print("[SenseVoice] Warming up model with dummy audio ...")
try:
    dummy = torch.zeros(1, 16000).to(device)
    _ = m.inference(
        data_in=[dummy],
        language="auto",
        use_itn=False,
        ban_emo_unk=False,
        key=["warmup"],
        fs=TARGET_FS,
        **kwargs,
    )
    print("[SenseVoice] Warm-up complete.")
except Exception as e:
    print(f"[SenseVoice] Warm-up warning (non-fatal): {e}")
```

- [ ] **Step 3: Add VRAM guard to inference endpoint**

In the `/api/v1/asr` endpoint, after `res = m.inference(...)` add:

```python
    # VRAM guard: free cached memory after each request
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
```

The full endpoint should look like:

```python
@app.post("/api/v1/asr")
async def turn_audio_to_text(
    files: Annotated[List[UploadFile], File(description="wav or mp3 audios in 16KHz")],
    keys: Annotated[str, Form(description="name of each audio joined with comma")] = None,
    lang: Annotated[Language, Form(description="language of audio content")] = "auto",
):
    audios = []
    for file in files:
        file_io = BytesIO(await file.read())
        data_or_path_or_list, audio_fs = torchaudio.load(file_io)

        if audio_fs != TARGET_FS:
            resampler = torchaudio.transforms.Resample(orig_freq=audio_fs, new_freq=TARGET_FS)
            data_or_path_or_list = resampler(data_or_path_or_list)

        data_or_path_or_list = data_or_path_or_list.mean(0)
        audios.append(data_or_path_or_list)

    if lang == "":
        lang = "auto"

    if not keys:
        key = [f.filename for f in files]
    else:
        key = keys.split(",")

    res = m.inference(
        data_in=audios,
        language=lang,
        use_itn=False,
        ban_emo_unk=False,
        key=key,
        fs=TARGET_FS,
        **kwargs,
    )

    # VRAM guard
    if device.startswith("cuda"):
        torch.cuda.empty_cache()

    if len(res) == 0:
        return {"result": []}
    for it in res[0]:
        it["raw_text"] = it["text"]
        it["clean_text"] = re.sub(regex, "", it["text"], 0, re.MULTILINE)
        it["text"] = rich_transcription_postprocess(it["text"])
    return {"result": res[0]}
```

- [ ] **Step 4: Verify syntax**

Run: `python -m py_compile api.py`
Expected: No output (success). Note: this will attempt model download on first run; syntax check alone is sufficient here.

- [ ] **Step 5: Commit**

```bash
git add api.py
git commit -m "feat: add health endpoint, VRAM guard, auto-fallback, mock env short-circuit"
```

---

### Task 4: Add API Connectivity Check to Client

**Files:**
- Modify: `voice_input_client.py`

**Context:** The client currently assumes the API is running. We add a lightweight connectivity check on startup with a tray tooltip if unreachable.

- [ ] **Step 1: Add `check_api` function**

Insert after `type_text` function (before `class VADAudio`):

```python
def check_api(api_url: str, timeout: float = 3.0) -> bool:
    """Check if the API server is reachable."""
    try:
        health_url = api_url.replace("/api/v1/asr", "/health")
        resp = requests.get(health_url, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False
```

- [ ] **Step 2: Add startup check in `VoiceInputApp.run`**

Inside `VoiceInputApp.run`, after `print("SenseVoice 语音输入客户端已启动")`, add:

```python
        # API connectivity check
        if not check_api(self.config["api_url"]):
            print("[WARNING] API server not reachable at", self.config["api_url"])
            if self.icon:
                self.icon.notify("API 服务器未连接，请启动服务器", "SenseVoice 语音输入")
        else:
            print("[OK] API server connected.")
```

- [ ] **Step 3: Verify syntax**

Run: `python -m py_compile voice_input_client.py`
Expected: No output (success).

- [ ] **Step 4: Commit**

```bash
git add voice_input_client.py
git commit -m "feat: add API connectivity check on client startup"
```

---

### Task 5: Real Model Test (`test_api_real.py`)

**Files:**
- Create: `test_api_real.py`

**Context:** We need a test that verifies the real model loads and produces transcription, without relying on the full E2E flow.

- [ ] **Step 1: Write the test**

```python
"""Test real SenseVoice model loading and inference."""
import sys
import os
import numpy as np

# Ensure we can import api.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_model_loads():
    """Verify model loads without error."""
    # Import after setting env to avoid mock short-circuit
    os.environ.setdefault("SENSEVOICE_DEVICE", "cpu")  # safe for CI
    import api
    assert api.m is not None
    assert api.device in ("cpu", "cuda:0")
    print("[PASS] Model loads on", api.device)


def test_inference_returns_text():
    """Verify inference on dummy audio returns a result structure."""
    os.environ.setdefault("SENSEVOICE_DEVICE", "cpu")
    import importlib
    import api
    importlib.reload(api)  # re-import after env set

    import torch
    dummy = torch.zeros(1, 16000)
    res = api.m.inference(
        data_in=[dummy],
        language="auto",
        use_itn=False,
        ban_emo_unk=False,
        key=["test"],
        fs=16000,
        **api.kwargs,
    )
    assert len(res) > 0
    assert "text" in res[0][0]
    print("[PASS] Inference returns text:", res[0][0]["text"])


def test_health_endpoint():
    """FastAPI health endpoint exists (requires app instance)."""
    from fastapi.testclient import TestClient
    os.environ.setdefault("SENSEVOICE_DEVICE", "cpu")
    import importlib
    import api
    importlib.reload(api)

    client = TestClient(api.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    print("[PASS] /health returns:", data)


if __name__ == "__main__":
    test_model_loads()
    test_inference_returns_text()
    test_health_endpoint()
    print("\nAll real-model tests passed!")
```

- [ ] **Step 2: Verify syntax**

Run: `python -m py_compile test_api_real.py`
Expected: No output (success).

- [ ] **Step 3: Commit**

```bash
git add test_api_real.py
git commit -m "test: add real model loading and inference tests"
```

---

### Task 6: Update E2E Test for Real Mode

**Files:**
- Modify: `e2e_test.py`

**Context:** The existing E2E test only tests client internals. We add a mode that actually calls the running server.

- [ ] **Step 1: Add server-aware E2E test**

Append to the bottom of `e2e_test.py` (before `if __name__ == "__main__"`):

```python
def test_real_api_with_silent_audio():
    """If a real server is running, verify it accepts audio and returns JSON."""
    import requests
    api_url = "http://localhost:50000/api/v1/asr"
    try:
        resp = requests.get("http://localhost:50000/health", timeout=2)
    except Exception:
        print("[SKIP] No server running at localhost:50000")
        return True

    # Create a 1-second silent WAV in memory
    import io, wave, struct
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
    buf.seek(0)

    files = {"files": ("silent.wav", buf, "audio/wav")}
    data = {"lang": "auto"}
    resp = requests.post(api_url, files=files, data=data, timeout=30)
    assert resp.status_code == 200
    result = resp.json()
    assert "result" in result
    print("[PASS] Real API returned:", result)
    return True
```

- [ ] **Step 2: Update main block to call new test**

Replace the `if __name__ == "__main__"` block with:

```python
if __name__ == "__main__":
    print("Starting SenseVoice Voice Input E2E Tests")
    print("Mock API running at: http://localhost:50000")
    print()

    try:
        test_push_to_talk_flow()
        test_streaming_toggle()
        test_icon_states()
        test_real_api_with_silent_audio()

        print("\n" + "=" * 50)
        print("ALL E2E TESTS PASSED")
        print("=" * 50)
    except Exception as e:
        print(f"\nE2E TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
```

- [ ] **Step 3: Verify syntax**

Run: `python -m py_compile e2e_test.py`
Expected: No output (success).

- [ ] **Step 4: Commit**

```bash
git add e2e_test.py
git commit -m "test: add real API E2E test with silent audio"
```

---

### Task 7: Final Integration Verification

**Files:**
- All of the above

- [ ] **Step 1: Run unit tests**

Run: `python test_voice_input.py`
Expected: All tests pass.

- [ ] **Step 2: Run real model tests (CPU mode)**

Run: `set SENSEVOICE_DEVICE=cpu && python test_api_real.py`
Expected: Model downloads (first time), then all tests pass.

- [ ] **Step 3: Start mock server and verify**

Run (in one terminal):
```batch
set SENSEVOICE_MOCK=1
python run_server.py
```

In another terminal:
```batch
curl http://localhost:50000/health
```
Expected: `{"status":"ok"}` (mock health is same shape).

```batch
curl -X POST -F "files=@silent.wav" -F "lang=auto" http://localhost:50000/api/v1/asr
```
Expected: JSON with random mock text.

- [ ] **Step 4: Start real server and verify (GPU)**

Run (in one terminal):
```batch
set SENSEVOICE_MOCK=0
set SENSEVOICE_DEVICE=cuda:0
python run_server.py
```

In another terminal:
```batch
curl http://localhost:50000/health
```
Expected: `{"status":"ok","device":"cuda:0","model":"iic/SenseVoiceSmall"}`.

```batch
curl -X POST -F "files=@silent.wav" -F "lang=auto" http://localhost:50000/api/v1/asr
```
Expected: JSON with empty or near-empty transcription (silent audio).

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: integrate real SenseVoice API with mock fallback"
```

---

## Self-Review

### Spec Coverage Check
- [x] Model loading & runtime → Task 3 (api.py modifications)
- [x] API server with mock env check → Task 3
- [x] Health endpoint → Task 3
- [x] VRAM guard → Task 3
- [x] Client integration → Task 4
- [x] Mock fallback → Task 1 + Task 2
- [x] Testing → Task 5 + Task 6
- [x] Deployment scripts → Task 2

### Placeholder Scan
- No "TBD", "TODO", or "implement later" found.
- No vague "add error handling" steps.
- Every step has exact code or exact command.

### Type Consistency
- `SENSEVOICE_MOCK` env var used consistently across `run_server.py`, `api.py`, batch files.
- `SENSEVOICE_DEVICE` env var used in `api.py`, batch files, tests.
- `api_url` format consistent between client and tests.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-07-voice-input-real.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach do you prefer?
