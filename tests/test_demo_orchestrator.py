"""Tests for the demo orchestrator helpers."""
import json
from pathlib import Path
import run_demo_pipeline


def test_artifact_gate_detects_required_pending(tmp_path):
    root = tmp_path
    folder = root / "05c_artifacts"
    folder.mkdir()
    payload = {
        "artifacts": [
            {
                "artifact_id": "portrait",
                "artifact_type": "portrait",
                "required": True,
                "approved": False,
                "status": "needs_review",
                "source_strategy": "extract_from_dossier",
            }
        ]
    }
    (folder / "artifact_manifest_final.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    pending = run_demo_pipeline.artifact_gate(root)
    assert pending[0]["artifact_id"] == "portrait"


def test_artifact_gate_ignores_approved(tmp_path):
    folder = tmp_path / "05c_artifacts"
    folder.mkdir()
    payload = {
        "artifacts": [
            {
                "artifact_id": "chart",
                "required": True,
                "approved": True,
                "status": "ready",
            }
        ]
    }
    (folder / "artifact_manifest_final.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    assert run_demo_pipeline.artifact_gate(tmp_path) == []
