"""FastAPI server — upload a dossier PDF, generate a video, download it."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.config import RUNS_DIR, create_project_directories, settings

logger = logging.getLogger("pm_video_web")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

APP_USERNAME = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "admin123")

app = FastAPI(title="PM Video Pipeline", version="0.2.0")

JOBS: dict[str, dict] = {}
SESSIONS: dict[str, dict] = {}

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


async def require_auth(authorization: str = Header(default=None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token or token not in SESSIONS:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return SESSIONS[token]


async def require_auth_query(token: str = ""):
    """Auth via query-param — needed for EventSource which can't set headers."""
    if not token or token not in SESSIONS:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return SESSIONS[token]


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Static + root
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/api/login")
async def login(body: LoginRequest):
    if body.username != APP_USERNAME or body.password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = secrets.token_hex(32)
    SESSIONS[token] = {
        "username": body.username,
        "created_at": datetime.utcnow().isoformat(),
    }
    return {"token": token, "username": body.username}


@app.post("/api/logout")
async def logout(session=Depends(require_auth), authorization: str = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        SESSIONS.pop(authorization[7:], None)
    return {"ok": True}


@app.get("/api/status/ping")
async def ping(_session=Depends(require_auth)):
    return {"ok": True}


@app.get("/api/costs/{job_id}")
async def get_costs(job_id: str, _session=Depends(require_auth)):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found.")
    costs = JOBS[job_id].get("costs")
    if costs is None:
        raise HTTPException(404, "Cost data not yet available.")
    return JSONResponse(costs)


# ---------------------------------------------------------------------------
# Pipeline endpoints
# ---------------------------------------------------------------------------

@app.post("/api/upload")
async def upload_dossier(
    file: UploadFile = File(...),
    _session=Depends(require_auth),
):
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
        "step_start_times": {},
        "run_dir": None,
        "video_path": None,
        "candidate_name": None,
        "error": None,
    }

    asyncio.create_task(_run_pipeline(job_id))
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def status_stream(job_id: str, token: str = "", _session=Depends(require_auth_query)):
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
async def status_poll(job_id: str, _session=Depends(require_auth)):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found.")
    return JSONResponse(JOBS[job_id])


# ---------------------------------------------------------------------------
# File listing
# ---------------------------------------------------------------------------

@app.get("/api/files/{job_id}")
async def list_files(job_id: str, _session=Depends(require_auth)):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found.")
    job = JOBS[job_id]
    if not job.get("run_dir"):
        return {"artifacts": [], "audio": [], "video": None, "transcript": None}

    run_dir = Path(job["run_dir"])

    artifacts = []
    for artifacts_dir in [run_dir / "05b_artifacts", run_dir / "05c_artifacts"]:
        if artifacts_dir.exists():
            for f in sorted(artifacts_dir.glob("*.png")):
                artifacts.append({
                    "name": f.name,
                    "size_kb": round(f.stat().st_size / 1024),
                    "dir": artifacts_dir.name,
                })

    audio = []
    audio_dir = run_dir / "06_audio"
    if audio_dir.exists():
        for f in sorted(audio_dir.glob("*.mp3")):
            audio.append({"name": f.name, "size_kb": round(f.stat().st_size / 1024)})

    transcript = None
    for t_path in [
        run_dir / "06_audio" / "final_transcript.txt",
        run_dir / "05_storyboard" / "voiceover.txt",
    ]:
        if t_path.exists():
            transcript = {
                "name": "voiceover_transcript.txt",
                "size_kb": round(t_path.stat().st_size / 1024),
            }
            break

    video = None
    video_path = job.get("video_path")
    if video_path and Path(video_path).exists():
        p = Path(video_path)
        video = {
            "name": p.name,
            "size_mb": round(p.stat().st_size / 1_048_576, 1),
        }

    return {"artifacts": artifacts, "audio": audio, "video": video, "transcript": transcript}


# ---------------------------------------------------------------------------
# Download endpoints
# ---------------------------------------------------------------------------

@app.get("/api/download/{job_id}/video")
async def download_video(job_id: str, _session=Depends(require_auth_query)):
    job = _get_job_or_404(job_id)
    video_path = job.get("video_path")
    if not video_path or not Path(video_path).exists():
        raise HTTPException(400, "Video not ready.")
    candidate = job.get("candidate_name", "candidate")
    return FileResponse(
        Path(video_path),
        media_type="video/mp4",
        filename=f"{candidate}_video.mp4",
    )


@app.get("/api/download/{job_id}/artifact/{filename}")
async def download_artifact(job_id: str, filename: str, _session=Depends(require_auth_query)):
    job = _get_job_or_404(job_id)
    run_dir = Path(job["run_dir"])
    file_path = run_dir / "05b_artifacts" / filename
    if not file_path.exists():
        raise HTTPException(404, "File not found.")
    return FileResponse(file_path, media_type="image/png", filename=filename)


@app.get("/api/download/{job_id}/transcript")
async def download_transcript(job_id: str, _session=Depends(require_auth_query)):
    job = _get_job_or_404(job_id)
    run_dir = Path(job["run_dir"])
    for t_path in [
        run_dir / "06_audio" / "final_transcript.txt",
        run_dir / "05_storyboard" / "voiceover.txt",
    ]:
        if t_path.exists():
            return FileResponse(t_path, media_type="text/plain", filename="voiceover_transcript.txt")
    raise HTTPException(404, "Transcript not found.")


@app.get("/api/download/{job_id}/audio/{filename}")
async def download_audio(job_id: str, filename: str, _session=Depends(require_auth_query)):
    job = _get_job_or_404(job_id)
    run_dir = Path(job["run_dir"])
    file_path = run_dir / "06_audio" / filename
    if not file_path.exists():
        raise HTTPException(404, "File not found.")
    return FileResponse(file_path, media_type="audio/mpeg", filename=filename)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_job_or_404(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found.")
    job = JOBS[job_id]
    if not job.get("run_dir"):
        raise HTTPException(400, "Run not started yet.")
    return job


def _emit(job_id: str, step_name: str, status: str, detail: str = ""):
    job = JOBS[job_id]
    now = datetime.utcnow()

    if status == "running":
        job["step_start_times"][step_name] = now

    duration_ms = None
    if status in ("done", "failed"):
        start = job.get("step_start_times", {}).get(step_name)
        if start:
            duration_ms = int((now - start).total_seconds() * 1000)

    job["steps"].append({
        "step": step_name,
        "status": status,
        "detail": detail,
        "duration_ms": duration_ms,
        "ts": now.isoformat(),
    })


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

async def _run_pipeline(job_id: str):
    job = JOBS[job_id]
    job["status"] = "running"
    current_step = None

    try:
        pdf_path = job["pdf_path"]

        current_step = "prepare_document"
        _emit(job_id, current_step, "running", "Preparing PDF pages…")
        run_dir = await asyncio.to_thread(_step_prepare, pdf_path)
        job["run_dir"] = str(run_dir)
        _emit(job_id, current_step, "done")

        current_step = "extract_dossier"
        _emit(job_id, current_step, "running", "Extracting dossier with AI…")
        await asyncio.to_thread(_step_extract, run_dir)
        _emit(job_id, current_step, "done")

        current_step = "validate_extraction"
        _emit(job_id, current_step, "running", "Validating extracted data…")
        await asyncio.to_thread(_step_validate, run_dir)
        _emit(job_id, current_step, "done")

        current_step = "select_video_content"
        _emit(job_id, current_step, "running", "Selecting video content…")
        await asyncio.to_thread(_step_select_content, run_dir)
        _emit(job_id, current_step, "done")

        current_step = "generate_scenes"
        _emit(job_id, current_step, "running", "Detecting headshot…")
        headshot_path = await asyncio.to_thread(_find_headshot, run_dir)
        logger.info("Headshot detection: %s", headshot_path or "not found")
        _emit(job_id, current_step, "running", "Designing scenes with AI…")
        video_spec = await asyncio.to_thread(_step_generate_scenes, run_dir, headshot_path)
        job["candidate_name"] = video_spec.candidate_name
        _emit(
            job_id,
            current_step,
            "done",
            f"{len(video_spec.scenes)} scenes · "
            f"{sum(s.duration_seconds for s in video_spec.scenes):.0f}s base (final duration set after audio)",
        )

        current_step = "generate_artifacts"
        _emit(job_id, current_step, "running", f"Generating {len(video_spec.artifacts)} image(s) with AI…")
        artifact_manifest = await asyncio.to_thread(_step_generate_artifacts, run_dir, video_spec, headshot_path)
        generated = len(artifact_manifest.get("artifacts", []))
        _emit(job_id, current_step, "done", f"{generated} image(s) ready")

        current_step = "generate_audio"
        _emit(job_id, current_step, "running", "Generating voiceover audio…")
        scene_audio = await asyncio.to_thread(_step_generate_audio, run_dir, video_spec)
        total_audio = sum(a["duration_seconds"] for a in scene_audio)
        total_video = sum(s.duration_seconds for s in video_spec.scenes)
        _emit(job_id, current_step, "done",
              f"{len(scene_audio)} clips · {total_audio:.1f}s" if scene_audio else "Skipped (no narration)")

        current_step = "render_video"
        _emit(job_id, current_step, "running", "Rendering video with Remotion…")
        # Dump AFTER audio step so scene durations reflect audio-adjusted values
        video_spec_dict = video_spec.model_dump(mode="json", by_alias=True)
        video_path = await asyncio.to_thread(_step_render, run_dir, video_spec_dict, scene_audio, artifact_manifest)
        job["video_path"] = str(video_path)
        _emit(job_id, current_step, "done", f"{video_path.stat().st_size / 1_048_576:.1f} MB")

        costs = await asyncio.to_thread(_step_calculate_costs, run_dir)
        job["costs"] = costs

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


def _step_calculate_costs(run_dir: Path) -> dict:
    try:
        from app.services.cost_service import CostService
        costs_dir = run_dir / "11_costs"
        costs_dir.mkdir(parents=True, exist_ok=True)
        service = CostService()
        return service.calculate_run_costs(
            run_directory=run_dir,
            output_directory=costs_dir,
        )
    except Exception as exc:
        logger.warning("Cost calculation failed: %s", exc)
        return {"error": str(exc)}


def _step_prepare(pdf_path: str) -> Path:
    from app.pipeline.step_01_prepare_document import prepare_document
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
    extract_dossier(run_directory=run_dir, model=settings.openai_model, image_detail="high")


def _step_validate(run_dir: Path):
    from app.pipeline.step_03_validate_extraction import validate_dossier
    validate_dossier(run_dir)


def _step_select_content(run_dir: Path):
    from app.pipeline.step_04_select_video_content import select_video_content
    select_video_content(run_directory=run_dir, model=settings.openai_model)



def _find_headshot(run_dir: Path) -> Path | None:
    """Extract all images from the PDF (XObjects + inline) and ask the VLM to identify the portrait."""
    try:
        import base64
        import json as _json
        import pymupdf
        from openai import OpenAI
        from app.config import settings

        pdf_files = sorted((run_dir / "00_input").glob("*.pdf"))
        if not pdf_files:
            return None

        extracted_dir = run_dir / "01_document" / "extracted_images"
        extracted_dir.mkdir(parents=True, exist_ok=True)

        doc = pymupdf.open(str(pdf_files[0]))
        images: list[dict] = []
        seen_xrefs: set[int] = set()

        try:
            # Check first 4 pages — headshot is almost always on page 1 or 2
            for page_idx in range(min(doc.page_count, 4)):
                page = doc.load_page(page_idx)

                # --- Method 1: XObject images (embedded image resources) ---
                for img_tuple in page.get_images(full=True):
                    xref = img_tuple[0]
                    if xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)
                    try:
                        extracted = doc.extract_image(xref)
                    except Exception:
                        continue
                    data = extracted.get("image")
                    if not data:
                        continue
                    w = int(extracted.get("width", 0))
                    h = int(extracted.get("height", 0))
                    if w < 80 or h < 80 or len(data) < 5_000:
                        continue
                    ext = extracted.get("ext", "png")
                    img_id = f"xobj_{xref}"
                    dest = extracted_dir / f"p{page_idx+1}_{img_id}.{ext}"
                    dest.write_bytes(data)
                    images.append({"id": img_id, "path": str(dest)})

                # --- Method 2: Clip image regions from the rendered page ---
                # get_image_info returns bbox for EVERY image including inline ones
                for info_idx, info in enumerate(page.get_image_info()):
                    bbox = info.get("bbox")
                    if not bbox:
                        continue
                    rect = pymupdf.Rect(bbox)
                    # Skip tiny icons / decorative elements (< 80×80 points)
                    if rect.width < 80 or rect.height < 80:
                        continue
                    img_id = f"clip_p{page_idx+1}_{info_idx}"
                    pix = page.get_pixmap(clip=rect, dpi=150, alpha=False)
                    dest = extracted_dir / f"{img_id}.png"
                    pix.save(str(dest))
                    if dest.stat().st_size < 5_000:
                        dest.unlink(missing_ok=True)
                        continue
                    images.append({"id": img_id, "path": str(dest)})
        finally:
            doc.close()

        # Deduplicate: exact same file size → likely same image extracted twice
        seen_sizes: set[int] = set()
        deduped: list[dict] = []
        for img in images:
            p = Path(img["path"])
            if not p.exists():
                continue
            sz = p.stat().st_size
            if sz not in seen_sizes:
                seen_sizes.add(sz)
                deduped.append(img)
        images = deduped

        if not images:
            logger.info("No usable images found in PDF")
            return None

        logger.info("Found %d unique images in PDF — asking VLM to identify portrait", len(images))

        client = OpenAI()
        content: list = [{
            "type": "text",
            "text": (
                f"I have {len(images)} image(s) extracted from a professional candidate dossier PDF. "
                "Which image (if any) is a real photograph of a human face or head-and-shoulders portrait "
                "of the candidate? Ignore logos, charts, graphs, orange/coloured shapes, decorative "
                "backgrounds, and anything that is not an actual photo of a person. "
                "Return JSON only: {\"portrait_id\": \"<id or null>\"}. "
                "Return null if none of the images clearly shows a person's face."
            ),
        }]
        id_map: dict[str, dict] = {}
        for img in images:
            p = Path(img["path"])
            b64 = base64.b64encode(p.read_bytes()).decode()
            content.append({"type": "text", "text": f"Image ID: {img['id']}"})
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"}})
            id_map[img["id"]] = img

        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_tokens=100,
        )
        result = _json.loads(resp.choices[0].message.content or "{}")
        portrait_id = result.get("portrait_id")
        logger.info("VLM portrait selection: %s", portrait_id)

        if not portrait_id or portrait_id not in id_map:
            logger.info("VLM found no candidate portrait in PDF")
            return None

        src = Path(id_map[portrait_id]["path"])
        headshot_path = run_dir / "01_document" / "candidate_headshot.png"
        try:
            from PIL import Image
            Image.open(src).save(headshot_path, "PNG")
        except Exception:
            import shutil
            shutil.copy2(src, headshot_path)
        logger.info("Candidate headshot saved → %s", headshot_path.name)
        return headshot_path

    except Exception as exc:
        logger.warning("Headshot detection failed (non-fatal): %s", exc)
        return None


def _step_generate_scenes(run_dir: Path, headshot_path: Path | None = None):
    from app.pipeline.step_05_dsl_generate_scenes import generate_scenes
    result = generate_scenes(run_dir, headshot_path=headshot_path)
    return result["video_spec"]


def _step_generate_artifacts(run_dir: Path, video_spec, headshot_path: Path | None = None) -> dict:
    from app.services.dsl_artifact_service import DSLArtifactService
    from app.schemas.scene_dsl import ArtifactSpec
    output_dir = run_dir / "05b_artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Ensure there is always at least one AI-generated image
    artifact_ids = {a.artifact_id for a in video_spec.artifacts}
    if not any(a.source == "generate" for a in video_spec.artifacts):
        video_spec.artifacts.append(ArtifactSpec(
            artifact_id="background_visual",
            prompt=(
                "A sophisticated, abstract executive background: deep navy blue gradient "
                "with subtle geometric patterns, professional and cinematic, 4K quality, "
                "no text, no people, suitable for a corporate video backdrop."
            ),
            orientation="landscape",
            source="generate",
        ))

    service = DSLArtifactService()
    return service.generate_artifacts(
        artifact_specs=video_spec.artifacts,
        output_dir=output_dir,
        headshot_path=headshot_path,
    )


def _step_generate_audio(run_dir: Path, video_spec) -> list[dict]:
    """Returns list of scene audio dicts for DSLRenderService."""
    import json as _json
    from app.services.tts_service import TTSService
    if not any(s.narration for s in video_spec.scenes):
        return []
    audio_dir = run_dir / "06_audio"
    tts = TTSService()
    scene_audio = tts.generate_scene_audio(video_spec.scenes, audio_dir)

    # Write metadata so cost_service can calculate TTS spend
    if scene_audio:
        total_chars = sum(len(s.narration or "") for s in video_spec.scenes if s.narration)
        total_duration = sum(a["duration_seconds"] for a in scene_audio)
        (audio_dir / "audio_metadata.json").write_text(
            _json.dumps({
                "model": tts.model,
                "voice": tts.voice,
                "result": {
                    "character_count": total_chars,
                    "duration_seconds": total_duration,
                    "scene_count": len(scene_audio),
                },
            }, indent=2),
            encoding="utf-8",
        )

    audio_by_scene = {a["scene_id"]: a["duration_seconds"] for a in scene_audio}
    # Stretch scene duration to fit audio, but warn when audio is much longer than planned
    for scene in video_spec.scenes:
        audio_dur = audio_by_scene.get(scene.scene_id)
        if audio_dur:
            if audio_dur + 1.5 > scene.duration_seconds:
                logger.warning(
                    "Scene %s: audio %.1fs > planned %.1fs — stretching scene",
                    scene.scene_id, audio_dur, scene.duration_seconds,
                )
                scene.duration_seconds = round(audio_dur + 1.5, 1)
    return scene_audio


def _step_render(
    run_dir: Path,
    video_spec_dict: dict,
    scene_audio: list[dict] | None = None,
    artifact_manifest: dict | None = None,
) -> Path:
    from app.services.dsl_render_service import DSLRenderService
    output_dir = run_dir / "dsl_render"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_mp4 = output_dir / "candidate_video.mp4"
    # Allow 10s of render time per second of video, minimum 300s
    total_video_seconds = sum(s.get("duration_seconds", 10) for s in video_spec_dict.get("scenes", []))
    timeout = max(300, int(total_video_seconds * 10))
    service = DSLRenderService()
    service.render(
        video_spec_dict=video_spec_dict,
        output_path=output_mp4,
        artifact_manifest=artifact_manifest,
        scene_audio=scene_audio or [],
        timeout_seconds=timeout,
    )
    return output_mp4
