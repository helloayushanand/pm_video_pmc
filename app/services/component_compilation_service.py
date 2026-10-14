"""Compile approved generated components in an isolated workspace."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from app.config import RENDERER_DIR
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger
logger = get_logger(__name__)

class ComponentCompilationError(Exception):
    """Raised when the compilation workspace cannot be prepared."""

class ComponentCompilationService:
    """Verify source snapshots and type-check each generated scene separately."""

    def compile_approved_components(self, run_directory, output_directory, timeout_seconds=120):
        run_path = Path(run_directory).expanduser().resolve()
        output_path = Path(output_directory).expanduser().resolve()
        approved_path = run_path / "05d_generated_components" / "approved_components.json"
        if not approved_path.exists():
            raise FileNotFoundError("approved_components.json is missing. Complete Phase 4D first.")
        approved_data = load_json(approved_path)
        approved = approved_data.get("approved_components", [])
        if not approved:
            raise ComponentCompilationError("No generated components are approved for compilation.")

        renderer = Path(RENDERER_DIR).expanduser().resolve()
        node_modules = renderer / "node_modules"
        sdk_source = renderer / "src" / "dynamic-sdk"
        if not node_modules.exists():
            raise FileNotFoundError(f"Renderer dependencies are missing: {node_modules}")
        if not sdk_source.exists():
            raise FileNotFoundError(f"Dynamic Scene SDK is missing: {sdk_source}")

        output_path.mkdir(parents=True, exist_ok=True)
        workspace = renderer / ".phase5_workspaces" / run_path.name
        if workspace.exists():
            shutil.rmtree(workspace)
        source_dir = workspace / "src"
        generated_dir = source_dir / "generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(sdk_source, source_dir / "dynamic-sdk")

        verification = []
        copied = []
        for item in approved:
            source = Path(item["source_file"]).expanduser().resolve()
            expected_hash = item["source_sha256"]
            if not source.exists():
                verification.append(self._verification(item, False, "source_missing", None))
                continue
            actual_hash = self._sha256_file(source)
            if actual_hash != expected_hash:
                verification.append(self._verification(item, False, "approval_hash_mismatch", actual_hash))
                continue
            scene_slug = self._safe_path_component(item["scene_id"])
            destination = generated_dir / scene_slug / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            export_kind = self._component_export_kind(
                source.read_text(encoding="utf-8-sig"),
                item["component_name"],
            )
            verification.append(self._verification(item, True, "verified", actual_hash))
            copied.append(
                {
                    **item,
                    "workspace_source": str(destination),
                    "export_kind": export_kind,
                }
            )

        package_path = self._write_package_json(workspace)
        verification_by_scene = {
            item["scene_id"]: item for item in verification
        }
        component_results = [
            self._result_from_verification(
                item,
                verification_by_scene[item["scene_id"]],
            )
            for item in approved
            if not verification_by_scene[item["scene_id"]]["verified"]
        ]
        compiler_outputs = []
        all_errors = []
        return_codes = []
        timed_out = False

        for item in copied:
            registry_path = self._write_registry(
                source_dir,
                [item],
            )
            tsconfig_path = self._write_tsconfig(
                workspace,
                [
                    item["workspace_source"],
                    str(registry_path),
                ],
            )
            command = [
                str(node_modules / ".bin" / "tsc.cmd"),
                "--project",
                str(tsconfig_path),
                "--pretty",
                "false",
            ]
            logger.info(
                "Type-checking generated scene %s independently.",
                item["scene_id"],
            )
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                stdout = completed.stdout or ""
                stderr = completed.stderr or ""
                return_code = completed.returncode
                item_timed_out = False
            except subprocess.TimeoutExpired as error:
                stdout = self._output_text(error.stdout)
                stderr = self._output_text(error.stderr)
                return_code = None
                item_timed_out = True

            output = stdout + "\n" + stderr
            errors = self._parse_compiler_output(output)
            item_compiled = not item_timed_out and return_code == 0
            compiler_outputs.append(
                {
                    "scene_id": item["scene_id"],
                    "command": command,
                    "stdout": stdout,
                    "stderr": stderr,
                    "return_code": return_code,
                    "timed_out": item_timed_out,
                    "errors": errors,
                }
            )
            all_errors.extend(
                {"scene_id": item["scene_id"], **error}
                for error in errors
            )
            if return_code is not None:
                return_codes.append(return_code)
            timed_out = timed_out or item_timed_out
            component_results.append(
                {
                    "scene_id": item["scene_id"],
                    "component_name": item["component_name"],
                    "source_file": item["source_file"],
                    "source_sha256": item["source_sha256"],
                    "workspace_source": item["workspace_source"],
                    "export_kind": item["export_kind"],
                    "fallback_component": item["fallback_component"],
                    "compile_status": (
                        "compiled"
                        if item_compiled
                        else "timeout"
                        if item_timed_out
                        else "compiler_error"
                    ),
                    "compile_errors": errors,
                    "fallback_reason": (
                        None
                        if item_compiled
                        else "compile_timeout"
                        if item_timed_out
                        else "typescript_compile_failed"
                    ),
                    "eligible_for_phase_5b_repair": False,
                }
            )

        compiled_components = [
            item for item in component_results
            if item["compile_status"] == "compiled"
        ]
        verification_failed = any(
            not item["verified"] for item in verification
        )
        all_compiled = (
            bool(copied)
            and len(compiled_components) == len(copied)
            and not verification_failed
        )
        if all_compiled:
            status = "compiled"
        elif compiled_components:
            status = "partially_compiled"
        elif timed_out:
            status = "timeout"
        elif verification_failed:
            status = "component_failures"
        else:
            status = "compiler_error"

        registry_path = self._write_registry(
            source_dir,
            compiled_components,
        )
        aggregate_stdout = "\n".join(
            item["stdout"] for item in compiler_outputs
        )
        aggregate_stderr = "\n".join(
            item["stderr"] for item in compiler_outputs
        )
        aggregate_return_code = (
            0 if compiled_components
            else 2 if return_codes or timed_out or verification_failed
            else None
        )
        report = {
            "status": status,
            "compiled": all_compiled,
            "compiled_count": len(compiled_components),
            "failed_count": len(component_results) - len(compiled_components),
            "timed_out": timed_out,
            "return_code": aggregate_return_code,
            "compiler_runs": compiler_outputs,
            "workspace": str(workspace),
            "registry": str(registry_path),
            "tsconfig": str(workspace / "tsconfig.json"),
            "package_json": str(package_path),
            "verification": verification,
            "compiler_stdout": aggregate_stdout,
            "compiler_stderr": aggregate_stderr,
            "compiler_errors": all_errors,
            "components": component_results,
        }
        save_json(report, output_path / "compilation_report.json")
        save_json(all_errors, output_path / "compiler_errors.json")
        save_json(
            {
                "schema_version": "1.0",
                "compiled_components": compiled_components,
                "compiled_count": len(compiled_components),
                "workspace_registry": str(registry_path),
                "failed_components": [
                    item for item in component_results
                    if item["compile_status"] != "compiled"
                ],
            },
            output_path / "approved_compiled_components.json",
        )
        shutil.copy2(registry_path, output_path / "compiled_registry.ts")
        (output_path / "compilation_summary.md").write_text(self._markdown(report), encoding="utf-8")
        return report

    @staticmethod
    def _write_registry(source_dir, components):
        lines = ['import type React from "react";', 'import type {GeneratedSceneProps} from "@/dynamic-sdk";', '']
        entries = []
        for index, item in enumerate(components, start=1):
            alias = f"GeneratedComponent{index}"
            source = Path(item["workspace_source"])
            module_path = (
                "./"
                + source.relative_to(source_dir)
                .with_suffix("")
                .as_posix()
            )
            if item.get("export_kind") == "default":
                lines.append(f'import {alias} from "{module_path}";')
            else:
                lines.append(f'import {{{item["component_name"]} as {alias}}} from "{module_path}";')
            entries.append(f'  "{item["scene_id"]}": {alias},')
        lines.extend(['', 'export const compiledSceneRegistry: Record<string, React.FC<GeneratedSceneProps>> = {', *entries, '};', ''])
        path = source_dir / "registry.ts"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    @staticmethod
    def _component_export_kind(source, component_name):
        named_export = re.search(
            rf"\bexport\s+(?:const|let|var|function|class)\s+"
            rf"{re.escape(component_name)}\b",
            source,
        )
        if named_export:
            return "named"
        if re.search(r"\bexport\s+default\b", source):
            return "default"
        return "named"

    @staticmethod
    def _write_tsconfig(workspace, generated_sources=None):
        payload = {
            "compilerOptions": {
                "target": "ES2020", "module": "ESNext", "moduleResolution": "Node",
                "jsx": "react-jsx", "strict": True, "noEmit": True,
                "esModuleInterop": True, "allowSyntheticDefaultImports": True,
                "skipLibCheck": True, "baseUrl": "./src",
                "paths": {"@/*": ["*"]}, "types": ["node"],
                "lib": ["ES2020", "DOM", "DOM.Iterable"]
            },
            "include": [
                "src/dynamic-sdk/**/*.ts",
                "src/dynamic-sdk/**/*.tsx",
                *(generated_sources or ["src/**/*.ts", "src/**/*.tsx"]),
            ],
            "exclude": ["node_modules"]
        }
        path = workspace / "tsconfig.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _safe_path_component(value):
        safe = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in value
        )
        if not safe:
            raise ComponentCompilationError(
                "Scene ID cannot be used as a workspace directory."
            )
        suffix = hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()[:8]
        return f"{safe}-{suffix}"

    @staticmethod
    def _output_text(value):
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value or ""

    @staticmethod
    def _result_from_verification(item, verification):
        return {
            "scene_id": item["scene_id"],
            "component_name": item.get("component_name"),
            "source_file": item.get("source_file"),
            "source_sha256": item.get("source_sha256"),
            "fallback_component": item.get("fallback_component"),
            "compile_status": verification["status"],
            "compile_errors": [],
            "fallback_reason": verification["status"],
            "eligible_for_phase_5b_repair": False,
        }

    @staticmethod
    def _write_package_json(workspace):
        payload = {"name": "generated-component-compilation", "private": True, "version": "0.0.0"}
        path = workspace / "package.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _parse_compiler_output(output):
        errors = []
        for line in output.splitlines():
            stripped = line.strip()
            if " error TS" in stripped or stripped.startswith("error TS"):
                errors.append({"raw": stripped})
        return errors

    @staticmethod
    def _sha256_file(path):
        """Calculate the same canonical source hash used by review."""

        source_text = Path(path).read_text(
            encoding="utf-8-sig"
        )

        canonical_text = source_text.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        )

        return hashlib.sha256(
            canonical_text.encode("utf-8")
        ).hexdigest()
    
    @staticmethod
    def _verification(item, verified, status, actual_hash):
        return {
            "scene_id": item.get("scene_id"), "component_name": item.get("component_name"),
            "source_file": item.get("source_file"), "expected_sha256": item.get("source_sha256"),
            "actual_sha256": actual_hash, "verified": verified, "status": status,
        }

    @staticmethod
    def _markdown(report):
        lines = [
            "# Component Compilation Summary", "", f"Status: {report['status']}",
            f"Compiled: {report['compiled_count']}/{len(report['components'])}",
            f"Failed: {report['failed_count']}",
            f"Timed out: {report['timed_out']}",
            f"Return code: {report['return_code']}", f"Workspace: `{report['workspace']}`", "",
            "## Components", "",
        ]
        for item in report["components"]:
            lines.extend([
                f"### {item['scene_id']}",
                f"- Component: {item['component_name']}",
                f"- Compile status: {item['compile_status']}",
                f"- Fallback: {item['fallback_component']}",
            ])
            if item.get("fallback_reason"):
                lines.append(f"- Fallback reason: {item['fallback_reason']}")
            lines.append("")
        if report["compiler_errors"]:
            lines.extend(["## Compiler Errors", ""])
            for error in report["compiler_errors"]:
                lines.append(f"- `{error['raw']}`")
        return "\n".join(lines)
