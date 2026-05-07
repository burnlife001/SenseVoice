"""Quick unit tests for voice_input_client modules"""
import numpy as np
import wave
import tempfile
import os

from voice_input_client import (
    load_config, save_config, DEFAULT_CONFIG,
    create_icon, ICON_IDLE, ICON_RECORDING_PUSH, ICON_RECORDING_STREAM,
    AudioRecorder, recognize_audio, type_text,
    VADAudio, StreamingRecorder, VoiceInputApp,
)


def test_config():
    cfg = load_config()
    assert cfg["sample_rate"] == 16000
    assert cfg["api_url"] == "http://localhost:50000/api/v1/asr"
    print("[PASS] Config module")


def test_icons():
    assert ICON_IDLE.size == (64, 64)
    assert ICON_RECORDING_PUSH.size == (64, 64)
    assert ICON_RECORDING_STREAM.size == (64, 64)
    print("[PASS] Tray icons")


def test_audio_recorder():
    rec = AudioRecorder()
    assert rec.sample_rate == 16000
    assert rec.channels == 1
    assert not rec.is_recording()
    print("[PASS] AudioRecorder")


def test_wav_writing():
    audio = np.zeros(16000, dtype=np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.tobytes())
    size = os.path.getsize(tmp_path)
    assert size > 0
    os.remove(tmp_path)
    print("[PASS] WAV writing")


def test_api_client_offline():
    audio = np.zeros(16000, dtype=np.int16)
    # Use a port that is very unlikely to have anything listening
    result = recognize_audio(audio, "http://localhost:59999/api/v1/asr", "auto")
    assert result == ""  # API offline, should return empty string gracefully
    print("[PASS] API client offline handling")


def test_vad():
    vad = VADAudio(aggressiveness=2, sample_rate=16000)
    assert vad.frame_bytes == int(16000 * 30 / 1000) * 2
    print("[PASS] VADAudio")


def test_streaming_recorder():
    sr = StreamingRecorder()
    assert sr.sample_rate == 16000
    assert not sr._running
    print("[PASS] StreamingRecorder")


def test_voice_input_app():
    app = VoiceInputApp()
    assert app.config is not None
    assert not app.push_to_talk_active
    assert not app.streaming_active
    print("[PASS] VoiceInputApp")


if __name__ == "__main__":
    test_config()
    test_icons()
    test_audio_recorder()
    test_wav_writing()
    test_api_client_offline()
    test_vad()
    test_streaming_recorder()
    test_voice_input_app()
    print("\nAll tests passed!")
