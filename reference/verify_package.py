"""Verify packaged bytes against local lineage, not cryptographic authenticity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


def verify(root: Path) -> dict:
    manifest = json.loads((root / "LINEAGE.json").read_text(encoding="utf-8"))
    errors = []
    if manifest.get("schema_version") != "vrs-reference-component-lineage-v1":
        errors.append("wrong_manifest_schema")
    for name, entry in manifest["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            errors.append(f"unsafe_path:{name}")
            continue
        path = root / name
        if path.is_symlink() or not path.is_file():
            errors.append(f"missing_or_symlink:{name}")
            continue
        if not path.resolve().is_relative_to(root.resolve()):
            errors.append(f"outside_package:{name}")
            continue
        data = path.read_bytes()
        if (
            len(data) != entry["bytes"]
            or hashlib.sha256(data).hexdigest() != entry["sha256"]
        ):
            errors.append(f"changed:{name}")
        data.decode("utf-8")
        if data.startswith(b"\xef\xbb\xbf"):
            errors.append(f"bom:{name}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "checked_files": len(manifest["files"]),
        "upstream_commit": manifest["upstream_commit"],
        "errors": errors,
        "scope": "local byte consistency, not authenticated provenance or empirical reproduction",
        "empirical_reproduction_complete": False,
    }


if __name__ == "__main__":
    result = verify(Path(__file__).resolve().parent)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
