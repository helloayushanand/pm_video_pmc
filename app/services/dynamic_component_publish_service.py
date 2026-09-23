"""Publish fully approved generated components into the Remotion renderer."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from app.config import RENDERER_DIR
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DynamicComponentPublishError(Exception):
    """Raised when generated components cannot be safely published."""


class DynamicComponentPublishService:
    """Publish source that passed compilation and visual QA."""

    def publish(self, run_directory, output_directory):
        run_path = Path(run_directory).expanduser().resolve()
        output_path = Path(output_directory).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        compiled_path = (
            run_path
            / "05e_component_compilation"
            / "approved_compiled_components.json"
        )
        preview_path = (
            run_path
            / "05f_component_previews"
            / "preview_qa_report.json"
        )
        approval_path = (
            run_path
            / "05d_generated_components"
            / "approved_components.json"
        )
        artifact_path = (
            run_path
            / "05c_artifacts"
            / "artifact_manifest_final.json"
        )

        for required_path in (
            compiled_path,
            preview_path,
            approval_path,
            artifact_path,
        ):
            if not required_path.exists():
                raise FileNotFoundError(
                    f"Required Phase 7 input is missing: {required_path}"
                )

        compiled_data = load_json(compiled_path)
        preview_data = load_json(preview_path)
        approval_data = load_json(approval_path)
        artifact_data = load_json(artifact_path)

        if not preview_data.get("ready_for_phase_7"):
            raise DynamicComponentPublishError(
                "Visual QA is not approved. Phase 7 publishing is blocked."
            )

        approved_by_scene = {
            item["scene_id"]: item
            for item in approval_data.get("approved_components", [])
        }
        preview_by_scene = {
            item["scene_id"]: item
            for item in preview_data.get("results", [])
        }

        renderer = Path(RENDERER_DIR).expanduser().resolve()
        publish_root = (
            renderer
            / "src"
            / "generated-runs"
            / run_path.name
        )
        components_dir = publish_root / "components"
        if publish_root.exists():
            shutil.rmtree(publish_root)
        components_dir.mkdir(parents=True, exist_ok=True)

        published = []
        blocked = []

        for item in compiled_data.get("compiled_components", []):
            scene_id = item["scene_id"]
            approval = approved_by_scene.get(scene_id)
            preview = preview_by_scene.get(scene_id)
            verification = self._verify_component(item, approval, preview)

            if not verification["verified"]:
                blocked.append(verification)
                continue

            source = Path(item["source_file"]).expanduser().resolve()
            destination = components_dir / source.name
            source_text = source.read_text(encoding="utf-8-sig")
            published_text = self._normalise_renderer_imports(source_text)
            destination.write_text(published_text, encoding="utf-8")

            published_hash = self._sha256_text(published_text)
            published.append(
                {
                    "scene_id": scene_id,
                    "component_name": item["component_name"],
                    "source_file": str(source),
                    "source_sha256": item["source_sha256"],
                    "published_source": str(destination),
                    "published_sha256": published_hash,
                    "fallback_component": item["fallback_component"],
                    "visual_approved": True,
                    "compile_status": item["compile_status"],
                }
            )

        if blocked:
            report = {
                "status": "blocked",
                "published_count": len(published),
                "blocked_count": len(blocked),
                "published": published,
                "blocked": blocked,
            }
            save_json(report, output_path / "dynamic_publish_report.json")
            raise DynamicComponentPublishError(
                "One or more generated components failed Phase 7 verification."
            )

        registry_path = self._write_registry(publish_root, published)
        index_path = self._write_index(publish_root)
        manifest_path = self._write_manifest(
            publish_root,
            run_path,
            published,
            artifact_data,
        )

        report = {
            "status": "published",
            "run_id": run_path.name,
            "publish_root": str(publish_root),
            "published_count": len(published),
            "blocked_count": 0,
            "registry_path": str(registry_path),
            "index_path": str(index_path),
            "manifest_path": str(manifest_path),
            "published": published,
            "ready_for_runtime_integration": len(published) > 0,
        }
        save_json(report, output_path / "dynamic_publish_report.json")
        (output_path / "dynamic_publish_summary.md").write_text(
            self._markdown(report),
            encoding="utf-8",
        )
        logger.info(
            "Published %s generated component(s) for run %s.",
            len(published),
            run_path.name,
        )
        return report

    def _verify_component(self, compiled, approval, preview):
        scene_id = compiled["scene_id"]
        errors = []
        source = Path(compiled["source_file"]).expanduser().resolve()

        if not source.exists():
            errors.append("source_missing")
            actual_hash = None
        else:
            actual_hash = self._sha256_file(source)

        expected_hash = compiled.get("source_sha256")
        if actual_hash != expected_hash:
            errors.append("compiled_source_hash_mismatch")

        if approval is None:
            errors.append("approval_missing")
        else:
            if not approval.get("approved_for_compilation"):
                errors.append("source_not_approved")
            if approval.get("source_sha256") != actual_hash:
                errors.append("approval_hash_mismatch")

        if preview is None:
            errors.append("visual_qa_missing")
        else:
            if not preview.get("visual_approved"):
                errors.append("visual_qa_not_approved")
            if preview.get("status") != "visual_approved":
                errors.append("preview_status_not_approved")

        if compiled.get("compile_status") != "compiled":
            errors.append("component_not_compiled")

        return {
            "scene_id": scene_id,
            "component_name": compiled.get("component_name"),
            "verified": not errors,
            "errors": errors,
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
        }

    @staticmethod
    def _normalise_renderer_imports(source_text):
        """Convert the generation alias into a stable renderer-relative import."""
        value = (
            source_text
            .replace('from "@/dynamic-sdk"', 'from "../../../dynamic-sdk"')
            .replace("from '@/dynamic-sdk'", "from '../../../dynamic-sdk'")
        )
        if "@/dynamic-sdk" in value:
            raise DynamicComponentPublishError(
                "Published source contains an unresolved Dynamic SDK alias."
            )
        return value

    @staticmethod
    def _write_registry(publish_root, published):
        lines = [
            'import type React from "react";',
            'import type {GeneratedSceneProps} from "../../dynamic-sdk";',
            "",
        ]
        entries = []
        fallback_entries = []
        for index, item in enumerate(published, start=1):
            alias = f"GeneratedComponent{index}"
            stem = Path(item["published_source"]).stem
            lines.append(
                f'import {{{item["component_name"]} as {alias}}} '
                f'from "./components/{stem}";'
            )
            entries.append(f'  "{item["scene_id"]}": {alias},')
            fallback_entries.append(
                f'  "{item["scene_id"]}": '
                f'"{item["fallback_component"]}",'
            )

        lines.extend(
            [
                "",
                "export const generatedSceneRegistry: Record<",
                "  string,",
                "  React.FC<GeneratedSceneProps>",
                "> = {",
                *entries,
                "};",
                "",
                "export const generatedSceneFallbackRegistry: "
                "Record<string, string> = {",
                *fallback_entries,
                "};",
                "",
            ]
        )
        path = publish_root / "generatedRegistry.ts"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    @staticmethod
    def _write_index(publish_root):
        path = publish_root / "index.ts"
        path.write_text(
            'export {generatedSceneRegistry, '
            'generatedSceneFallbackRegistry} '
            'from "./generatedRegistry";\n',
            encoding="utf-8",
        )
        return path

    def _write_manifest(self, publish_root, run_path, published, artifact_data):
        payload = {
            "schema_version": "1.0",
            "run_id": run_path.name,
            "components": published,
            "artifact_manifest_sha256": self._sha256_text(
                json.dumps(
                    artifact_data,
                    sort_keys=True,
                    ensure_ascii=False,
                )
            ),
        }
        path = publish_root / "generatedManifest.json"
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _sha256_file(path):
        text = Path(path).read_text(encoding="utf-8-sig")
        return DynamicComponentPublishService._sha256_text(text)

    @staticmethod
    def _sha256_text(value):
        canonical = value.replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _markdown(report):
        lines = [
            "# Dynamic Component Publish Summary",
            "",
            f"Run ID: {report['run_id']}",
            f"Published components: {report['published_count']}",
            f"Blocked components: {report['blocked_count']}",
            f"Ready for runtime integration: "
            f"{report['ready_for_runtime_integration']}",
            "",
            "## Published Components",
            "",
        ]
        for item in report["published"]:
            lines.extend(
                [
                    f"### {item['scene_id']}",
                    f"- Component: {item['component_name']}",
                    f"- Published source: `{item['published_source']}`",
                    f"- Fallback: {item['fallback_component']}",
                    f"- Compile status: {item['compile_status']}",
                    f"- Visual approved: {item['visual_approved']}",
                    "",
                ]
            )
        return "\n".join(lines)
