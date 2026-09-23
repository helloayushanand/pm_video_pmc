"""Static validation for untrusted generated TypeScript."""
from __future__ import annotations
import re
from app.schemas.generated_component import SceneGenerationInput, SourceValidationIssue, SourceValidationResult

ALLOWED_DIRECT_IMPORTS = {"react", "remotion"}
ALLOWED_IMPORT_PREFIXES = {"./dynamic-sdk", "../dynamic-sdk", "../../dynamic-sdk", "@/dynamic-sdk"}
FORBIDDEN_PATTERNS = {
    "process.env": "environment_access", "require(": "commonjs_require",
    "eval(": "eval", "new Function": "function_constructor",
    "child_process": "child_process", "node:fs": "filesystem",
    "node:path": "filesystem_path", "node:net": "network",
    "node:http": "network", "node:https": "network",
    "XMLHttpRequest": "network", "WebSocket(": "network",
    "fetch(": "network", "import(": "dynamic_import",
    "document.cookie": "browser_secret_access", "localStorage": "browser_storage",
    "sessionStorage": "browser_storage",
}
IMPORT_PATTERN = re.compile(r'(?:import\s+(?:type\s+)?[^;]*?\s+from\s+|import\s*)["\']([^"\']+)["\']')
ARTIFACT_PATTERN = re.compile(r'artifactId\s*:\s*["\']([^"\']+)["\']')

def validate_generated_source(source: str, scene_input: SceneGenerationInput) -> SourceValidationResult:
    issues = []
    imports = IMPORT_PATTERN.findall(source)
    for pattern, code in FORBIDDEN_PATTERNS.items():
        if pattern in source:
            issues.append(SourceValidationIssue(code=code, message=f"Forbidden pattern: {pattern}"))
    for module in imports:
        direct = module in ALLOWED_DIRECT_IMPORTS
        prefix = any(module == p or module.startswith(p + "/") for p in ALLOWED_IMPORT_PREFIXES)
        if not direct and not prefix:
            issues.append(SourceValidationIssue(code="unapproved_import", message=f"Unapproved import: {module}"))
    for fragment, code in {
        "GeneratedSceneProps": "missing_generated_scene_props",
        "export": "missing_export",
        scene_input.component_name: "component_name_mismatch",
    }.items():
        if fragment not in source:
            issues.append(SourceValidationIssue(code=code, message=f"Missing fragment: {fragment}"))
    artifacts = ARTIFACT_PATTERN.findall(source)
    approved = {a.artifact_id for a in scene_input.available_artifacts if a.approved}
    for artifact_id in artifacts:
        if artifact_id not in approved:
            issues.append(SourceValidationIssue(code="unapproved_artifact", message=f"Unapproved artifact: {artifact_id}"))
    return SourceValidationResult(valid=not issues, issues=issues, discovered_imports=imports, discovered_artifacts=artifacts)
