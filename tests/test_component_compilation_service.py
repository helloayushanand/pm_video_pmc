"""Tests for Phase 5A compilation helpers."""
import json
import subprocess
from pathlib import Path

from app.services.component_compilation_service import ComponentCompilationService

def test_parse_compiler_output():
    value = "src/test.tsx(1,2): error TS2304: Cannot find name 'x'."
    errors = ComponentCompilationService._parse_compiler_output(value)
    assert len(errors) == 1

def test_sha256_file(tmp_path):
    path = tmp_path / "source.tsx"
    path.write_text("hello", encoding="utf-8")
    first = ComponentCompilationService._sha256_file(path)
    second = ComponentCompilationService._sha256_file(path)
    assert first == second
    assert len(first) == 64

def test_hash_normalises_line_endings(tmp_path):
    windows_path = (
        tmp_path / "windows.tsx"
    )

    unix_path = (
        tmp_path / "unix.tsx"
    )

    windows_path.write_bytes(
        b"line one\r\nline two\r\n"
    )

    unix_path.write_bytes(
        b"line one\nline two\n"
    )

    windows_hash = (
        ComponentCompilationService
        ._sha256_file(windows_path)
    )

    unix_hash = (
        ComponentCompilationService
        ._sha256_file(unix_path)
    )

    assert windows_hash == unix_hash

def test_hash_ignores_utf8_bom(tmp_path):
    bom_path = (
        tmp_path / "bom.tsx"
    )

    plain_path = (
        tmp_path / "plain.tsx"
    )

    bom_path.write_bytes(
        b"\xef\xbb\xbfconst value = 1;\n"
    )

    plain_path.write_bytes(
        b"const value = 1;\n"
    )

    bom_hash = (
        ComponentCompilationService
        ._sha256_file(bom_path)
    )

    plain_hash = (
        ComponentCompilationService
        ._sha256_file(plain_path)
    )

    assert bom_hash == plain_hash


def test_components_are_type_checked_independently_and_successes_survive(
    monkeypatch, tmp_path
):
    renderer = tmp_path / "renderer"
    sdk = renderer / "src" / "dynamic-sdk"
    (renderer / "node_modules" / ".bin").mkdir(parents=True)
    sdk.mkdir(parents=True)
    (sdk / "index.ts").write_text("export type SdkType = string;\n")
    monkeypatch.setattr(
        "app.services.component_compilation_service.RENDERER_DIR",
        renderer,
    )

    run_dir = tmp_path / "run"
    generated = run_dir / "05d_generated_components"
    generated.mkdir(parents=True)
    source_paths = []
    approved = []
    for scene_id in ("scene_ok", "scene_error"):
        source = generated / f"{scene_id}.tsx"
        source.write_text(
            f"export const {scene_id}: string = 'ok';\n",
            encoding="utf-8",
        )
        source_paths.append(source)
        approved.append(
            {
                "scene_id": scene_id,
                "component_name": scene_id,
                "source_file": str(source),
                "source_sha256": ComponentCompilationService._sha256_file(
                    source
                ),
                "fallback_component": "GenericScene",
            }
        )
    (generated / "approved_components.json").write_text(
        json.dumps({"approved_components": approved}),
        encoding="utf-8",
    )

    includes_by_call = []

    def fake_run(command, cwd, capture_output, text, timeout, check):
        tsconfig = Path(command[command.index("--project") + 1])
        includes_by_call.append(
            json.loads(tsconfig.read_text(encoding="utf-8"))["include"]
        )
        scene_fails = "scene_error" in str(includes_by_call[-1])
        return subprocess.CompletedProcess(
            command,
            2 if scene_fails else 0,
            stdout=(
                "src/generated/scene_error/scene_error.tsx(1,1): "
                "error TS2322: Type mismatch.\n"
                if scene_fails
                else ""
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "app.services.component_compilation_service.subprocess.run",
        fake_run,
    )

    report = ComponentCompilationService().compile_approved_components(
        run_dir,
        run_dir / "05e_component_compilation",
    )

    assert report["status"] == "partially_compiled"
    assert report["compiled_count"] == 1
    assert report["failed_count"] == 1
    assert [len(configured) for configured in includes_by_call] == [4, 4]
    assert "scene_ok" in str(includes_by_call[0])
    assert "scene_error" not in str(includes_by_call[0])
    assert "scene_error" in str(includes_by_call[1])
    assert "scene_ok" not in str(includes_by_call[1])
    manifest = json.loads(
        (
            run_dir
            / "05e_component_compilation"
            / "approved_compiled_components.json"
        ).read_text(encoding="utf-8")
    )
    assert [item["scene_id"] for item in manifest["compiled_components"]] == [
        "scene_ok"
    ]
    assert manifest["failed_components"][0]["fallback_reason"] == (
        "typescript_compile_failed"
    )


def test_registry_imports_default_export_when_generated_source_uses_it(
    tmp_path,
):
    source_dir = tmp_path / "src"
    source_file = (
        source_dir
        / "generated"
        / "scene-default"
        / "component.tsx"
    )
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        "const Scene: React.FC<GeneratedSceneProps> = () => null;\n"
        "export default Scene;\n",
        encoding="utf-8",
    )

    export_kind = ComponentCompilationService._component_export_kind(
        source_file.read_text(encoding="utf-8"),
        "Scene",
    )
    registry = ComponentCompilationService._write_registry(
        source_dir,
        [
            {
                "scene_id": "scene-default",
                "component_name": "Scene",
                "workspace_source": str(source_file),
                "export_kind": export_kind,
            }
        ],
    )

    registry_source = registry.read_text(encoding="utf-8")
    assert export_kind == "default"
    assert 'import GeneratedComponent1 from "./generated/scene-default/component";' in registry_source
    assert "import {Scene as GeneratedComponent1}" not in registry_source


def test_unverified_component_does_not_block_a_verified_component(
    monkeypatch, tmp_path
):
    renderer = tmp_path / "renderer"
    sdk = renderer / "src" / "dynamic-sdk"
    (renderer / "node_modules" / ".bin").mkdir(parents=True)
    sdk.mkdir(parents=True)
    (sdk / "index.ts").write_text("export type SdkType = string;\n")
    monkeypatch.setattr(
        "app.services.component_compilation_service.RENDERER_DIR",
        renderer,
    )

    run_dir = tmp_path / "run"
    generated = run_dir / "05d_generated_components"
    generated.mkdir(parents=True)
    valid_source = generated / "valid.tsx"
    valid_source.write_text("export const Valid = 1;\n", encoding="utf-8")
    approved = [
        {
            "scene_id": "scene_valid",
            "component_name": "Valid",
            "source_file": str(valid_source),
            "source_sha256": ComponentCompilationService._sha256_file(
                valid_source
            ),
            "fallback_component": "GenericScene",
        },
        {
            "scene_id": "scene_missing",
            "component_name": "Missing",
            "source_file": str(generated / "missing.tsx"),
            "source_sha256": "0" * 64,
            "fallback_component": "GenericScene",
        },
    ]
    (generated / "approved_components.json").write_text(
        json.dumps({"approved_components": approved}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.services.component_compilation_service.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout="", stderr=""
        ),
    )

    report = ComponentCompilationService().compile_approved_components(
        run_dir,
        run_dir / "05e_component_compilation",
    )

    assert report["status"] == "partially_compiled"
    assert report["components"][0]["compile_status"] == "source_missing"
    assert report["components"][1]["compile_status"] == "compiled"
    assert report["compiled_count"] == 1