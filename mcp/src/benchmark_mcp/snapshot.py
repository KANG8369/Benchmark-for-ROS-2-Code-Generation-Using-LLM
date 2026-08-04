"""Canonical package-snapshot identity helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from benchmark_mcp.schemas import PackageFile


def snapshot_sha256(package_name: str, files: Sequence[PackageFile]) -> str:
    """Hash a complete package snapshot independently of input file ordering."""

    canonical = {
        "package_name": package_name,
        "files": [
            {
                "path": package_file.path,
                "content": package_file.content,
                "executable": package_file.executable,
            }
            for package_file in sorted(files, key=lambda item: item.path)
        ],
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
