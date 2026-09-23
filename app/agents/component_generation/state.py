"""LangGraph shared state."""
from __future__ import annotations
from typing import TypedDict

class DynamicComponentState(TypedDict, total=False):
    run_id: str
    scene_id: str
    scene_input: dict
    generated_component: dict | None
    generated_source: str | None
    source_validation: dict | None
    source_validation_errors: list[str]
    generation_attempts: int
    source_repair_attempts: int
    max_generation_attempts: int
    max_source_repair_attempts: int
    status: str
    fallback_component: str
    output_directory: str
    source_file: str | None
    manifest_file: str | None
    events: list[dict]
