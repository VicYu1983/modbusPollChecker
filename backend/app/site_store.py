from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from .schemas import SiteConfig


class SiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def load(self) -> SiteConfig:
        with self._lock:
            if not self.path.exists():
                return SiteConfig(site_name="未命名案場")
            return SiteConfig.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, config: SiteConfig) -> SiteConfig:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(".tmp")
            temporary_path.write_text(
                config.model_dump_json(indent=2), encoding="utf-8"
            )
            temporary_path.replace(self.path)
            return config
