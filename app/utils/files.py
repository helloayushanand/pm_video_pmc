"""File-system helper functions."""

import hashlib
import re
import shutil
from pathlib import Path


def ensure_directory(path: str | Path) -> Path:
    """Create a directory if required and return its resolved path."""

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve()


def calculate_sha256(
    file_path: str | Path,
    chunk_size: int = 1024 * 1024,
) -> str:
    """Calculate the SHA-256 hash of a file."""

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ValueError(f"Expected a file but received: {path}")

    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        while chunk := file_handle.read(chunk_size):
            digest.update(chunk)

    return digest.hexdigest()


def copy_file(
    source: str | Path,
    destination: str | Path,
    overwrite: bool = False,
) -> Path:
    """Copy a file to a new location."""

    source_path = Path(source)
    destination_path = Path(destination)

    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    if not source_path.is_file():
        raise ValueError(f"Source is not a file: {source_path}")

    if destination_path.exists() and not overwrite:
        raise FileExistsError(
            f"Destination already exists: {destination_path}"
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)

    return destination_path.resolve()


def safe_filename(filename: str, replacement: str = "_") -> str:
    """Convert an arbitrary filename into a safe local filename."""

    path = Path(filename)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", replacement, path.stem)
    safe_stem = safe_stem.strip("._-") or "file"

    suffix = re.sub(r"[^A-Za-z0-9.]+", "", path.suffix.lower())

    return f"{safe_stem}{suffix}"


def list_files(
    directory: str | Path,
    pattern: str = "*",
) :
    """Return sorted files matching a pattern in a directory."""

    directory_path = Path(directory)

    if not directory_path.exists():
        return []

    return sorted(
        path.resolve()
        for path in directory_path.glob(pattern)
        if path.is_file()
    )


def get_relative_path(
    file_path: str | Path,
    base_directory: str | Path,
) -> str:
    """Return a portable relative path using forward slashes."""

    path = Path(file_path).resolve()
    base = Path(base_directory).resolve()

    return path.relative_to(base).as_posix()

