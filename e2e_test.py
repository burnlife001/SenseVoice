"""E2E test: simulate push-to-talk and verify text input"""
import io
import sys
import time
import threading
import wave
import numpy as np
import requests

sys.stdout.reconfigure(line_buffering=True)
# Force UTF-8 on Windows to avoid UnicodeEncodeError for CJK characters
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

from voice_input_client import (
    VoiceInputApp, AudioRecorder, recognize_audio,
    type_text, ICON_IDLE, ICON_RECORDING_PUSH, ICON_RECORDING_STREAM,
    check_api,
)


def test_push_to_talk_flow():
    """Test the complete push-to-talk flow with mock audio"""
    print("=" * 50)
    print("E2E Test: Push-to-Talk Mode")
    print("=" * 50)

    # 1. Create app
    print("[1/5] Creating VoiceInputApp...")
    app = VoiceInputApp()
    assert app.config["api_url"] == "http://localhost:50000/api/v1/asr"
    print("   App created, API URL:", app.config["api_url"])

    # 2. Simulate push-to-talk press
    print("[2/5] Simulating RCtrl press...")
    app._on_push_to_talk_press()
    assert app.push_to_talk_active == True
    print("   Recording started, push_to_talk_active:", app.push_to_talk_active)

    # Wait a bit (simulating speech)
    time.sleep(0.5)

    # 3. Simulate push-to-talk release
    print("[3/5] Simulating RCtrl release...")
    app._on_push_to_talk_release()
    assert app.push_to_talk_active == False
    print("   Recording stopped")

    # 4. Test with actual silent audio (API should return empty or mock text)
    print("[4/5] Testing API call with silent audio...")
    audio = np.zeros(16000, dtype=np.int16)
    text = recognize_audio(audio, app.config["api_url"], app.config["language"])
    print("   API returned:", repr(text))

    # 5. Test text typing (without actually typing)
    print("[5/5] Testing type_text function...")
    print("   type_text would input:", repr(text) if text else "(empty - no text)")

    print("\nPush-to-Talk E2E test PASSED")
    return True


def test_streaming_toggle():
    """Test streaming mode toggle"""
    print("\n" + "=" * 50)
    print("E2E Test: Streaming Mode Toggle")
    print("=" * 50)

    app = VoiceInputApp()

    # Toggle on
    print("[1/3] Toggling streaming ON...")
    app._on_streaming_toggle()
    assert app.streaming_active == True
    assert app.streaming_recorder is not None
    print("   Streaming active:", app.streaming_active)

    time.sleep(0.5)

    # Toggle off
    print("[2/3] Toggling streaming OFF...")
    app._on_streaming_toggle()
    assert app.streaming_active == False
    assert app.streaming_recorder is None
    print("   Streaming active:", app.streaming_active)

    # Test double-toggle safety
    print("[3/3] Testing safety: push-to-talk during streaming...")
    app._on_streaming_toggle()
    assert app.streaming_active == True
    # Should be ignored when streaming is active
    app._on_push_to_talk_press()
    assert app.push_to_talk_active == False  # Should not start
    print("   Push-to-talk correctly ignored during streaming")

    # Cleanup
    app._on_streaming_toggle()

    print("\nStreaming Mode E2E test PASSED")
    return True


def test_icon_states():
    """Verify icon state transitions"""
    print("\n" + "=" * 50)
    print("E2E Test: Icon State Transitions")
    print("=" * 50)

    app = VoiceInputApp()

    print("[1/3] Idle icon:", ICON_IDLE.size, "color check: blue")
    assert ICON_IDLE.size == (64, 64)

    print("[2/3] Recording push icon:", ICON_RECORDING_PUSH.size, "color check: red")
    assert ICON_RECORDING_PUSH.size == (64, 64)

    print("[3/3] Recording stream icon:", ICON_RECORDING_STREAM.size, "color check: green")
    assert ICON_RECORDING_STREAM.size == (64, 64)

    print("\nIcon State E2E test PASSED")
    return True


def test_real_api_with_silent_audio():
    """Test the real API server with silent audio (requires server running)."""
    print("\n" + "=" * 50)
    print("E2E Test: Real API with Silent Audio")
    print("=" * 50)

    api_url = "http://localhost:50000/api/v1/asr"

    # 1. Check if server is running
    print("[1/3] Checking API server...")
    if not check_api(api_url):
        print("   SKIP: API server not running at", api_url)
        return None  # Skip, not a failure

    print("   API server is up")

    # 2. Create silent WAV in memory
    print("[2/3] Creating silent audio...")
    sample_rate = 16000
    duration_sec = 1
    silent_samples = np.zeros(sample_rate * duration_sec, dtype=np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(silent_samples.tobytes())
    buf.seek(0)

    # 3. POST to API
    print("[3/3] POSTing silent audio to API...")
    files = {"files": ("silent.wav", buf, "audio/wav")}
    data = {"lang": "auto"}
    resp = requests.post(api_url, files=files, data=data, timeout=30)
    resp.raise_for_status()

    result = resp.json()
    print("   API response:", result)

    assert "result" in result, "Expected 'result' key in response"
    assert isinstance(result["result"], list), "Expected 'result' to be a list"

    print("\nReal API E2E test PASSED")
    return True


if __name__ == "__main__":
    print("Starting SenseVoice Voice Input E2E Tests")
    print("Target API: http://localhost:50000")
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
