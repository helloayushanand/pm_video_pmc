"""FastAPI server — upload a dossier PDF, generate a video, download it."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from app.config import RUNS_DIR, create_project_directories, settings

logger = logging.getLogger("pm_video_web")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="PM Video Pipeline", version="0.1.0")


@app.on_event("startup")
async def _check_deps():
    import sys
    logger.info("Python executable: %s", sys.executable)
    for mod_name in ("openai", "pydantic", "tenacity"):
        try:
            __import__(mod_name)
            logger.info("  %s: OK", mod_name)
        except ImportError:
            logger.error("  %s: MISSING — run: pip install %s", mod_name, mod_name)

JOBS: dict[str, dict] = {}

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/api/upload")
async def upload_dossier(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    job_id = uuid.uuid4().hex[:12]
    create_project_directories()

    upload_dir = RUNS_DIR / f".uploads_{job_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / file.filename
    content = await file.read()
    pdf_path.write_bytes(content)

    JOBS[job_id] = {
        "status": "queued",
        "pdf_path": str(pdf_path),
        "filename": file.filename,
        "created_at": datetime.utcnow().isoformat(),
        "steps": [],
        "run_dir": None,
        "video_path": None,
        "error": None,
    }

    asyncio.create_task(_run_pipeline(job_id))
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def status_stream(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found.")

    async def event_generator():
        last_len = 0
        while True:
            job = JOBS[job_id]
            steps = job["steps"]
            if len(steps) > last_len:
                for step in steps[last_len:]:
                    yield {"event": "step", "data": json.dumps(step)}
                last_len = len(steps)

            if job["status"] in ("done", "failed"):
                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "status": job["status"],
                        "video_path": job.get("video_path"),
                        "error": job.get("error"),
                    }),
                }
                return
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@app.get("/api/status/{job_id}/poll")
async def status_poll(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found.")
    return JSONResponse(JOBS[job_id])


@app.get("/api/download/{job_id}")
async def download_video(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found.")
    job = JOBS[job_id]
    if job["status"] != "done" or not job.get("video_path"):
        raise HTTPException(400, "Video not ready.")
    video = Path(job["video_path"])
    if not video.exists():
        raise HTTPException(404, "Video file missing.")
    candidate = job.get("candidate_name", "candidate")
    return FileResponse(
        video,
        media_type="video/mp4",
        filename=f"{candidate}_video.mp4",
    )


def _emit(job_id: str, step_name: str, status: str, detail: str = ""):
    JOBS[job_id]["steps"].append({
        "step": step_name,
        "status": status,
        "detail": detail,
        "ts": datetime.utcnow().isoformat(),
    })


async def _run_pipeline(job_id: str):
    """Run the simplified DSL pipeline in a background thread."""
    job = JOBS[job_id]
    job["status"] = "running"
    current_step = None

    try:
        pdf_path = job["pdf_path"]

        # Step 1: Prepare document
        current_step = "prepare_document"
        _emit(job_id, current_step, "running", "Preparing PDF pages…")
        run_dir = await asyncio.to_thread(_step_prepare, pdf_path)
        job["run_dir"] = str(run_dir)
        _emit(job_id, current_step, "done")

        # Step 2: Extract dossier
        current_step = "extract_dossier"
        _emit(job_id, current_step, "running", "Extracting dossier with AI…")
        await asyncio.to_thread(_step_extract, run_dir)
        _emit(job_id, current_step, "done")

        # Step 3: Validate extraction
        current_step = "validate_extraction"
        _emit(job_id, current_step, "running", "Validating extracted data…")
        await asyncio.to_thread(_step_validate, run_dir)
        _emit(job_id, current_step, "done")

        # Step 4: Select video content
        current_step = "select_video_content"
        _emit(job_id, current_step, "running", "Selecting video content…")
        await asyncio.to_thread(_step_select_content, run_dir)
        _emit(job_id, current_step, "done")

        # Step 5: Generate DSL scenes
        current_step = "generate_scenes"
        _emit(job_id, current_step, "running", "Designing scenes with AI…")
        video_spec = await asyncio.to_thread(_step_generate_scenes, run_dir)
        job["candidate_name"] = video_spec.candidate_name
        _emit(
            job_id,
            current_step,
            "done",
            f"{len(video_spec.scenes)} scenes, "
            f"{sum(s.duration_seconds for s in video_spec.scenes):.0f}s total",
        )

        # Step 6: Render video
        current_step = "render_video"
        _emit(job_id, current_step, "running", "Rendering video with Remotion…")
        video_path = await asyncio.to_thread(_step_render, run_dir, video_spec)
        job["video_path"] = str(video_path)
        _emit(job_id, current_step, "done", f"{video_path.stat().st_size / 1_048_576:.1f} MB")

        job["status"] = "done"

    except Exception as exc:
        import traceback
        error_msg = f"{type(exc).__name__}: {exc}"
        print(f"\n{'='*60}", flush=True)
        print(f"PIPELINE ERROR at step '{current_step}':", flush=True)
        traceback.print_exc()
        print(f"{'='*60}\n", flush=True)
        job["status"] = "failed"
        job["error"] = error_msg
        if current_step:
            _emit(job_id, current_step, "failed", str(exc))


def _step_prepare(pdf_path: str) -> Path:
    print("[pipeline] Importing step_01...", flush=True)
    from app.pipeline.step_01_prepare_document import prepare_document
    print("[pipeline] step_01 imported OK", flush=True)
    configuration = {
        "video_mode": "automatic",
        "include_compensation": False,
        "include_availability": True,
        "pdf_render_dpi": settings.pdf_render_dpi,
        "openai_model": settings.openai_model,
        "video_width": settings.video_width,
        "video_height": settings.video_height,
        "video_fps": settings.video_fps,
    }
    return prepare_document(
        input_file=pdf_path,
        render_dpi=settings.pdf_render_dpi,
        configuration=configuration,
    )


def _step_extract(run_dir: Path):
    from app.pipeline.step_02_extract_dossier import extract_dossier
    extract_dossier(
        run_directory=run_dir,
        model=settings.openai_model,
        image_detail="high",
    )


def _step_validate(run_dir: Path):
    from app.pipeline.step_03_validate_extraction import validate_dossier
    validate_dossier(run_dir)


def _step_select_content(run_dir: Path):
    from app.pipeline.step_04_select_video_content import select_video_content
    select_video_content(run_directory=run_dir, model=settings.openai_model)


def _step_generate_scenes(run_dir: Path):
    from app.pipeline.step_05_dsl_generate_scenes import generate_scenes
    result = generate_scenes(run_dir)
    return result["video_spec"]


def _step_render(run_dir: Path, video_spec) -> Path:
    from app.services.dsl_render_service import DSLRenderService
    output_dir = run_dir / "dsl_render"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_mp4 = output_dir / "candidate_video.mp4"
    service = DSLRenderService()
    service.render(
        video_spec_dict=video_spec.model_dump(mode="json", by_alias=True),
        output_path=output_mp4,
    )
    return output_mp4
