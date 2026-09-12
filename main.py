"""FastAPI wrapper around the agent pipeline.

    uvicorn main:app --reload --port 8000
"""
from pathlib import Path
import shutil
import tempfile

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
from enhance import Pipeline


app = FastAPI(title="Lowlight Agents API")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")


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
            str(input_path),
            output_path=str(output_path),
            report_path=str(report_path),
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
