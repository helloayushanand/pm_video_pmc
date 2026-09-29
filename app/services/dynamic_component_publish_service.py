"""Publish compiled generated components into the Remotion renderer."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from app.config import RENDERER_DIR
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger


logger = get_logger(__name__)


class DynamicComponentPublishError(Exception):
    """Raised when generated components cannot be safely published."""


class DynamicComponentPublishService:
    """
    Publish successfully compiled generated components into Remotion.

    Architecture:

    generated source
        ↓
    compiled successfully
        ↓
    verify source hash
        ↓
    publish run-specific copy
        ↓
    publish stable generated-current copy
        ↓
    CandidateVideo imports generated-current registry directly

    Visual QA is optional in the POC architecture and is not a
    prerequisite for publishing.
    """

    def publish(
        self,
        run_directory,
        output_directory,
    ):
        run_path = (
            Path(run_directory)
            .expanduser()
            .resolve()
        )

        output_path = (
            Path(output_directory)
            .expanduser()
            .resolve()
        )

        output_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        compiled_path = (
            run_path
            / "05e_component_compilation"
            / "approved_compiled_components.json"
        )

        artifact_path = (
            run_path
            / "05c_artifacts"
            / "artifact_manifest_final.json"
        )

        preview_path = (
            run_path
            / "05f_component_previews"
            / "preview_qa_report.json"
        )

        if not compiled_path.exists():
            raise FileNotFoundError(
                "Compiled component manifest is missing: "
                f"{compiled_path}"
            )

        if not artifact_path.exists():
            raise FileNotFoundError(
                "Final artifact manifest is missing: "
                f"{artifact_path}"
            )

        compiled_data = load_json(
            compiled_path
        )

        artifact_data = load_json(
            artifact_path
        )


        preview_data = (
            load_json(preview_path)
            if preview_path.exists()
            else {}
        )

        preview_by_scene = {
            item["scene_id"]: item
            for item in preview_data.get(
                "results",
                [],
            )
            if item.get("scene_id")
        }

        renderer = (
            Path(RENDERER_DIR)
            .expanduser()
            .resolve()
        )
        archive_root = (
            renderer
            / "src"
            / "generated-runs"
            / run_path.name
        )


        current_root = (
            renderer
            / "src"
            / "generated-current"
        )

        archive_components = (
            archive_root
            / "components"
        )

        current_components = (
            current_root
            / "components"
        )


        if archive_root.exists():
            shutil.rmtree(
                archive_root
            )

        if current_root.exists():
            shutil.rmtree(
                current_root
            )

        archive_components.mkdir(
            parents=True,
            exist_ok=True,
        )

        current_components.mkdir(
            parents=True,
            exist_ok=True,
        )

        published = []
        blocked = []

        for item in compiled_data.get(
            "compiled_components",
            [],
        ):
            verification = (
                self._verify_component(
                    item
                )
            )

            if not verification[
                "verified"
            ]:
                blocked.append(
                    verification
                )

                continue

            scene_id = item[
                "scene_id"
            ]

            source = (
                Path(
                    item[
                        "source_file"
                    ]
                )
                .expanduser()
                .resolve()
            )

            source_text = (
                source.read_text(
                    encoding="utf-8-sig"
                )
            )

            published_text = (
                self
                ._normalise_renderer_imports(
                    source_text
                )
            )

            archive_destination = (
                archive_components
                / source.name
            )

            current_destination = (
                current_components
                / source.name
            )

            archive_destination.write_text(
                published_text,
                encoding="utf-8",
            )

            current_destination.write_text(
                published_text,
                encoding="utf-8",
            )

            published_hash = (
                self._sha256_text(
                    published_text
                )
            )

            preview = (
                preview_by_scene
                .get(scene_id)
            )

            visual_approved = (
                bool(
                    preview.get(
                        "visual_approved"
                    )
                )
                if preview
                else None
            )

            published.append(
                {
                    "scene_id":
                        scene_id,

                    "component_name":
                        item[
                            "component_name"
                        ],

                    "source_file":
                        str(source),

                    "source_sha256":
                        item[
                            "source_sha256"
                        ],

                    "published_source":
                        str(
                            archive_destination
                        ),

                    "runtime_source":
                        str(
                            current_destination
                        ),

                    "published_sha256":
                        published_hash,

                    "fallback_component":
                        item.get(
                            "fallback_component",
                            "GenericScene",
                        ),
                    "visual_approved":
                        visual_approved,

                    "compile_status":
                        item.get(
                            "compile_status"
                        ),
                }
            )

        if blocked:
            report = {
                "status":
                    "blocked",

                "run_id":
                    run_path.name,

                "published_count":
                    len(published),

                "blocked_count":
                    len(blocked),

                "published":
                    published,

                "blocked":
                    blocked,
            }

            save_json(
                report,
                output_path
                / "dynamic_publish_report.json",
            )

            raise DynamicComponentPublishError(
                "One or more supposedly compiled generated "
                "components failed publishing verification."
            )

        archive_registry_path = (
            self._write_registry(
                archive_root,
                published,
            )
        )

        archive_index_path = (
            self._write_index(
                archive_root
            )
        )

        archive_manifest_path = (
            self._write_manifest(
                publish_root=archive_root,
                run_path=run_path,
                published=published,
                artifact_data=artifact_data,
            )
        )

        current_registry_path = (
            self._write_registry(
                current_root,
                published,
            )
        )

        current_index_path = (
            self._write_index(
                current_root
            )
        )

        current_manifest_path = (
            self._write_manifest(
                publish_root=current_root,
                run_path=run_path,
                published=published,
                artifact_data=artifact_data,
            )
        )

        report = {
            "status":
                "published",

            "run_id":
                run_path.name,

            "publish_root":
                str(
                    archive_root
                ),

            "runtime_publish_root":
                str(
                    current_root
                ),

            "published_count":
                len(published),

            "blocked_count":
                0,

            "registry_path":
                str(
                    archive_registry_path
                ),

            "index_path":
                str(
                    archive_index_path
                ),

            "manifest_path":
                str(
                    archive_manifest_path
                ),

            "runtime_registry_path":
                str(
                    current_registry_path
                ),

            "runtime_index_path":
                str(
                    current_index_path
                ),

            "runtime_manifest_path":
                str(
                    current_manifest_path
                ),

            "published":
                published,

            "ready_for_runtime_integration":
                len(published) > 0,
        }

        save_json(
            report,
            output_path
            / "dynamic_publish_report.json",
        )

        (
            output_path
            / "dynamic_publish_summary.md"
        ).write_text(
            self._markdown(
                report
            ),
            encoding="utf-8",
        )

        logger.info(
            "Published %s generated "
            "component(s) for run %s.",
            len(published),
            run_path.name,
        )

        logger.info(
            "Stable runtime registry: %s",
            current_registry_path,
        )

        return report

    def _verify_component(
        self,
        compiled,
    ):
        """
        Verify only deterministic publishing requirements.

        For the POC:

        required:
        - source exists
        - source hash matches compiled manifest
        - compile_status == compiled

        not required:
        - manual approval
        - Visual QA
        """

        scene_id = compiled[
            "scene_id"
        ]

        errors = []

        source = (
            Path(
                compiled[
                    "source_file"
                ]
            )
            .expanduser()
            .resolve()
        )

        if not source.exists():
            errors.append(
                "source_missing"
            )

            actual_hash = None

        else:
            actual_hash = (
                self._sha256_file(
                    source
                )
            )

        expected_hash = (
            compiled.get(
                "source_sha256"
            )
        )

        if (
            expected_hash
            and actual_hash
            != expected_hash
        ):
            errors.append(
                "compiled_source_hash_mismatch"
            )

        if (
            compiled.get(
                "compile_status"
            )
            != "compiled"
        ):
            errors.append(
                "component_not_compiled"
            )

        return {
            "scene_id":
                scene_id,

            "component_name":
                compiled.get(
                    "component_name"
                ),

            "verified":
                not errors,

            "errors":
                errors,

            "expected_sha256":
                expected_hash,

            "actual_sha256":
                actual_hash,
        }

    @staticmethod
    def _normalise_renderer_imports(
        source_text,
    ):
        """
        Convert generation aliases into stable imports.

        Generated component path:

        src/generated-current/components/Foo.tsx

        Dynamic SDK path:

        src/dynamic-sdk
        """

        value = (
            source_text

            .replace(
                'from "@/dynamic-sdk"',
                'from "../../dynamic-sdk"',
            )

            .replace(
                "from '@/dynamic-sdk'",
                "from '../../dynamic-sdk'",
            )
        )

        if "@/dynamic-sdk" in value:
            raise (
                DynamicComponentPublishError(
                    "Published source contains "
                    "an unresolved Dynamic SDK alias."
                )
            )

        return value

    @staticmethod
    def _write_registry(
        publish_root,
        published,
    ):
        lines = [
            (
                'import type React '
                'from "react";'
            ),

            (
                'import type '
                '{GeneratedSceneProps} '
                'from "../dynamic-sdk";'
            ),

            "",
        ]

        entries = []

        fallback_entries = []

        for index, item in enumerate(
            published,
            start=1,
        ):
            alias = (
                f"GeneratedComponent"
                f"{index}"
            )

            stem = Path(
                item[
                    "runtime_source"
                ]
                if "runtime_source"
                in item
                else item[
                    "published_source"
                ]
            ).stem

            lines.append(
                f'import '
                f'{{'
                f'{item["component_name"]} '
                f'as {alias}'
                f'}} '
                f'from '
                f'"./components/{stem}";'
            )

            entries.append(
                f'  '
                f'"{item["scene_id"]}": '
                f'{alias},'
            )

            fallback_entries.append(
                f'  '
                f'"{item["scene_id"]}": '
                f'"{item["fallback_component"]}",'
            )

        lines.extend(
            [
                "",

                (
                    "export const "
                    "generatedSceneRegistry: "
                    "Record<"
                ),

                "  string,",

                (
                    "  React.FC<"
                    "GeneratedSceneProps>"
                ),

                "> = {",

                *entries,

                "};",

                "",

                (
                    "export const "
                    "generatedSceneFallbackRegistry: "
                    "Record<string, string> = {"
                ),

                *fallback_entries,

                "};",

                "",
            ]
        )

        path = (
            publish_root
            / "generatedRegistry.ts"
        )

        path.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

        return path

    @staticmethod
    def _write_index(
        publish_root,
    ):
        path = (
            publish_root
            / "index.ts"
        )

        path.write_text(
            (
                "export {\n"
                "  generatedSceneRegistry,\n"
                "  generatedSceneFallbackRegistry,\n"
                "} from "
                '"./generatedRegistry";\n'
            ),
            encoding="utf-8",
        )

        return path

    def _write_manifest(
        self,
        publish_root,
        run_path,
        published,
        artifact_data,
    ):
        payload = {
            "schema_version":
                "2.0",

            "run_id":
                run_path.name,

            "components":
                published,

            "artifact_manifest_sha256":
                self._sha256_text(
                    json.dumps(
                        artifact_data,
                        sort_keys=True,
                        ensure_ascii=False,
                    )
                ),
        }

        path = (
            publish_root
            / "generatedManifest.json"
        )

        path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return path

    @staticmethod
    def _sha256_file(
        path,
    ):
        text = (
            Path(path)
            .read_text(
                encoding="utf-8-sig"
            )
        )

        return (
            DynamicComponentPublishService
            ._sha256_text(
                text
            )
        )

    @staticmethod
    def _sha256_text(
        value,
    ):
        canonical = (
            value
            .replace(
                "\r\n",
                "\n",
            )
            .replace(
                "\r",
                "\n",
            )
        )

        return hashlib.sha256(
            canonical.encode(
                "utf-8"
            )
        ).hexdigest()

    @staticmethod
    def _markdown(
        report,
    ):
        lines = [
            (
                "# Dynamic Component "
                "Publish Summary"
            ),

            "",

            (
                f"Run ID: "
                f"{report['run_id']}"
            ),

            (
                "Published components: "
                f"{report['published_count']}"
            ),

            (
                "Blocked components: "
                f"{report['blocked_count']}"
            ),

            (
                "Ready for runtime integration: "
                f"{report['ready_for_runtime_integration']}"
            ),

            "",

            (
                "Stable runtime registry: "
                f"`{report['runtime_registry_path']}`"
            ),

            "",

            "## Published Components",

            "",
        ]

        for item in report[
            "published"
        ]:
            visual_status = (
                "not_run"
                if item[
                    "visual_approved"
                ] is None
                else str(
                    item[
                        "visual_approved"
                    ]
                )
            )

            lines.extend(
                [
                    (
                        f"### "
                        f"{item['scene_id']}"
                    ),

                    (
                        "- Component: "
                        f"{item['component_name']}"
                    ),

                    (
                        "- Runtime source: "
                        f"`{item['runtime_source']}`"
                    ),

                    (
                        "- Fallback: "
                        f"{item['fallback_component']}"
                    ),

                    (
                        "- Compile status: "
                        f"{item['compile_status']}"
                    ),

                    (
                        "- Visual QA: "
                        f"{visual_status}"
                    ),

                    "",
                ]
            )

        return "\n".join(lines)