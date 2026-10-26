import json
from pathlib import Path

from app.schemas.generated_component import (
    GeneratedComponentOutput,
    SceneGenerationInput,
)
from app.services.compiler_repair_service import CompilerRepairService

def test_sdk_contract_contains_context_fields():
    contract = CompilerRepairService._load_sdk_contract()
    assert "durationInFrames" in contract["SceneContext"]
    assert "accent" in contract["DynamicTheme"]

def test_compiler_text_combines_streams():
    value = CompilerRepairService._compiler_text({"compiler_stdout": "one", "compiler_stderr": "two"})
    assert "one" in value and "two" in value


def test_automatic_repair_only_retries_failed_scenes_once(
    monkeypatch,
    tmp_path,
):
    run_dir = tmp_path / "run"
    compilation_dir = run_dir / "05e_component_compilation"
    generation_dir = run_dir / "05d_generated_components"
    compilation_dir.mkdir(parents=True)
    generation_dir.mkdir(parents=True)
    output_dir = compilation_dir

    scene_input = SceneGenerationInput(
        run_id="run",
        scene_id="scene_bad",
        scene_type="metrics",
        component_name="GeneratedScene",
        fallback_component="GenericScene",
        duration_hint_seconds=8,
        creative_direction={},
        scene_architecture={},
        approved_facts=[],
        available_artifacts=[],
        allowed_primitives=["SceneFrame"],
    )
    original_component = GeneratedComponentOutput(
        scene_id="scene_bad",
        component_name="GeneratedScene",
        source_code=(
            'import React from "react";\n'
            'import type {GeneratedSceneProps} from "@/dynamic-sdk";\n'
            "export const GeneratedScene: React.FC<GeneratedSceneProps> = "
            "() => <div>original scene</div>;\n"
        ),
        used_primitives=["SceneFrame"],
        used_artifacts=[],
        generation_rationale="Original custom layout",
        expected_peak_frame_percentage=0.8,
        fallback_component="GenericScene",
    )
    (generation_dir / "generation_plan.json").write_text(
        json.dumps({"scenes": [scene_input.model_dump(mode="json")]}),
        encoding="utf-8",
    )
    (generation_dir / "generation_results.json").write_text(
        json.dumps(
            [
                {
                    "scene_id": "scene_bad",
                    "generated_component": original_component.model_dump(
                        mode="json"
                    ),
                }
            ]
        ),
        encoding="utf-8",
    )
    (compilation_dir / "compilation_report.json").write_text(
        json.dumps(
            {
                "status": "partially_compiled",
                "compiled": False,
                "compiled_count": 1,
                "failed_count": 1,
                "compiler_runs": [
                    {
                        "scene_id": "scene_bad",
                        "stdout": "error TS2304: missing import",
                        "stderr": "",
                    }
                ],
                "compiler_errors": [
                    {
                        "scene_id": "scene_bad",
                        "raw": "error TS2304: missing import",
                    }
                ],
                "components": [
                    {
                        "scene_id": "scene_good",
                        "compile_status": "compiled",
                    },
                    {
                        "scene_id": "scene_bad",
                        "component_name": "GeneratedScene",
                        "source_file": "original.tsx",
                        "source_sha256": "source-hash",
                        "fallback_component": "GenericScene",
                        "compile_status": "compiler_error",
                        "compile_errors": [
                            {"raw": "error TS2304: missing import"}
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (compilation_dir / "approved_compiled_components.json").write_text(
        json.dumps(
            {
                "compiled_components": [
                    {
                        "scene_id": "scene_good",
                        "compile_status": "compiled",
                    }
                ],
                "compiled_count": 1,
            }
        ),
        encoding="utf-8",
    )

    repaired_source = (
        'import React from "react";\n'
        'import type {GeneratedSceneProps} from "@/dynamic-sdk";\n'
        "export const GeneratedScene: React.FC<GeneratedSceneProps> = "
        "() => <div>repaired scene</div>;\n"
    )

    class FakeAgent:
        calls = 0

        def repair(self, scene, component, compiler_output, sdk_contract):
            self.calls += 1
            assert scene.scene_id == "scene_bad"
            assert "error TS2304" in compiler_output
            assert "source_derived_public_api" in sdk_contract
            repaired = component.model_copy(
                update={"source_code": repaired_source}
            )
            return repaired, {"operation": "compiler_repair"}

    service = CompilerRepairService.__new__(CompilerRepairService)
    service.agent = FakeAgent()
    compile_calls = []

    def fake_compile(run_path, scene, component, candidate, timeout):
        compile_calls.append((scene.scene_id, Path(candidate)))
        return {
            "compiled": True,
            "status": "compiled",
            "compiler_output": "",
            "return_code": 0,
        }

    monkeypatch.setattr(service, "_compile_candidate", fake_compile)
    monkeypatch.setattr(
        "app.agents.component_generation.agent.ComponentGenerationAgent."
        "_read_sdk_public_api",
        lambda: "current SDK signatures",
    )

    summary = service.repair_failed_components_once(
        run_dir,
        output_dir,
    )

    assert service.agent.calls == 1
    assert compile_calls[0][0] == "scene_bad"
    assert summary["attempted_repair_count"] == 1
    assert summary["repaired_compiled_count"] == 1
    assert summary["compiled_count"] == 2
    assert summary["failed_count"] == 0
    manifest = json.loads(
        (compilation_dir / "approved_compiled_components.json").read_text(
            encoding="utf-8"
        )
    )
    assert {item["scene_id"] for item in manifest["compiled_components"]} == {
        "scene_good",
        "scene_bad",
    }
    report = json.loads(
        (compilation_dir / "compilation_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["compiler_errors"] == []
    assert len(report["initial_compiler_errors"]) == 1
