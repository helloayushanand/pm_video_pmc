"""Executable pipeline stages for candidate video generation."""

PIPELINE_STEPS = [
    "prepare_document",
    "extract_dossier",
    "validate_extraction",
    "select_video_content",
    "generate_scenes",
    "generate_artifacts",
    "generate_audio",
    "render_video",
]
