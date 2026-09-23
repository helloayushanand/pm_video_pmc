from app.services.compiler_repair_service import CompilerRepairService

def test_sdk_contract_contains_context_fields():
    contract = CompilerRepairService._load_sdk_contract()
    assert "durationInFrames" in contract["SceneContext"]
    assert "accent" in contract["DynamicTheme"]

def test_compiler_text_combines_streams():
    value = CompilerRepairService._compiler_text({"compiler_stdout": "one", "compiler_stderr": "two"})
    assert "one" in value and "two" in value
