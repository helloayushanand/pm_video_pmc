"""Approve or reject one generated component after source review."""

from __future__ import annotations

import argparse

from app.services.component_review_service import create_approval


def main():
    parser = argparse.ArgumentParser(description="Approve generated TSX source.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--scene-id", required=True)
    parser.add_argument(
        "--decision",
        required=True,
        choices=["approved_for_compilation", "rejected_use_fallback"],
    )
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    path = create_approval(
        run_directory=args.run_dir,
        scene_id=args.scene_id,
        decision=args.decision,
        reviewer=args.reviewer,
        notes=args.notes,
    )
    print(f"Component review decision saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
