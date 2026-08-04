"""Immutable generated-package artifacts shared with the evaluator profile."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from benchmark_mcp.schemas import BuildResult, PackageFile
from benchmark_mcp.snapshot import snapshot_sha256

RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
FILE_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class ArtifactStore:
    """Persist valid package snapshots and build observations by opaque run ID.

    The Coder profile can write a record through ``BuildService`` but has no MCP
    resource exposing it. The Evaluator profile opens the same store read-only
    through narrowly scoped resource templates.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def record(
        self,
        *,
        run_id: str,
        package_name: str,
        files: list[PackageFile],
        build_result: BuildResult,
    ) -> None:
        self._validate_run_id(run_id)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        final_directory = self.root / run_id
        if final_directory.exists():
            raise FileExistsError(f"artifact run already exists: {run_id}")

        snapshot_hash = snapshot_sha256(package_name, files)
        manifest_files = []
        contents: dict[str, dict[str, Any]] = {}
        for package_file in sorted(files, key=lambda item: item.path):
            file_id = hashlib.sha256(package_file.path.encode("utf-8")).hexdigest()
            manifest_files.append(
                {
                    "file_id": file_id,
                    "path": package_file.path,
                    "size_bytes": len(package_file.content.encode("utf-8")),
                    "executable": package_file.executable,
                }
            )
            contents[file_id] = {
                "path": package_file.path,
                "content": package_file.content,
                "executable": package_file.executable,
            }

        payload = {
            "artifact_version": 1,
            "run_id": run_id,
            "package_name": package_name,
            "snapshot_sha256": snapshot_hash,
            "files": manifest_files,
            "build": build_result.model_dump(mode="json"),
            "contents": contents,
        }

        temporary_directory = Path(tempfile.mkdtemp(prefix=".record-", dir=self.root)).resolve(
            strict=True
        )
        try:
            if temporary_directory.parent != self.root:
                raise RuntimeError("artifact temporary directory escaped artifact root")
            target = temporary_directory / "artifact.json"
            target.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            target.chmod(0o600)
            os.replace(temporary_directory, final_directory)
        except Exception:
            shutil.rmtree(temporary_directory, ignore_errors=True)
            raise

    def package_resource(self, run_id: str) -> dict[str, Any]:
        payload = self._load(run_id)
        return {
            "artifact_version": payload["artifact_version"],
            "run_id": payload["run_id"],
            "package_name": payload["package_name"],
            "snapshot_sha256": payload["snapshot_sha256"],
            "files": copy.deepcopy(payload["files"]),
            "build": copy.deepcopy(payload["build"]),
        }

    def file_resource(self, run_id: str, file_id: str) -> dict[str, Any]:
        self._validate_file_id(file_id)
        payload = self._load(run_id)
        try:
            file_data = payload["contents"][file_id]
        except KeyError as exc:
            raise ValueError(f"Unknown artifact file identifier for run {run_id}") from exc
        return {
            "run_id": payload["run_id"],
            "file_id": file_id,
            "path": file_data["path"],
            "content": file_data["content"],
            "executable": file_data["executable"],
        }

    def _load(self, run_id: str) -> dict[str, Any]:
        self._validate_run_id(run_id)
        record_path = self.root / run_id / "artifact.json"
        try:
            resolved = record_path.resolve(strict=True)
        except OSError as exc:
            raise ValueError(f"Unknown artifact run: {run_id}") from exc
        expected_parent = (self.root / run_id).resolve(strict=True)
        if (
            record_path.is_symlink()
            or resolved.parent != expected_parent
            or expected_parent.parent != self.root
            or not resolved.is_file()
        ):
            raise ValueError(f"Invalid artifact record for run: {run_id}")
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unreadable artifact record for run: {run_id}") from exc
        self._validate_payload(payload, run_id)
        return payload

    @staticmethod
    def _validate_payload(payload: object, run_id: str) -> None:
        if not isinstance(payload, dict) or payload.get("run_id") != run_id:
            raise ValueError(f"Invalid artifact record for run: {run_id}")
        if not isinstance(payload.get("contents"), dict):
            raise ValueError(f"Invalid artifact contents for run: {run_id}")
        if not isinstance(payload.get("files"), list):
            raise ValueError(f"Invalid artifact manifest for run: {run_id}")
        for entry in payload["files"]:
            if not isinstance(entry, dict):
                raise ValueError(f"Invalid artifact manifest for run: {run_id}")
            path = entry.get("path")
            file_id = entry.get("file_id")
            if not isinstance(path, str) or not isinstance(file_id, str):
                raise ValueError(f"Invalid artifact manifest for run: {run_id}")
            ArtifactStore._validate_file_id(file_id)
            pure_path = PurePosixPath(path)
            if pure_path.is_absolute() or any(part in ("", ".", "..") for part in pure_path.parts):
                raise ValueError(f"Invalid artifact manifest for run: {run_id}")

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError("run_id must be an opaque 32-character hexadecimal identifier")

    @staticmethod
    def _validate_file_id(file_id: str) -> None:
        if not FILE_ID_PATTERN.fullmatch(file_id):
            raise ValueError("file_id must be an opaque SHA-256 hexadecimal identifier")
