"""Pipeline Step 08: Compile the master frame-level render specification."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from uuid import uuid4

from mutagen.mp3 import MP3

from app.config import settings
from app.schemas.render_spec import (
    AudioTrack,
    RenderScene,
    RenderSpecification,
    RenderVideoSettings,
    ResolvedAsset,
    ThemeSettings,
)
from app.schemas.storyboard import Storyboard
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "compile_render_spec"

SCENE_COMPONENTS = {
    "candidate_intro": "CandidateIntro",
    "executive_summary": "ExecutiveSummary",
    "career_timeline": "CareerTimeline",
    "career_milestone": "CareerMilestone",
    "quantified_highlights": "MetricHighlights",
    "single_highlight": "SingleHighlight",
    "leadership_scope": "LeadershipScope",
    "organisation_structure": "OrganisationStructure",
    "strength_summary": "StrengthSummary",
    "compensation_availability": "ConfidentialDetails",
    "closing": "ClosingScene",
}


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Compile the master renderer JSON."
    )
    parser.add_argument("--run-dir", required=True)
    return parser


def _creative_scene_map(creative_plan):
    draft = creative_plan.get("draft", creative_plan)
    return {
        item["scene_id"]: item
        for item in draft.get("scene_briefs", [])
        if isinstance(item, dict) and item.get("scene_id")
    }


def _published_scene_map(publish_report):
    return {
        item["scene_id"]: item
        for item in publish_report.get("published", [])
        if isinstance(item, dict) and item.get("scene_id")
    }


def _approved_artifact_map(artifact_manifest):
    return {
        item["artifact_id"]: item
        for item in artifact_manifest.get("artifacts", [])
        if (
            isinstance(item, dict)
            and item.get("artifact_id")
            and item.get("approved")
        )
    }


def _artifact_ids_for_scene(creative_scene):
    artifact_ids = []
    requirements = creative_scene.get("artifact_requirements", []) or []

    for requirement in requirements:
        artifact_id = None
        if isinstance(requirement, str):
            artifact_id = requirement
        elif isinstance(requirement, dict):
            artifact_id = (
                requirement.get("artifact_id")
                or requirement.get("artifactId")
                or requirement.get("id")
            )

        if artifact_id and str(artifact_id) not in artifact_ids:
            artifact_ids.append(str(artifact_id))

    return artifact_ids


def _scene_artifacts(creative_scene, approved_artifacts):
    values = []
    for artifact_id in _artifact_ids_for_scene(creative_scene):
        artifact = approved_artifacts.get(artifact_id)
        if not artifact:
            continue
        values.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact.get("artifact_type", "image"),
                "renderer_path": artifact.get("renderer_path"),
                "approved": True,
                "alt_text": artifact.get("alt_text") or artifact_id,
                "source_strategy": artifact.get("source_strategy"),
            }
        )
    return values


def _resolved_assets(artifact_manifest):
    assets = []
    for item in artifact_manifest.get("artifacts", []):
        if not isinstance(item, dict) or not item.get("approved"):
            continue
        local_path = item.get("local_path")
        artifact_id = item.get("artifact_id")
        if not local_path or not artifact_id:
            continue
        assets.append(
            ResolvedAsset(
                asset_id=str(artifact_id),
                asset_type=str(item.get("artifact_type", "other")),
                source_path=str(local_path),
                renderer_path=item.get("renderer_path"),
                required=bool(item.get("required", False)),
                approved=True,
                alt_text=item.get("alt_text") or str(artifact_id),
            )
        )
    return assets


def _visual_element_type(element):
    value = (
        element.get("element_type")
        or element.get("type")
        or element.get("kind")
    )
    return str(value).strip().lower() if value is not None else None


def _visual_element_text(visual_elements, element_types):
    normalised_types = {str(value).strip().lower() for value in element_types}
    for element in visual_elements:
        if not isinstance(element, dict):
            continue
        if _visual_element_type(element) not in normalised_types:
            continue
        value = (
            element.get("content")
            or element.get("value")
            or element.get("text")
            or element.get("label")
            or element.get("title")
        )
        if value:
            return str(value).strip()
    return None


def _default_headline(scene_type):
    return {
        "candidate_intro": "Executive profile",
        "executive_summary": "Executive profile",
        "career_timeline": "Career progression",
        "career_milestone": "Career impact",
        "quantified_highlights": "Selected outcomes",
        "single_highlight": "Selected highlight",
        "leadership_scope": "Leadership at scale",
        "organisation_structure": "Organisation structure",
        "strength_summary": "Core strengths",
        "compensation_availability": "Availability",
        "closing": "Private and Confidential",
    }.get(scene_type, "Candidate snapshot")


def _build_display(scene, creative_scene, visual_elements):
    viewer_copy = (
        creative_scene.get("viewer_copy")
        or creative_scene.get("display")
        or {}
    )
    if not isinstance(viewer_copy, dict):
        viewer_copy = {}

    headline = (
        viewer_copy.get("headline")
        or viewer_copy.get("title")
        or _visual_element_text(
            visual_elements,
            {"heading", "headline", "title"},
        )
        or _default_headline(scene.scene_type.value)
    )

    supporting_text = (
        viewer_copy.get("supporting_text")
        or viewer_copy.get("supportingText")
        or viewer_copy.get("subtitle")
        or _visual_element_text(
            visual_elements,
            {"subheading", "subtitle", "supporting_text", "body"},
        )
    )

    eyebrow = (
        viewer_copy.get("eyebrow")
        or viewer_copy.get("section_label")
        or scene.scene_type.value.replace("_", " ").upper()
    )

    return {
        "eyebrow": str(eyebrow).strip() if eyebrow else None,
        "headline": str(headline).strip() if headline else None,
        "supporting_text": (
            str(supporting_text).strip() if supporting_text else None
        ),
    }


def _approved_facts(scene, creative_scene):
    values = []
    sources = [
        creative_scene.get("approved_facts", []),
        getattr(scene, "approved_facts", []),
    ]
    for source in sources:
        if not source:
            continue
        if isinstance(source, str):
            source = [source]
        if not isinstance(source, (list, tuple)):
            continue
        for value in source:
            if isinstance(value, dict):
                candidate = (
                    value.get("text")
                    or value.get("value")
                    or value.get("content")
                    or value.get("fact")
                )
            else:
                candidate = value
            if candidate is None:
                continue
            text = str(candidate).strip()
            if text and text not in values:
                values.append(text)
    return values


def _requested_component_strategy(creative_scene):
    strategy = (
        creative_scene.get("component_strategy")
        or creative_scene.get("renderer_strategy")
        or creative_scene.get("render_strategy")
    )
    if isinstance(strategy, dict):
        strategy = (
            strategy.get("strategy")
            or strategy.get("type")
            or strategy.get("value")
        )
    return str(strategy).strip().lower() if strategy is not None else None


def _renderer_strategy(scene_id, creative_scene, published_scenes):
    published = published_scenes.get(scene_id)
    creative_strategy = _requested_component_strategy(creative_scene)
    generated_requested = creative_strategy in {
        "generated_component",
        "generated",
        "dynamic_component",
        "custom_component",
    }
    if generated_requested and published is not None:
        generated_key = published.get("scene_id") or scene_id
        return "generated_component", str(generated_key)
    return "library_component", None


def compile_render_spec(run_directory):
    run_path = Path(run_directory).expanduser().resolve()
    run_manager = RunManager(run_path)
    setup_logging(
        settings.log_level,
        run_manager.get_directory("logs") / "pipeline.log",
    )

    storyboard_path = run_manager.get_directory("storyboard") / "storyboard.json"
    audio_path = run_manager.get_directory("audio") / "voiceover.mp3"
    output_directory = run_manager.get_directory("render_spec")
    creative_plan_path = run_path / "05b_creative_plan" / "creative_plan.json"
    artifact_manifest_path = (
        run_path / "05c_artifacts" / "artifact_manifest_final.json"
    )
    publish_report_path = (
        run_path
        / "05g_dynamic_integration"
        / "dynamic_publish_report.json"
    )

    for path, message in (
        (storyboard_path, "Storyboard not found."),
        (audio_path, "Audio not found."),
        (creative_plan_path, "Creative plan not found."),
        (artifact_manifest_path, "Final artifact manifest not found."),
    ):
        if not path.exists():
            raise FileNotFoundError(f"{message} Expected: {path}")

    output_directory.mkdir(parents=True, exist_ok=True)
    run_manager.start_step(STEP_NAME)

    try:
        storyboard = Storyboard.model_validate(load_json(storyboard_path))
        creative_plan = load_json(creative_plan_path)
        artifact_manifest = load_json(artifact_manifest_path)
        publish_report = (
            load_json(publish_report_path)
            if publish_report_path.exists()
            else {}
        )

        creative_scenes = _creative_scene_map(creative_plan)
        published_scenes = _published_scene_map(publish_report)
        approved_artifacts = _approved_artifact_map(artifact_manifest)

        audio_duration = float(MP3(audio_path).info.length)
        fps = int(settings.video_fps)
        total_frames = max(1, math.ceil(audio_duration * fps))
        estimated_total = sum(
            float(scene.estimated_duration_seconds)
            for scene in storyboard.scenes
        )
        scale = audio_duration / estimated_total if estimated_total > 0 else 1.0

        scenes = []
        current_frame = 0
        generated_scene_count = 0
        library_scene_count = 0

        for index, scene in enumerate(storyboard.scenes):
            is_last = index == len(storyboard.scenes) - 1
            if is_last:
                duration_frames = max(1, total_frames - current_frame)
            else:
                duration_frames = max(
                    1,
                    round(float(scene.estimated_duration_seconds) * scale * fps),
                )
                remaining_frames = total_frames - current_frame
                remaining_scene_count = len(storyboard.scenes) - index - 1
                maximum_duration = max(
                    1,
                    remaining_frames - remaining_scene_count,
                )
                duration_frames = min(duration_frames, maximum_duration)

            component = SCENE_COMPONENTS.get(scene.scene_type.value)
            if not component:
                raise ValueError(
                    f"Unsupported scene type: {scene.scene_type.value}"
                )

            creative_scene = creative_scenes.get(scene.scene_id, {})
            visual_elements = [
                element.model_dump(mode="json")
                for element in scene.visual_elements
            ]
            display = _build_display(scene, creative_scene, visual_elements)
            scene_artifacts = _scene_artifacts(
                creative_scene,
                approved_artifacts,
            )
            approved_facts = _approved_facts(scene, creative_scene)
            renderer_strategy, generated_component_key = _renderer_strategy(
                scene.scene_id,
                creative_scene,
                published_scenes,
            )

            if renderer_strategy == "generated_component":
                generated_scene_count += 1
            else:
                library_scene_count += 1

            renderer_instructions = {
                "scene_purpose": scene.purpose,
                "visual_story": creative_scene.get("visual_story"),
                "layout_intent": creative_scene.get("layout_intent"),
                "animation_intent": creative_scene.get("animation_intent"),
                "transition_in": (
                    creative_scene.get("transition_in") or scene.transition_in
                ),
                "transition_out": (
                    creative_scene.get("transition_out") or scene.transition_out
                ),
                "background_variant": (
                    creative_scene.get("background_treatment")
                    or scene.background_variant
                ),
                "do_not_render_as_text": True,
            }

            props = {
                "display": display,
                "visual_elements": visual_elements,
                "approved_facts": approved_facts,
                "artifacts": scene_artifacts,
                "voiceover": scene.complete_voiceover,
                "purpose": "",
                "renderer_instructions": renderer_instructions,
                "transition_in": scene.transition_in,
                "transition_out": scene.transition_out,
                "background_variant": scene.background_variant,
            }

            scenes.append(
                RenderScene(
                    scene_id=scene.scene_id,
                    component=component,
                    renderer_strategy=renderer_strategy,
                    generated_component_key=generated_component_key,
                    variant=scene.variant,
                    start_frame=current_frame,
                    duration_frames=duration_frames,
                    props=props,
                )
            )
            current_frame += duration_frames

        if not scenes:
            raise ValueError("Storyboard produced no render scenes.")

        final_scene = scenes[-1]
        final_end = final_scene.start_frame + final_scene.duration_frames
        if final_end != total_frames:
            corrected_duration = total_frames - final_scene.start_frame
            if corrected_duration <= 0:
                raise ValueError(
                    "Unable to resolve a positive duration for the final scene."
                )
            final_scene.duration_frames = corrected_duration

        resolved_assets = _resolved_assets(artifact_manifest)

        render_specification = RenderSpecification(
            schema_version="2.0",
            render_id=f"render_{uuid4().hex[:12]}",
            candidate_name=storyboard.candidate_name,
            video=RenderVideoSettings(
                width=settings.video_width,
                height=settings.video_height,
                fps=fps,
                duration_frames=total_frames,
            ),
            theme=ThemeSettings(
                theme_id=storyboard.branding_theme,
                confidential=storyboard.confidential,
            ),
            audio=AudioTrack(
                source_path=str(audio_path),
                duration_seconds=audio_duration,
                start_frame=0,
                volume=1.0,
            ),
            scenes=scenes,
            assets=resolved_assets,
            output_path=str(
                run_manager.get_directory("video") / "candidate_video.mp4"
            ),
            metadata={
                "storyboard_path": str(storyboard_path),
                "creative_plan_path": str(creative_plan_path),
                "artifact_manifest_path": str(artifact_manifest_path),
                "publish_report_path": (
                    str(publish_report_path)
                    if publish_report_path.exists()
                    else None
                ),
                "duration_seconds": audio_duration,
                "render_contract": "master_single_composition_v2",
                "generated_scene_count": generated_scene_count,
                "library_scene_count": library_scene_count,
                "published_generated_component_count": len(published_scenes),
                "approved_artifact_count": len(approved_artifacts),
                "viewer_copy_contract": "display_and_visual_elements_only",
                "production_instruction_contract": (
                    "renderer_instructions_never_viewer_facing"
                ),
            },
        )

        output_path = output_directory / "render_spec.json"
        resolved_assets_path = output_directory / "resolved_assets.json"
        validation_path = output_directory / "render_validation.json"

        save_json(
            render_specification.model_dump(mode="json"),
            output_path,
        )
        save_json(
            [item.model_dump(mode="json") for item in resolved_assets],
            resolved_assets_path,
        )

        validation = {
            "status": "passed",
            "scene_count": len(scenes),
            "generated_scene_count": generated_scene_count,
            "library_scene_count": library_scene_count,
            "published_generated_component_count": len(published_scenes),
            "approved_artifact_count": len(approved_artifacts),
            "duration_frames": total_frames,
            "duration_seconds": audio_duration,
            "final_scene_end_frame": (
                scenes[-1].start_frame + scenes[-1].duration_frames
            ),
            "timeline_exact": (
                scenes[-1].start_frame + scenes[-1].duration_frames
                == total_frames
            ),
            "single_composition": True,
        }
        save_json(validation, validation_path)

        run_manager.complete_step(
            STEP_NAME,
            outputs={
                "render_spec": str(output_path),
                "resolved_assets": str(resolved_assets_path),
                "render_validation": str(validation_path),
                "duration_frames": total_frames,
                "scene_count": len(scenes),
                "generated_scene_count": generated_scene_count,
                "library_scene_count": library_scene_count,
            },
        )

        return render_specification

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )
        raise


def main():
    arguments = build_argument_parser().parse_args()

    try:
        specification = compile_render_spec(arguments.run_dir)
        generated_count = specification.metadata.get(
            "generated_scene_count",
            0,
        )
        library_count = specification.metadata.get(
            "library_scene_count",
            0,
        )

        print()
        print("STEP 08 COMPLETED")
        print(f"Frames: {specification.video.duration_frames}")
        print(f"Scenes: {len(specification.scenes)}")
        print(f"Generated scenes: {generated_count}")
        print(f"Library scenes: {library_count}")
        print("Render mode: single master composition")
        print()
        return 0

    except Exception as error:
        print()
        print("STEP 08 FAILED")
        print(f"{type(error).__name__}: {error}")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
