"""Compile approved generated components in an isolated workspace."""
from __future__ import annotations
import hashlib
import json
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
    """Verify approvals, create a bounded workspace, and run TypeScript."""

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
            destination = generated_dir / source.name
            shutil.copy2(source, destination)
            verification.append(self._verification(item, True, "verified", actual_hash))
            copied.append({**item, "workspace_source": str(destination)})

        failed_verification = [item for item in verification if not item["verified"]]
        if failed_verification:
            report = {
                "status": "approval_verification_failed",
                "workspace": str(workspace),
                "verification": verification,
                "compiler": None,
                "components": copied,
            }
            save_json(report, output_path / "compilation_report.json")
            raise ComponentCompilationError("One or more source approvals are stale or invalid.")

        registry_path = self._write_registry(source_dir, copied)
        tsconfig_path = self._write_tsconfig(workspace)
        package_path = self._write_package_json(workspace)
        command = [str(node_modules / ".bin" / "tsc.cmd"), "--project", str(tsconfig_path), "--pretty", "false"]
        logger.info("Running isolated TypeScript compilation for %s component(s).", len(copied))
        try:
            completed = subprocess.run(
                command,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            timed_out = False
        except subprocess.TimeoutExpired as error:
            completed = None
            timed_out = True
            stdout = error.stdout or ""
            stderr = error.stderr or ""

        if completed is not None:
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            return_code = completed.returncode
        else:
            return_code = None

        errors = self._parse_compiler_output(stdout + "\n" + stderr)
        compiled = not timed_out and return_code == 0
        component_results = []
        for item in copied:
            component_results.append({
                "scene_id": item["scene_id"],
                "component_name": item["component_name"],
                "source_file": item["source_file"],
                "source_sha256": item["source_sha256"],
                "workspace_source": item["workspace_source"],
                "fallback_component": item["fallback_component"],
                "compile_status": "compiled" if compiled else "compiler_error",
                "eligible_for_phase_5b_repair": not compiled,
            })

        report = {
            "status": "compiled" if compiled else ("timeout" if timed_out else "compiler_error"),
            "compiled": compiled,
            "timed_out": timed_out,
            "return_code": return_code,
            "command": command,
            "workspace": str(workspace),
            "registry": str(registry_path),
            "tsconfig": str(tsconfig_path),
            "package_json": str(package_path),
            "verification": verification,
            "compiler_stdout": stdout,
            "compiler_stderr": stderr,
            "compiler_errors": errors,
            "components": component_results,
        }
        save_json(report, output_path / "compilation_report.json")
        save_json(errors, output_path / "compiler_errors.json")
        if compiled:
            save_json({
                "schema_version": "1.0",
                "compiled_components": component_results,
                "compiled_count": len(component_results),
                "workspace_registry": str(registry_path),
            }, output_path / "approved_compiled_components.json")
            shutil.copy2(registry_path, output_path / "compiled_registry.ts")
        (output_path / "compilation_summary.md").write_text(self._markdown(report), encoding="utf-8")
        return report

    @staticmethod
    def _write_registry(source_dir, components):
        lines = ['import type React from "react";', 'import type {GeneratedSceneProps} from "@/dynamic-sdk";', '']
        entries = []
        for index, item in enumerate(components, start=1):
            alias = f"GeneratedComponent{index}"
            stem = Path(item["workspace_source"]).stem
            lines.append(f'import {{{item["component_name"]} as {alias}}} from "./generated/{stem}";')
            entries.append(f'  "{item["scene_id"]}": {alias},')
        lines.extend(['', 'export const compiledSceneRegistry: Record<string, React.FC<GeneratedSceneProps>> = {', *entries, '};', ''])
        path = source_dir / "registry.ts"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    @staticmethod
    def _write_tsconfig(workspace):
        payload = {
            "compilerOptions": {
                "target": "ES2020", "module": "ESNext", "moduleResolution": "Node",
                "jsx": "react-jsx", "strict": True, "noEmit": True,
                "esModuleInterop": True, "allowSyntheticDefaultImports": True,
                "skipLibCheck": True, "baseUrl": "./src",
                "paths": {"@/*": ["*"]}, "types": ["node"],
                "lib": ["ES2020", "DOM", "DOM.Iterable"]
            },
            "include": ["src/**/*.ts", "src/**/*.tsx"],
            "exclude": ["node_modules"]
        }
        path = workspace / "tsconfig.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

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
            f"Compiled: {report['compiled']}", f"Timed out: {report['timed_out']}",
            f"Return code: {report['return_code']}", f"Workspace: `{report['workspace']}`", "",
            "## Components", "",
        ]
        for item in report["components"]:
            lines.extend([f"### {item['scene_id']}", f"- Component: {item['component_name']}", f"- Compile status: {item['compile_status']}", f"- Fallback: {item['fallback_component']}", ""])
        if report["compiler_errors"]:
            lines.extend(["## Compiler Errors", ""])
            for error in report["compiler_errors"]:
                lines.append(f"- `{error['raw']}`")
        return "\n".join(lines)
