"""Tests for Phase 5A compilation helpers."""
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