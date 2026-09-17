"""JSON reading, writing, and validation helpers."""

import json
from pathlib import Path
from typing import Any


def load_json(file_path: str | Path) -> Any:
    """Load and return JSON content from a local file."""

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Expected a JSON file but received: {path}")

    try:
        with path.open("r", encoding="utf-8-sig") as file_handle:
            return json.load(file_handle)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON in {path}: line {error.lineno}, "
            f"column {error.colno}: {error.msg}"
        ) from error


def save_json(
    data: Any,
    file_path: str | Path,
    indent: int = 2,
    overwrite: bool = True,
) -> Path:
    """Save data as formatted UTF-8 JSON."""

    path = Path(file_path)

    if path.exists() and not overwrite:
        raise FileExistsError(f"JSON file already exists: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_suffix(f"{path.suffix}.tmp")

    with temporary_path.open("w", encoding="utf-8") as file_handle:
        json.dump(
            data,
            file_handle,
            indent=indent,
            ensure_ascii=False,
            default=str,
        )
        file_handle.write("\n")

    temporary_path.replace(path)

    return path.resolve()


def is_valid_json(file_path: str | Path) -> bool:
    """Return True when a file contains valid JSON."""

    try:
        load_json(file_path)
        return True
    except (FileNotFoundError, ValueError):
        return False


def merge_json(
    base: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Recursively merge one JSON-compatible dictionary into another."""

    result = base.copy()

    for key, value in updates.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = merge_json(result[key], value)
        else:
            result[key] = value

    return result
