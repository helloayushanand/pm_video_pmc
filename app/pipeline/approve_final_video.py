"""Approve or reject the final dynamic demo video."""
from __future__ import annotations
import argparse
from app.services.final_video_qa_service import create_final_video_approval


def main():
    parser = argparse.ArgumentParser(description="Approve the final dynamic demo video.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--decision", required=True, choices=["approved_for_demo", "rejected"])
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    path = create_final_video_approval(args.run_dir, args.reviewer, args.decision, args.notes)
    print(f"Final video decision saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
