"""Fail-closed intake for files downloaded through the signed-in Tripo UI.

The Chrome extension may not emit a browser automation download event even
though Chrome successfully writes the file.  This tool treats the configured
download directory as the observable surface, validates the resulting asset,
deduplicates byte-identical retries, and moves one accepted file into the
project with a receipt.

This tool never calls a Tripo API and never clicks Generate or Retopology.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import struct
import sys
import time
from pathlib import Path
from typing import Any


SUPPORTED_SUFFIXES = {".glb", ".fbx", ".zip"}
PARTIAL_SUFFIXES = {".crdownload", ".part", ".tmp"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".building")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def snapshot(directory: Path, suffix: str | None = None) -> dict[str, Any]:
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES | PARTIAL_SUFFIXES:
            if suffix and path.suffix.lower() not in {suffix.lower(), ".crdownload"}:
                continue
            stat = path.stat()
            files.append(
                {
                    "path": str(path.resolve()),
                    "name": path.name,
                    "suffix": path.suffix.lower(),
                    "bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
    return {
        "status": "TRIPO_DOWNLOAD_BASELINE",
        "watch_directory": str(directory),
        "captured_at": time.time(),
        "files": files,
    }


def new_candidates(
    baseline: dict[str, Any], suffix: str | None = None, name_regex: str | None = None
) -> list[Path]:
    directory = Path(baseline["watch_directory"]).resolve()
    old = {row["path"]: (row["bytes"], row["mtime_ns"]) for row in baseline["files"]}
    result = []
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() in PARTIAL_SUFFIXES:
            continue
        if suffix and path.suffix.lower() != suffix.lower():
            continue
        if name_regex and re.fullmatch(name_regex, path.name) is None:
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        stat = path.stat()
        previous = old.get(str(path.resolve()))
        if previous is None or previous != (stat.st_size, stat.st_mtime_ns):
            result.append(path.resolve())
    return sorted(result, key=lambda path: (path.stat().st_mtime_ns, path.name))


def wait_until_stable(path: Path, stable_seconds: float, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    stable_since = None
    last_size = None
    while time.monotonic() < deadline:
        if path.exists() and path.is_file():
            size = path.stat().st_size
            if size > 0 and size == last_size:
                stable_since = stable_since or time.monotonic()
                if time.monotonic() - stable_since >= stable_seconds:
                    return
            else:
                last_size = size
                stable_since = None
        time.sleep(0.25)
    raise TimeoutError(f"Download did not become stable: {path}")


def inspect_glb(path: Path) -> dict[str, Any]:
    with path.open("rb") as source:
        header = source.read(20)
        if len(header) != 20 or header[:4] != b"glTF":
            raise ValueError("GLB magic/header is invalid")
        version, declared_length, json_length, json_type = struct.unpack_from("<4I", header, 4)
        if version != 2 or json_type != 0x4E4F534A:
            raise ValueError("Expected glTF 2.0 JSON chunk")
        payload = source.read(json_length)
        binary_length_raw = source.read(8)
        binary = b""
        if len(binary_length_raw) == 8:
            binary_length, binary_type = struct.unpack("<2I", binary_length_raw)
            if binary_type == 0x004E4942:
                binary = source.read(binary_length)
    if declared_length != path.stat().st_size:
        raise ValueError("GLB declared length does not match file size")
    document = json.loads(payload.rstrip(b" \x00"))
    accessors = document.get("accessors", [])
    primitive_vertices = 0
    triangles = 0
    primitive_count = 0
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            primitive_count += 1
            position = primitive.get("attributes", {}).get("POSITION")
            if position is None:
                raise ValueError("Mesh primitive has no POSITION accessor")
            vertices = int(accessors[position]["count"])
            indices = primitive.get("indices")
            index_count = int(accessors[indices]["count"]) if indices is not None else vertices
            mode = int(primitive.get("mode", 4))
            if mode != 4:
                raise ValueError(f"Unsupported primitive mode for rigging intake: {mode}")
            primitive_vertices += vertices
            triangles += index_count // 3
    image_rows = []
    if binary:
        from PIL import Image

        for index, image in enumerate(document.get("images", [])):
            buffer_view_index = image.get("bufferView")
            if buffer_view_index is None:
                continue
            buffer_view = document["bufferViews"][buffer_view_index]
            offset = int(buffer_view.get("byteOffset", 0))
            length = int(buffer_view["byteLength"])
            raw = binary[offset : offset + length]
            with Image.open(io.BytesIO(raw)) as decoded:
                image_rows.append(
                    {
                        "index": index,
                        "name": image.get("name"),
                        "mime_type": image.get("mimeType"),
                        "width": decoded.width,
                        "height": decoded.height,
                        "bytes": length,
                    }
                )
    return {
        "format": "GLB",
        "version": version,
        "generator": document.get("asset", {}).get("generator"),
        "meshes": len(document.get("meshes", [])),
        "primitives": primitive_count,
        "primitive_vertices": primitive_vertices,
        "triangles": triangles,
        "materials": len(document.get("materials", [])),
        "images": len(document.get("images", [])),
        "image_details": image_rows,
        "extensions_used": document.get("extensionsUsed", []),
    }


def validate(
    path: Path,
    maximum_triangles: int | None,
    minimum_texture_size: int | None = None,
) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported Tripo download suffix: {suffix}")
    if path.stat().st_size <= 0:
        raise ValueError("Downloaded file is empty")
    if suffix == ".glb":
        report = inspect_glb(path)
        if report["meshes"] < 1 or report["triangles"] < 1:
            raise ValueError("Downloaded GLB has no usable mesh triangles")
        if maximum_triangles is not None and report["triangles"] > maximum_triangles:
            raise ValueError(
                f"Downloaded GLB has {report['triangles']} triangles, above {maximum_triangles}"
            )
        if minimum_texture_size is not None:
            if not report["image_details"]:
                raise ValueError("Downloaded GLB has no embedded texture to validate")
            undersized = [
                row
                for row in report["image_details"]
                if min(row["width"], row["height"]) < minimum_texture_size
            ]
            if undersized:
                raise ValueError(
                    f"Downloaded GLB texture is below {minimum_texture_size}: {undersized}"
                )
        return report
    return {"format": suffix[1:].upper(), "bytes": path.stat().st_size}


def recycle(path: Path) -> None:
    """Send one verified absolute file to the Windows Recycle Bin."""
    if os.name != "nt":
        raise RuntimeError("Recycle Bin handling is implemented only for Windows")
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    resolved = path.resolve(strict=True)
    operation = SHFILEOPSTRUCTW()
    operation.wFunc = 3  # FO_DELETE
    operation.pFrom = str(resolved) + "\0\0"
    operation.fFlags = 0x0040 | 0x0010 | 0x0400  # recycle, no confirmation, no error UI
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(f"Recycle Bin operation failed for {resolved}: {result}")


def _copy_verified(source: Path, destination: Path, expected_hash: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".building")
    if temporary.exists():
        temporary.unlink()
    shutil.copy2(source, temporary)
    copied_hash = sha256(temporary)
    if copied_hash != expected_hash:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Copied download hash does not match source")
    os.replace(temporary, destination)


def intake(
    candidates: list[Path],
    destination: Path,
    receipt_path: Path,
    maximum_triangles: int | None,
    minimum_texture_size: int | None,
    recycle_duplicates: bool,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = [path.resolve(strict=True) for path in candidates]
    if not candidates:
        raise ValueError("No completed Tripo download candidates")
    hashes = {str(path): sha256(path) for path in candidates}
    unique_hashes = set(hashes.values())
    if len(unique_hashes) != 1:
        raise RuntimeError("Multiple non-identical Tripo download candidates; refusing to guess")
    selected = min(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))
    selected_hash = hashes[str(selected)]
    validation = validate(selected, maximum_triangles, minimum_texture_size)
    destination = destination.resolve()
    output_root = (PROJECT_ROOT / "outputs").resolve()
    if not destination.is_relative_to(output_root):
        raise ValueError(f"Destination must stay inside project outputs: {destination}")
    receipt_path = receipt_path.resolve()
    if not receipt_path.is_relative_to(output_root):
        raise ValueError(f"Receipt must stay inside project outputs: {receipt_path}")
    if destination.exists():
        if sha256(destination) != selected_hash:
            raise FileExistsError(f"Destination exists with different content: {destination}")
    else:
        _copy_verified(selected, destination, selected_hash)
    duplicate_rows = []
    for path in candidates:
        if path == selected:
            continue
        row = {"path": str(path), "bytes": path.stat().st_size, "sha256": hashes[str(path)]}
        if recycle_duplicates:
            recycle(path)
            row["recycled"] = True
        else:
            row["recycled"] = False
        duplicate_rows.append(row)
    # Once the project copy is proven identical, the selected download is also
    # a redundant copy in the browser download directory.
    selected_download_row = {
        "path": str(selected),
        "bytes": selected.stat().st_size,
        "sha256": selected_hash,
        "recycled": False,
    }
    if recycle_duplicates:
        recycle(selected)
        selected_download_row["recycled"] = True
    result = {
        "status": "PASS_TRIPO_UI_DOWNLOAD_INTAKE",
        "destination": str(destination),
        "bytes": destination.stat().st_size,
        "sha256": selected_hash,
        "validation": validation,
        "selected_download": selected_download_row,
        "duplicate_downloads": duplicate_rows,
        "browser_download_event_required": False,
        "tripo_api_used": False,
        "provenance": provenance or {},
    }
    _json_write(receipt_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    baseline_parser = subparsers.add_parser("baseline")
    baseline_parser.add_argument("--watch-dir", type=Path, required=True)
    baseline_parser.add_argument("--state", type=Path, required=True)
    baseline_parser.add_argument("--suffix", choices=sorted(SUPPORTED_SUFFIXES))

    intake_parser = subparsers.add_parser("intake")
    intake_parser.add_argument("--candidate", type=Path, action="append", default=[])
    intake_parser.add_argument("--baseline", type=Path)
    intake_parser.add_argument("--suffix", choices=sorted(SUPPORTED_SUFFIXES))
    intake_parser.add_argument("--name-regex")
    intake_parser.add_argument("--timeout", type=float, default=180.0)
    intake_parser.add_argument("--stable-seconds", type=float, default=2.0)
    intake_parser.add_argument("--destination", type=Path, required=True)
    intake_parser.add_argument("--receipt", type=Path, required=True)
    intake_parser.add_argument("--maximum-triangles", type=int)
    intake_parser.add_argument("--minimum-texture-size", type=int)
    intake_parser.add_argument("--recycle-duplicates", action="store_true")
    intake_parser.add_argument("--source-asset-id")
    intake_parser.add_argument("--conversion-id")
    intake_parser.add_argument("--ui-topology")
    intake_parser.add_argument("--ui-faces", type=int)
    intake_parser.add_argument("--ui-vertices", type=int)
    intake_parser.add_argument("--ui-credit-delta", type=int)
    arguments = parser.parse_args()

    if arguments.command == "baseline":
        state = snapshot(arguments.watch_dir, arguments.suffix)
        state["suffix"] = arguments.suffix
        _json_write(arguments.state.resolve(), state)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    candidates = list(arguments.candidate)
    if arguments.baseline:
        baseline = json.loads(arguments.baseline.read_text(encoding="utf-8-sig"))
        deadline = time.monotonic() + arguments.timeout
        while time.monotonic() < deadline:
            candidates = new_candidates(baseline, arguments.suffix, arguments.name_regex)
            if candidates:
                break
            time.sleep(0.5)
    if not candidates:
        raise RuntimeError("No matching download appeared before timeout")
    for path in candidates:
        wait_until_stable(path, arguments.stable_seconds, arguments.timeout)
    result = intake(
        candidates,
        arguments.destination,
        arguments.receipt,
        arguments.maximum_triangles,
        arguments.minimum_texture_size,
        arguments.recycle_duplicates,
        {
            key: value
            for key, value in {
                "source_asset_id": arguments.source_asset_id,
                "conversion_id": arguments.conversion_id,
                "ui_topology": arguments.ui_topology,
                "ui_faces": arguments.ui_faces,
                "ui_vertices": arguments.ui_vertices,
                "ui_credit_delta": arguments.ui_credit_delta,
            }.items()
            if value is not None
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "FAIL_TRIPO_UI_DOWNLOAD_INTAKE", "error": str(error)}), file=sys.stderr)
        raise
