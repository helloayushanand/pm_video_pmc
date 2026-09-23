"""Promote a reviewed compiler-repaired source into Phase 4D review."""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path
from app.utils.json_utils import load_json, save_json

def main():
    parser = argparse.ArgumentParser(description="Promote one repaired source for renewed human approval.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--scene-id", required=True)
    args = parser.parse_args()
    run_path = Path(args.run_dir).expanduser().resolve()
    repair_report_path = run_path / "05e_component_compilation" / "compiler_repair_report.json"
    report = load_json(repair_report_path)
    matches = [item for item in report.get("results", []) if item.get("scene_id") == args.scene_id and item.get("status") == "repaired_compiled_pending_approval"]
    if not matches:
        raise RuntimeError(f"No compiled repaired source found for scene {args.scene_id}.")
    repaired = Path(matches[0]["repaired_source_file"]).resolve()
    generation_results_path = run_path / "05d_generated_components" / "generation_results.json"
    results = load_json(generation_results_path)
    matched = False
    for item in results:
        if item.get("scene_id") != args.scene_id:
            continue
        original = Path(item["source_file"]).resolve()
        backup = original.with_suffix(original.suffix + ".pre_compiler_repair")
        if original.exists() and not backup.exists():
            shutil.copy2(original, backup)
        shutil.copy2(repaired, original)
        item["generated_source"] = original.read_text(encoding="utf-8-sig")
        if item.get("generated_component"):
            item["generated_component"]["source_code"] = item["generated_source"]
        item["status"] = "ready_for_compilation"
        item["compiler_repair_promoted"] = True
        matched = True
    if not matched:
        raise RuntimeError(f"Scene not found in generation results: {args.scene_id}")
    save_json(results, generation_results_path)
    approval_path = run_path / "05d_generated_components" / "approvals" / f"{args.scene_id}.approval.json"
    if approval_path.exists():
        approval_path.unlink()
    print(f"Promoted repaired source for scene {args.scene_id}.")
    print("Run component_review, inspect the source, and approve the new hash.")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
