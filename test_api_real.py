"""Test real SenseVoice model loading and inference.

These tests run api.py in subprocesses to isolate heavy import-time side effects
(model loading, warm-up inference) from each other and from the test process.
"""
import os
import sys
import subprocess
import json

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _run_api_script(code: str, env: dict = None) -> subprocess.CompletedProcess:
    """Run a Python snippet with api.py imported in a subprocess."""
    full_code = f"""
import sys
sys.path.insert(0, {repr(PROJECT_DIR)})
{code}
"""
    env_vars = os.environ.copy()
    env_vars.setdefault("SENSEVOICE_DEVICE", "cpu")
    env_vars.pop("SENSEVOICE_MOCK", None)
    if env:
        env_vars.update(env)
    return subprocess.run(
        [sys.executable, "-c", full_code],
        capture_output=True,
        text=True,
        env=env_vars,
        cwd=PROJECT_DIR,
    )


def test_model_loads():
    """Verify model loads without error."""
    result = _run_api_script("""
import api
assert api.m is not None, "Model should be loaded"
assert api.device in ("cpu", "cuda:0"), f"Unexpected device: {api.device}"
print("PASS test_model_loads")
""")
    assert result.returncode == 0, f"Model load failed:\n{result.stderr}"
    assert "PASS test_model_loads" in result.stdout
    print("[PASS] test_model_loads")


def test_inference_returns_text():
    """Verify inference on dummy audio returns a result structure."""
    result = _run_api_script("""
import api
import torch

dummy = torch.zeros(32000)  # 2 seconds at 16kHz, 1D tensor for fbank
res = api.m.inference(
    data_in=[dummy],
    language="auto",
    use_itn=False,
    ban_emo_unk=False,
    key=["test"],
    fs=16000,
    **api.kwargs,
)
assert len(res) > 0, "Inference should return non-empty result"
assert "text" in res[0][0], f"Expected 'text' key, got {res[0][0].keys()}"
print("PASS test_inference_returns_text")
""")
    assert result.returncode == 0, f"Inference failed:\n{result.stderr}"
    assert "PASS test_inference_returns_text" in result.stdout
    print("[PASS] test_inference_returns_text")


def test_health_endpoint():
    """Verify /health endpoint returns correct JSON."""
    result = _run_api_script("""
import api
from fastapi.testclient import TestClient

client = TestClient(api.app)
response = client.get("/health")
assert response.status_code == 200, f"Expected 200, got {response.status_code}"
data = response.json()
assert data["status"] == "ok", f"Expected status 'ok', got {data.get('status')}"
print("PASS test_health_endpoint")
""")
    assert result.returncode == 0, f"Health endpoint failed:\n{result.stderr}"
    assert "PASS test_health_endpoint" in result.stdout
    print("[PASS] test_health_endpoint")


if __name__ == "__main__":
    test_model_loads()
    test_inference_returns_text()
    test_health_endpoint()
    print("\nAll real-model tests passed!")
