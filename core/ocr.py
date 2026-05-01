import json
import re
import time

import requests

OCR_JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
OCR_MODEL = "PaddleOCR-VL-1.5"


def extract_toc_via_ocr(pdf_path: str, token: str, progress_cb=None) -> str:
    """通过 PaddleOCR API 提取目录文本。progress_cb(msg) 用于回调进度。"""
    def notify(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    headers = {"Authorization": f"bearer {token}"}
    payload = json.dumps({
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    })

    notify("上传中...")
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            OCR_JOB_URL,
            headers=headers,
            data={"model": OCR_MODEL, "optionalPayload": payload},
            files={"file": f},
        )

    if resp.status_code != 200:
        raise RuntimeError(f"上传失败: {resp.text}")

    job_id = resp.json()["data"]["jobId"]
    notify("处理中，请稍候...")

    jsonl_url = _poll_until_done(job_id, headers)

    return _parse_jsonl(requests.get(jsonl_url).text)


def _poll_until_done(job_id: str, headers: dict) -> str:
    """轮询任务状态，完成后返回结果文件 URL。"""
    while True:
        resp = requests.get(f"{OCR_JOB_URL}/{job_id}", headers=headers)
        data = resp.json()["data"]
        if data["state"] == "done":
            return data["resultUrl"]["jsonUrl"]
        if data["state"] == "failed":
            raise RuntimeError(data["errorMsg"])
        time.sleep(2)


def _parse_jsonl(jsonl_text: str) -> str:
    """从 JSONL 结果中提取并清理目录文本。"""
    all_text = []
    for line in jsonl_text.strip().split("\n"):
        if not line.strip():
            continue
        for res in json.loads(line)["result"]["layoutParsingResults"]:
            cleaned = _clean_ocr_line(res["markdown"]["text"])
            if cleaned:
                all_text.append(cleaned)
    return "\n".join(all_text)


def _clean_ocr_line(text: str) -> str:
    """清理单段 OCR 文本：去除省略号、破折号等填充符，保留含页码的行。"""
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or not re.search(r"\d+", line) or len(line) <= 3:
            continue
        line = re.sub(r"[。．…·•⋯_＿—–-]{2,}|\.{2,}", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line and re.search(r"\d+", line):
            lines.append(line)
    return "\n".join(lines)
