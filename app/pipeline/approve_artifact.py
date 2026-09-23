"""Approve an extracted, generated, or local artifact for Phase 3B."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.utils.json_utils import save_json


def main():
    parser = argparse.ArgumentParser(description="Approve one artifact file.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--selected-path", required=True)
    parser.add_argument("--description", default="Manually approved artifact.")
    args = parser.parse_args()

    run_path = Path(args.run_dir).expanduser().resolve()
    selected = Path(args.selected_path).expanduser().resolve()
    if not selected.exists() or not selected.is_file():
        raise FileNotFoundError(f"Selected artifact does not exist: {selected}")

    approved_dir = run_path / "05c_artifacts" / "approved"
    approved_dir.mkdir(parents=True, exist_ok=True)
    approval_path = approved_dir / f"{args.artifact_id}.approval.json"
    save_json(
        {
            "artifact_id": args.artifact_id,
            "approved": True,
            "selected_path": str(selected),
            "source_description": args.description,
        },
        approval_path,
    )
    print(f"Approval saved: {approval_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
