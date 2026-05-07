"""Mock SenseVoice API for E2E testing"""
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from typing import List
import random

app = FastAPI()

MOCK_RESPONSES = [
    "你好，这是语音输入测试",
    "今天天气真不错",
    "SenseVoice 语音识别效果很棒",
    "我正在测试语音输入功能",
    "你好世界",
]


@app.get("/", response_class=HTMLResponse)
async def root():
    return "<html><body><a href='./docs'>API Docs</a></body></html>"


@app.post("/api/v1/asr")
async def mock_asr(
    files: List[UploadFile] = File(...),
    keys: str = Form(None),
    lang: str = Form("auto"),
):
    # Read and discard file content
    for f in files:
        await f.read()

    result = []
    for i, f in enumerate(files):
        text = random.choice(MOCK_RESPONSES)
        result.append({
            "key": f.filename,
            "text": text,
            "raw_text": text,
            "clean_text": text,
        })

    return {"result": result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=50000)
