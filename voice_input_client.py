"""SenseVoice 全局语音输入客户端"""
import os
import sys
import json
import threading
import time
import io
import tempfile
from typing import Optional, Callable

# Fix Windows GBK console encoding for emoji/unicode output
if sys.platform == "win32":
    import codecs
    if sys.stdout.encoding.lower() in ("gbk", "cp936", "cp1252"):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer)
    if sys.stderr.encoding.lower() in ("gbk", "cp936", "cp1252"):
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer)

import numpy as np
import sounddevice as sd
import requests
import pyautogui
from pynput import keyboard
import pystray
from PIL import Image, ImageDraw

# 配置
DEFAULT_CONFIG = {
    "hotkey_push_to_talk": "right_ctrl",
    "hotkey_streaming": "fn",
    "api_url": "http://localhost:50000/api/v1/asr",
    "language": "auto",
    "vad_aggressiveness": 2,
    "input_delay_ms": 50,
    "input_method": "clipboard",  # "clipboard" or "typewrite"
    "sample_rate": 16000,
    "channels": 1,
    "dtype": "int16",
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def create_icon(color: str, size: int = 64) -> Image.Image:
    """生成纯色圆形托盘图标"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
    )
    return img


ICON_IDLE = create_icon("#4a90d9")   # 蓝色 - 空闲
ICON_RECORDING_PUSH = create_icon("#e74c3c")  # 红色 - 按键录音中
ICON_RECORDING_STREAM = create_icon("#2ecc71")  # 绿色 - 流式听写中


class AudioRecorder:
    """基于 sounddevice 的音频录制器"""

    def __init__(self, sample_rate: int = 16000, channels: int = 1, dtype: str = "int16"):
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.frames: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._recording = False

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            print(f"Audio status: {status}")
        if self._recording:
            self.frames.append(indata.copy())

    def start(self):
        self.frames = []
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self.frames:
            return np.array([], dtype=self.dtype)
        return np.concatenate(self.frames, axis=0)

    def is_recording(self) -> bool:
        return self._recording


def recognize_audio(audio_data: np.ndarray, api_url: str, language: str = "auto") -> str:
    """调用 SenseVoice API 识别音频"""
    if audio_data.size == 0:
        return ""

    # 写入临时 wav 文件
    import wave
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_data.tobytes())

    try:
        with open(tmp_path, "rb") as f:
            files = {"files": ("audio.wav", f, "audio/wav")}
            data = {"lang": language}
            resp = requests.post(api_url, files=files, data=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        texts = [item.get("text", "") for item in result.get("result", [])]
        return " ".join(t for t in texts if t)
    except Exception as e:
        print(f"API error: {e}")
        return ""
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _type_via_clipboard(text: str) -> bool:
    """通过剪贴板粘贴输入文本（Windows 最可靠的中文输入方式）

    注意：这会覆盖当前剪贴板内容，不尝试恢复。
    使用 pyperclip 如果可用，否则用原生 Windows API。
    """
    try:
        import pyperclip
        pyperclip.copy(text)
    except ImportError:
        # 回退到原生 Windows API
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        if not user32.OpenClipboard(None):
            return False
        user32.EmptyClipboard()
        text_bytes = text.encode('utf-16-le')
        handle = kernel32.GlobalAlloc(0x2002, len(text_bytes) + 2)
        if not handle:
            user32.CloseClipboard()
            return False
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, text_bytes, len(text_bytes))
        ctypes.memset(ptr + len(text_bytes), 0, 2)
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(13, handle)  # CF_UNICODETEXT = 13
        user32.CloseClipboard()

    # 粘贴: Ctrl+V
    pyautogui.keyDown('ctrl')
    pyautogui.keyDown('v')
    pyautogui.keyUp('v')
    pyautogui.keyUp('ctrl')

    return True


def type_text(text: str, delay_ms: int = 50, use_clipboard: bool = True):
    """将文本输入到当前光标位置"""
    if not text:
        return
    # 延迟一小会儿，确保焦点窗口正确
    time.sleep(delay_ms / 1000.0)

    # 调试：打印当前前台窗口信息
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        print(f"[TYPE] Target window: {buf.value}")
    except Exception as e:
        print(f"[TYPE] GetForegroundWindow failed: {e}")

    print(f"[TYPE] Typing text: {repr(text)}")

    # 优先使用剪贴板粘贴（中文最可靠），失败则回退到 pyautogui.typewrite
    if use_clipboard and _type_via_clipboard(text):
        print("[TYPE] Done (clipboard)")
        return

    # 回退到 pyautogui.typewrite
    pyautogui.typewrite(text, interval=0.01)
    print("[TYPE] Done (typewrite)")


def check_api(api_url: str, timeout: float = 3.0) -> bool:
    """检查 API 服务器是否可用"""
    from urllib.parse import urljoin, urlparse
    parsed = urlparse(api_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    health_url = urljoin(base + "/", "health")
    try:
        resp = requests.get(health_url, timeout=timeout)
        if resp.status_code != 200:
            return False
        data = resp.json()
        return data.get("status") == "ok"
    except Exception:
        return False


class VADAudio:
    """基于 webrtcvad 的语音活动检测"""

    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000):
        import webrtcvad
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.frame_duration_ms = 30  # 30ms
        self.frame_bytes = int(sample_rate * self.frame_duration_ms / 1000) * 2  # 16bit

    def is_speech(self, frame: bytes) -> bool:
        return self.vad.is_speech(frame, self.sample_rate)

    def frame_generator(self, audio_bytes: bytes):
        """将音频字节流切分为 VAD 帧"""
        offset = 0
        while offset + self.frame_bytes <= len(audio_bytes):
            yield audio_bytes[offset:offset + self.frame_bytes]
            offset += self.frame_bytes


class StreamingRecorder:
    """流式录音器：持续录音，VAD 断句后回调"""

    def __init__(
        self,
        sample_rate: int = 16000,
        vad_aggressiveness: int = 2,
        padding_duration_ms: int = 300,
        on_utterance: Optional[Callable[[np.ndarray], None]] = None,
    ):
        self.sample_rate = sample_rate
        self.vad = VADAudio(vad_aggressiveness, sample_rate)
        self.padding_duration_ms = padding_duration_ms
        self.on_utterance = on_utterance
        self._running = False
        self._stream: Optional[sd.InputStream] = None
        self._thread: Optional[threading.Thread] = None

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            print(f"Stream status: {status}")
        # 将新数据放入队列
        self._audio_buffer.append(indata.copy())

    def _process_loop(self):
        """后台线程：处理音频缓冲区，VAD 断句"""
        import collections

        ring_buffer = collections.deque(maxlen=int(self.padding_duration_ms / self.vad.frame_duration_ms))
        triggered = False
        voiced_frames = []

        while self._running:
            if not self._audio_buffer:
                time.sleep(0.01)
                continue

            # 取出一帧音频
            frame_data = self._audio_buffer.pop(0)
            frame_bytes = frame_data.astype(np.int16).tobytes()

            # 按 VAD 帧大小处理
            for vad_frame in self.vad.frame_generator(frame_bytes):
                is_speech = self.vad.is_speech(vad_frame)

                if not triggered:
                    ring_buffer.append(vad_frame)
                    num_voiced = sum(1 for f in ring_buffer if self.vad.is_speech(f))
                    if num_voiced > 0.9 * ring_buffer.maxlen:
                        triggered = True
                        voiced_frames.extend(ring_buffer)
                        ring_buffer.clear()
                else:
                    voiced_frames.append(vad_frame)
                    ring_buffer.append(vad_frame)
                    num_unvoiced = sum(1 for f in ring_buffer if not self.vad.is_speech(f))
                    if num_unvoiced > 0.9 * ring_buffer.maxlen:
                        triggered = False
                        # 触发回调
                        if self.on_utterance and voiced_frames:
                            audio = np.frombuffer(b"".join(voiced_frames), dtype=np.int16)
                            self.on_utterance(audio)
                        voiced_frames = []
                        ring_buffer.clear()

        # 处理剩余音频
        if triggered and voiced_frames and self.on_utterance:
            audio = np.frombuffer(b"".join(voiced_frames), dtype=np.int16)
            self.on_utterance(audio)

    def start(self):
        self._audio_buffer = []
        self._running = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None


class VoiceInputApp:
    """语音输入客户端主控制器"""

    def __init__(self):
        self.config = load_config()
        self.icon: Optional[pystray.Icon] = None
        self.recorder = AudioRecorder(
            sample_rate=self.config["sample_rate"],
            channels=self.config["channels"],
            dtype=self.config["dtype"],
        )
        self.streaming_recorder: Optional[StreamingRecorder] = None
        self.push_to_talk_active = False
        self.streaming_active = False
        self._hotkey_listener: Optional[keyboard.Listener] = None

    def _set_icon(self, image: Image.Image):
        if self.icon:
            self.icon.icon = image

    def _on_push_to_talk_press(self):
        """按键模式：按下热键"""
        if self.streaming_active:
            return
        if not self.push_to_talk_active:
            self.push_to_talk_active = True
            self._set_icon(ICON_RECORDING_PUSH)
            self.recorder.start()
            print("[PUSH] Recording started")

    def _on_push_to_talk_release(self):
        """按键模式：释放热键"""
        if not self.push_to_talk_active:
            return
        self.push_to_talk_active = False
        self._set_icon(ICON_IDLE)
        audio = self.recorder.stop()
        print(f"[PUSH] Recording stopped, frames: {len(audio)}")

        if audio.size == 0:
            return

        text = recognize_audio(
            audio,
            self.config["api_url"],
            self.config["language"],
        )
        if text:
            print(f"[PUSH] Recognized: {text}")
            use_clipboard = self.config.get("input_method", "clipboard") == "clipboard"
            type_text(text, self.config["input_delay_ms"], use_clipboard=use_clipboard)
        else:
            print("[PUSH] No text recognized")

    def _on_streaming_toggle(self):
        """流式模式：切换开关"""
        if self.push_to_talk_active:
            return

        if not self.streaming_active:
            # 开启流式听写
            self.streaming_active = True
            self._set_icon(ICON_RECORDING_STREAM)
            print("[STREAM] Streaming started")

            def on_utterance(audio: np.ndarray):
                print(f"[STREAM] Utterance detected, frames: {len(audio)}")
                use_clipboard = self.config.get("input_method", "clipboard") == "clipboard"
                # 先输入占位符
                placeholder = " ... "
                type_text(placeholder, 10, use_clipboard=use_clipboard)

                text = recognize_audio(
                    audio,
                    self.config["api_url"],
                    self.config["language"],
                )
                if text:
                    print(f"[STREAM] Recognized: {text}")
                    # 选中占位符并替换
                    # placeholder 长度 = 5
                    pyautogui.keyDown('shift')
                    for _ in range(len(placeholder)):
                        pyautogui.keyDown('left')
                        pyautogui.keyUp('left')
                    pyautogui.keyUp('shift')
                    type_text(text + " ", 10, use_clipboard=use_clipboard)
                else:
                    # 删除占位符
                    for _ in range(len(placeholder)):
                        pyautogui.keyDown('backspace')
                        pyautogui.keyUp('backspace')

            self.streaming_recorder = StreamingRecorder(
                sample_rate=self.config["sample_rate"],
                vad_aggressiveness=self.config["vad_aggressiveness"],
                on_utterance=on_utterance,
            )
            self.streaming_recorder.start()
        else:
            # 关闭流式听写
            self.streaming_active = False
            self._set_icon(ICON_IDLE)
            if self.streaming_recorder:
                self.streaming_recorder.stop()
                self.streaming_recorder = None
            print("[STREAM] Streaming stopped")

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem("按键模式 (按住 RCtrl)", lambda: None, enabled=False),
            pystray.MenuItem("流式模式 (按 Fn 切换)", lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._on_exit),
        )

    def _on_exit(self):
        if self.push_to_talk_active:
            self._on_push_to_talk_release()
        if self.streaming_active:
            self._on_streaming_toggle()
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        if self.icon:
            self.icon.stop()

    def _parse_hotkey(self, hotkey_str: str) -> str:
        """将配置中的热键字符串转换为 pynput 格式"""
        parts = hotkey_str.lower().split("+")
        mapped = []
        for p in parts:
            p = p.strip()
            if p == "right_ctrl":
                mapped.append("<ctrl_r>")
            elif p == "left_ctrl":
                mapped.append("<ctrl_l>")
            elif p == "ctrl":
                mapped.append("<ctrl>")
            elif p == "alt":
                mapped.append("<alt>")
            elif p == "shift":
                mapped.append("<shift>")
            elif p == "fn":
                # Fn 键在 pynput 中通常映射为 media 或功能键，这里保留原样由 Listener 特殊处理
                mapped.append("<fn>")
            else:
                mapped.append(p)
        return "+".join(mapped)

    def run(self):
        # 启动托盘图标
        self.icon = pystray.Icon(
            "sensevoice_input",
            ICON_IDLE,
            "SenseVoice 语音输入",
            self._build_menu(),
        )

        # 启动热键监听
        print("Registering hotkeys: push=RCtrl (hold), stream=Fn (toggle)")

        # pynput GlobalHotKeys 不支持按住/释放，我们用 Listener 手动处理
        current_keys = set()

        def on_press(key):
            try:
                k = key.name.lower() if hasattr(key, "name") else str(key).lower()
            except AttributeError:
                k = str(key).lower()

            # 映射特殊键名
            if "right ctrl" in k or "ctrl_r" in k:
                k = "right_ctrl"
            elif "ctrl" in k and "right" not in k and "left" not in k:
                k = "ctrl"
            elif "alt" in k:
                k = "alt"
            elif k.startswith("key.f") and k[5:].isdigit():
                k = "fn"
            elif "fn" in k:
                k = "fn"

            current_keys.add(k)

            # 检查流式热键（切换）- Fn 键单独触发
            if k == "fn" and not self.push_to_talk_active:
                # 防止重复触发，简单去抖
                if not hasattr(self, "_last_stream_time") or time.time() - self._last_stream_time > 0.5:
                    self._last_stream_time = time.time()
                    self._on_streaming_toggle()
                return

            # 检查按键热键（按住）- 仅 RCtrl
            if k == "right_ctrl" and not self.streaming_active:
                self._on_push_to_talk_press()

        def on_release(key):
            try:
                k = key.name.lower() if hasattr(key, "name") else str(key).lower()
            except AttributeError:
                k = str(key).lower()

            if "right ctrl" in k or "ctrl_r" in k:
                k = "right_ctrl"
            elif k.startswith("key.f") and k[5:].isdigit():
                k = "fn"
            elif "fn" in k:
                k = "fn"

            current_keys.discard(k)

            # 释放右 Ctrl 时，如果按键模式激活则停止
            if k == "right_ctrl" and self.push_to_talk_active:
                self._on_push_to_talk_release()

        self._hotkey_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._hotkey_listener.start()

        print("SenseVoice 语音输入客户端已启动")
        if not check_api(self.config["api_url"]):
            print("[WARN] API server not connected.")
            if self.icon:
                self.icon.notify("API 服务器未连接，请启动服务器", "SenseVoice 语音输入")
        else:
            print("[OK] API server connected.")
        print("  按键模式: 按住 RCtrl 说话，释放识别")
        print("  流式模式: 按 Fn 开启/关闭智能听写")
        self.icon.run()


if __name__ == "__main__":
    app = VoiceInputApp()
    app.run()
