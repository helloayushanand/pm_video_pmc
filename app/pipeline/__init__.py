"""Executable pipeline stages for candidate video generation."""

PIPELINE_STEPS = [
    "prepare_document",
    "extract_dossier",
    "validate_extraction",
    "select_video_content",
    "generate_storyboard",
    "generate_audio",
    "align_audio",
    "compile_render_spec",
    "render_video",
    "run_quality_checks",
    "calculate_costs",
]
