"""Run the DSL pipeline from a dossier PDF to a rendered video."""

import argparse
import sys
import time
from pathlib import Path

from app.config import create_project_directories, settings


def main():
    parser = argparse.ArgumentParser(description="DSL video pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="Path to a dossier PDF (starts fresh)")
    group.add_argument("--run-dir", help="Existing run directory (resumes)")
    parser.add_argument("--from-step", type=int, default=1, help="Start from step (1-8)")
    parser.add_argument("--skip-artifacts", action="store_true", help="Skip DALL-E artifact generation")
    parser.add_argument("--skip-audio", action="store_true", help="Skip TTS audio generation")
    args = parser.parse_args()

    create_project_directories()
    start = time.time()
    run_dir = None
    video_spec = None
    artifact_manifest = None
    scene_audio = None
    step = args.from_step

    if args.run_dir:
        run_dir = Path(args.run_dir).expanduser().resolve()
        if not run_dir.exists():
            print(f"Run directory not found: {run_dir}")
            sys.exit(1)
        print(f"Resuming from: {run_dir}")
    elif step > 1:
        print("--from-step > 1 requires --run-dir")
        sys.exit(1)

    # Step 1: Prepare document
    if step <= 1 and args.input:
        pdf_path = Path(args.input).expanduser().resolve()
        if not pdf_path.exists():
            print(f"File not found: {pdf_path}")
            sys.exit(1)
        print(f"\n{'='*60}")
        print("STEP 1/8: Preparing document...")
        print(f"{'='*60}")
        from app.pipeline.step_01_prepare_document import prepare_document
        run_dir = prepare_document(
            input_file=pdf_path,
            render_dpi=settings.pdf_render_dpi,
            configuration={
                "video_mode": "automatic",
                "include_compensation": False,
                "include_availability": True,
                "pdf_render_dpi": settings.pdf_render_dpi,
                "openai_model": settings.openai_model,
                "video_width": settings.video_width,
                "video_height": settings.video_height,
                "video_fps": settings.video_fps,
            },
        )
        print(f"Done. Run directory: {run_dir}")

    # Step 2: Extract dossier
    if step <= 2:
        print(f"\n{'='*60}")
        print("STEP 2/8: Extracting dossier with AI...")
        print(f"{'='*60}")
        from app.pipeline.step_02_extract_dossier import extract_dossier
        extract_dossier(
            run_directory=run_dir,
            model=settings.openai_model,
            image_detail="high",
        )
        print("Done.")

    # Step 3: Validate extraction
    if step <= 3:
        print(f"\n{'='*60}")
        print("STEP 3/8: Validating extraction...")
        print(f"{'='*60}")
        from app.pipeline.step_03_validate_extraction import validate_dossier
        validate_dossier(run_dir)
        print("Done.")

    # Step 4: Select video content
    if step <= 4:
        print(f"\n{'='*60}")
        print("STEP 4/8: Selecting video content...")
        print(f"{'='*60}")
        from app.pipeline.step_04_select_video_content import select_video_content
        select_video_content(run_directory=run_dir, model=settings.openai_model)
        print("Done.")

    # Step 5: Generate DSL scenes
    if step <= 5:
        print(f"\n{'='*60}")
        print("STEP 5/8: Generating DSL scenes with AI...")
        print(f"{'='*60}")
        from app.pipeline.step_05_dsl_generate_scenes import generate_scenes
        result = generate_scenes(run_dir)
        video_spec = result["video_spec"]
        summary = result["summary"]
        print(f"Done. {summary['scene_count']} scenes, {summary['total_duration']:.0f}s total")

    # Load video_spec from disk if resuming past step 5
    if video_spec is None and step > 5:
        from app.utils.json_utils import load_json
        from app.schemas.scene_dsl import VideoSpec
        spec_path = run_dir / "05_dsl_scenes" / "video_spec.json"
        if not spec_path.exists():
            print(f"video_spec.json not found at {spec_path}. Run step 5 first.")
            sys.exit(1)
        video_spec = VideoSpec.model_validate(load_json(spec_path))

    # Step 6: Generate artifacts (DALL-E images)
    if step <= 6 and not args.skip_artifacts:
        artifacts_list = video_spec.artifacts if video_spec.artifacts else []
        if artifacts_list:
            print(f"\n{'='*60}")
            print(f"STEP 6/8: Generating {len(artifacts_list)} artifacts with DALL-E...")
            print(f"{'='*60}")
            from app.services.dsl_artifact_service import DSLArtifactService
            artifact_dir = run_dir / "05b_artifacts"
            service = DSLArtifactService()
            artifact_manifest = service.generate_artifacts(artifacts_list, artifact_dir)
            print(f"Done. {len(artifact_manifest['artifacts'])} artifacts generated.")
        else:
            print(f"\n{'='*60}")
            print("STEP 6/8: No artifacts requested, skipping.")
            print(f"{'='*60}")
    elif step <= 6:
        print(f"\n{'='*60}")
        print("STEP 6/8: Artifact generation skipped (--skip-artifacts).")
        print(f"{'='*60}")

    # Step 7: Generate audio (TTS)
    if step <= 7 and not args.skip_audio:
        print(f"\n{'='*60}")
        print("STEP 7/8: Generating voiceover with TTS...")
        print(f"{'='*60}")
        from app.services.tts_service import TTSService
        audio_dir = run_dir / "06_audio"
        tts = TTSService()
        scene_audio = tts.generate_scene_audio(video_spec.scenes, audio_dir)
        total_audio = sum(a["duration_seconds"] for a in scene_audio)
        print(f"Done. {len(scene_audio)} clips, {total_audio:.1f}s total audio.")

        # Adjust scene durations to match audio (scene >= audio + 1.5s buffer)
        audio_by_scene = {a["scene_id"]: a["duration_seconds"] for a in scene_audio}
        for scene in video_spec.scenes:
            audio_dur = audio_by_scene.get(scene.scene_id)
            if audio_dur and audio_dur + 1.5 > scene.duration_seconds:
                scene.duration_seconds = round(audio_dur + 1.5, 1)
    elif step <= 7:
        print(f"\n{'='*60}")
        print("STEP 7/8: Audio generation skipped (--skip-audio).")
        print(f"{'='*60}")

    # Reload artifact manifest from disk if resuming past step 6
    if artifact_manifest is None and step > 6:
        manifest_path = run_dir / "05b_artifacts"
        if manifest_path.exists():
            import glob as _glob
            entries = []
            for png in sorted(manifest_path.glob("*.png")):
                entries.append({
                    "artifactId": png.stem,
                    "rendererPath": f"artifacts/{png.name}",
                    "altText": png.stem,
                    "approved": True,
                })
            if entries:
                artifact_manifest = {"artifacts": entries}
                print(f"Loaded {len(entries)} artifacts from disk.")

    # Reload scene audio from disk if resuming past step 7
    if scene_audio is None and step > 7:
        audio_dir = run_dir / "06_audio"
        if audio_dir.exists():
            from mutagen.mp3 import MP3
            scene_audio = []
            for mp3 in sorted(audio_dir.glob("*.mp3")):
                dur = MP3(str(mp3)).info.length
                scene_audio.append({
                    "scene_id": mp3.stem,
                    "audio_path": str(mp3),
                    "duration_seconds": round(dur, 1),
                })
            if scene_audio:
                print(f"Loaded {len(scene_audio)} audio clips from disk.")
                audio_by_scene = {a["scene_id"]: a["duration_seconds"] for a in scene_audio}
                for scene in video_spec.scenes:
                    audio_dur = audio_by_scene.get(scene.scene_id)
                    if audio_dur and audio_dur + 1.5 > scene.duration_seconds:
                        scene.duration_seconds = round(audio_dur + 1.5, 1)

    # Step 8: Render video
    if step <= 8:
        print(f"\n{'='*60}")
        print("STEP 8/8: Rendering video with Remotion...")
        print(f"{'='*60}")
        from app.services.dsl_render_service import DSLRenderService
        output_dir = run_dir / "dsl_render"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_mp4 = output_dir / "candidate_video.mp4"
        service = DSLRenderService()
        service.render(
            video_spec_dict=video_spec.model_dump(mode="json", by_alias=True),
            output_path=output_mp4,
            artifact_manifest=artifact_manifest,
            scene_audio=scene_audio,
        )
        size_mb = output_mp4.stat().st_size / 1_048_576
        elapsed = time.time() - start

        print(f"\n{'='*60}")
        print("PIPELINE COMPLETE")
        print(f"{'='*60}")
        print(f"Candidate:  {video_spec.candidate_name}")
        print(f"Scenes:     {len(video_spec.scenes)}")
        print(f"Duration:   {sum(s.duration_seconds for s in video_spec.scenes):.0f}s")
        print(f"Video:      {output_mp4}")
        print(f"Size:       {size_mb:.1f} MB")
        print(f"Time:       {elapsed:.0f}s")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
