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
