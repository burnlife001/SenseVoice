# Set the device with environment, default is cuda:0
# export SENSEVOICE_DEVICE=cuda:1

import os
import re

if os.getenv("SENSEVOICE_MOCK") == "1":
    from mock_api import app
    raise SystemExit(0)

import torch
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.concurrency import run_in_threadpool
from typing_extensions import Annotated
from typing import List
from enum import Enum
import torchaudio
from model import SenseVoiceSmall
from funasr.utils.postprocess_utils import rich_transcription_postprocess
from io import BytesIO

TARGET_FS = 16000
MAX_FILE_SIZE_MB = 50


class Language(str, Enum):
    auto = "auto"
    zh = "zh"
    en = "en"
    yue = "yue"
    ja = "ja"
    ko = "ko"
    nospeech = "nospeech"


model_dir = "iic/SenseVoiceSmall"

# Disable cudnn benchmark for deterministic memory usage
torch.backends.cudnn.benchmark = False

_env_device = os.getenv("SENSEVOICE_DEVICE", "cuda:0")
try:
    m, kwargs = SenseVoiceSmall.from_pretrained(model=model_dir, device=_env_device)
    device = _env_device
    print(f"[SenseVoice] Model loaded on {device}")
except Exception as e:
    print(f"[SenseVoice] Failed to load on {_env_device}: {e}")
    print("[SenseVoice] Falling back to CPU")
    m, kwargs = SenseVoiceSmall.from_pretrained(model=model_dir, device="cpu")
    device = "cpu"
    print(f"[SenseVoice] Model loaded on {device}")

m.eval()

# Pre-compile regex for performance
EMO_REGEX = re.compile(r"<\|.*?\|>")

app = FastAPI()

# Warm-up inference with dummy audio
_dummy_audio = torch.zeros(TARGET_FS)
try:
    _ = m.inference(
        data_in=[_dummy_audio],
        language="auto",
        use_itn=False,
        ban_emo_unk=False,
        key=["warmup"],
        fs=TARGET_FS,
        **kwargs,
    )
    print("[SenseVoice] Warm-up inference done")
except Exception as e:
    print(f"[SenseVoice] Warm-up inference failed: {e}")


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <meta charset=utf-8>
            <title>Api information</title>
        </head>
        <body>
            <a href='./docs'>Documents of API</a>
        </body>
    </html>
    """


@app.get("/health")
async def health():
    return {"status": "ok", "device": device, "model": model_dir}


@app.post("/api/v1/asr")
async def turn_audio_to_text(
    files: Annotated[List[UploadFile], File(description="wav or mp3 audios in 16KHz")],
    keys: Annotated[str, Form(description="name of each audio joined with comma")] = None,
    lang: Annotated[Language, Form(description="language of audio content")] = "auto",
):
    # Validate file count and size
    if len(files) == 0:
        raise HTTPException(status_code=422, detail="No audio files provided")

    for file in files:
        if file.size is not None and file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"File '{file.filename}' exceeds {MAX_FILE_SIZE_MB}MB limit"
            )

    # Build keys list
    if not keys:
        key = [f.filename for f in files]
    else:
        key = keys.split(",")
        if len(key) != len(files):
            raise HTTPException(
                status_code=422,
                detail=f"keys count ({len(key)}) does not match files count ({len(files)})"
            )

    try:
        audios = []
        for file in files:
            file_io = BytesIO(await file.read())
            data_or_path_or_list, audio_fs = torchaudio.load(file_io)

            # transform to target sample
            if audio_fs != TARGET_FS:
                resampler = torchaudio.transforms.Resample(orig_freq=audio_fs, new_freq=TARGET_FS)
                data_or_path_or_list = resampler(data_or_path_or_list)

            data_or_path_or_list = data_or_path_or_list.mean(0)
            audios.append(data_or_path_or_list)

        # Offload inference to thread pool to avoid blocking the event loop
        res = await run_in_threadpool(
            m.inference,
            data_in=audios,
            language=lang,
            use_itn=False,
            ban_emo_unk=False,
            key=key,
            fs=TARGET_FS,
            **kwargs,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}")
    finally:
        # VRAM guard: free cached memory after each request
        if device.startswith("cuda"):
            torch.cuda.empty_cache()

    if len(res) == 0:
        return {"result": []}
    for it in res[0]:
        it["raw_text"] = it["text"]
        it["clean_text"] = EMO_REGEX.sub("", it["text"])
        it["text"] = rich_transcription_postprocess(it["text"])
    return {"result": res[0]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=50000)
