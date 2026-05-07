# SenseVoice Real API Design

## Overview
Replace the mock API (`mock_api.py`) with a real SenseVoice-Small inference server running on the local GTX 1660 Ti (6GB VRAM), while keeping the mock as a test fallback.

## Context
- **Current state**: `api.py` loads `SenseVoiceSmall` from `iic/SenseVoiceSmall` on `cuda:0`, but no venv, no model download automation, no startup script.
- **Mock state**: `mock_api.py` exists for testing.
- **Client**: `voice_input_client.py` calls `http://localhost:50000/api/v1/asr`.
- **GPU**: GTX 1660 Ti, 6GB VRAM (~1.3GB used by desktop), CUDA 13.2.

## Architecture

```
┌─────────────────┐      HTTP POST      ┌──────────────────┐
│  voice_input_   │ ──────────────────► │   api.py (real)  │
│  client.py      │   /api/v1/asr       │  or mock_api.py  │
│  (system tray)  │                     │   (FastAPI)      │
└─────────────────┘                     └────────┬─────────┘
                                                 │
                                          ┌──────▼──────┐
                                          │  model.onnx │
                                          │  OR PyTorch │
                                          │  (GPU/CPU)  │
                                          └─────────────┘
```

## Design Decisions

### 1. Model Loading & Runtime
- **Default**: PyTorch `SenseVoiceSmall.from_pretrained()` on `cuda:0`.
- **VRAM guard**: Set `torch.backends.cudnn.benchmark = False` and `empty_cache()` after each inference to keep VRAM < 3GB.
- **Fallback**: If CUDA unavailable or OOM, auto-fallback to CPU with a logged warning.
- **Model download**: `modelscope` will auto-download `iic/SenseVoiceSmall` on first run (~300MB).

### 2. API Server (`api.py`)
- Keep the existing FastAPI structure.
- Add `SENSEVOICE_MOCK=1` env var to load `mock_api.py` logic instead.
- Add startup health check: print model device and a sample inference to verify it works.
- Bind to `127.0.0.1:50000` (localhost only, as requested).

### 3. Client Integration
- `voice_input_client.py` stays unchanged — it already talks to `http://localhost:50000/api/v1/asr`.
- Add a connection check on startup: if API is unreachable, show a tray tooltip warning.

### 4. Mock Fallback
- Keep `mock_api.py` as-is.
- Add a unified launcher script `run_server.py` that checks `SENSEVOICE_MOCK` and starts the right app.

### 5. Testing
- `test_voice_input.py`: unit tests (no change needed).
- `e2e_test.py`: add a real-mode E2E test that starts the server, sends a real WAV, and checks for non-empty text.
- Add `test_api_real.py`: verify model loads and inference works.

### 6. Deployment Scripts
- `start_server.bat` / `start_server.sh`: activate venv, set env vars, run `uvicorn api:app`.
- `start_mock.bat` / `start_mock.sh`: set `SENSEVOICE_MOCK=1`, run mock.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `api.py` | Modify | Add mock env check, startup health check, VRAM guard |
| `run_server.py` | Create | Unified launcher for real/mock mode |
| `start_server.bat` | Create | Windows launcher for real server |
| `start_mock.bat` | Create | Windows launcher for mock server |
| `test_api_real.py` | Create | Verify real model loads and infers |
| `voice_input_client.py` | Modify | Add API connectivity check on startup |

## Risk Mitigation
- **OOM on 6GB**: `torch.cuda.empty_cache()` after every request; fallback to CPU if CUDA OOM.
- **Model download failure**: `modelscope` caches to `~/.cache/modelscope`; pre-download in setup script.
- **Slow first inference**: Warm-up with a dummy audio tensor on startup.

## Success Criteria
- [ ] `start_server.bat` launches real API, loads model on GPU, responds to `/api/v1/asr` with real transcription.
- [ ] `start_mock.bat` launches mock API, responds with random text.
- [ ] Client connects and transcribes live microphone audio into any text field.
- [ ] E2E test passes for both real and mock modes.
