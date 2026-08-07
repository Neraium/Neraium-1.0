from __future__ import annotations

import json
from pathlib import Path

from .contracts import EvidencePackage


class JsonlEvidencePackageStore:
    """Small append-only store suitable for prototypes and replay artifacts."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, package: EvidencePackage) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(package.model_dump_json() + "\n")

    def get(self, package_id: str) -> EvidencePackage | None:
        if not self.path.exists():
            return None
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                package = EvidencePackage.model_validate_json(line)
                if package.id == package_id:
                    return package
        return None

    def list(self, *, limit: int = 100) -> list[EvidencePackage]:
        if not self.path.exists():
            return []
        packages: list[EvidencePackage] = []
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    packages.append(EvidencePackage.model_validate_json(line))
        return packages[-max(0, limit) :]

