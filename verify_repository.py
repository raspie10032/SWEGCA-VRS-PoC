"""Verify current paper bytes and preserved component lineage without models/network."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent


def verify():
    manifest = json.loads((ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
    errors = []
    for name, entry in manifest["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            errors.append(f"unsafe_path:{name}")
            continue
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            errors.append(f"missing_or_unsafe:{name}")
            continue
        raw = path.read_bytes()
        if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            errors.append(f"changed:{name}")
    checked = subprocess.run([sys.executable, "-I", str(ROOT / "reference/verify_package.py")], cwd=ROOT, capture_output=True, text=True, check=False)
    if checked.returncode:
        errors.append("reference_package_failed")
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "snapshot_files": len(manifest["files"]), "reference": json.loads(checked.stdout), "scope": "local byte consistency; not provenance authentication or empirical replay"}


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(result["status"] != "PASS")
