"""FastAPI wrapper around the agent pipeline.

    uvicorn main:app --reload --port 8000
"""
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import config
from agents.orchestrator import Pipeline

app = FastAPI(title="Lowlight Agents API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "message": "Low-Light Image Enhancement API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/enhance")
async def enhance(
    file: UploadFile = File(...),
    max_reflections: int = Query(config.MAX_REFLECTION_ROUNDS, ge=0, le=5),
):
    suffix = Path(file.filename or "input.jpg").suffix or ".jpg"
    work_dir = Path(tempfile.mkdtemp())
    input_path = work_dir / f"input{suffix}"
    output_path = work_dir / f"enhanced{suffix}"
    report_path = work_dir / "report.md"

    with input_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    pipeline = Pipeline(max_reflection_rounds=max_reflections)
    try:
        report = pipeline.run(
            str(input_path), output_path=str(output_path), report_path=str(report_path)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return FileResponse(
        report.output_path,
        media_type="image/jpeg",
        filename=f"enhanced{suffix}",
        headers={
            "X-Final-Score": str(report.final_overall_score),
            "X-Used-Safety-Preset": str(report.used_safety_preset),
        },
    )
