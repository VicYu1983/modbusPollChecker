from __future__ import annotations

from pathlib import Path
import re
from threading import Lock

from .schemas import SiteConfig


class SiteStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._lock = Lock()
        self._current_site_name: str | None = None

    def list_sites(self) -> list[str]:
        with self._lock:
            return sorted(
                path.stem
                for path in self.directory.glob("*.json")
                if self._is_site_file(path)
            ) if self.directory.exists() else []

    @staticmethod
    def _is_site_file(path: Path) -> bool:
        try:
            SiteConfig.model_validate_json(path.read_text(encoding="utf-8"))
            return True
        except (OSError, ValueError):
            return False

    @staticmethod
    def _file_stem(site_name: str) -> str:
        safe_name = re.sub(r'[<>:"/\\|?*]+', "_", site_name.strip()).rstrip(". ")
        return safe_name or "未命名案場"

    def load(self, site_name: str | None = None) -> SiteConfig:
        with self._lock:
            selected_name = site_name or self._current_site_name
            if selected_name:
                path = self.directory / f"{self._file_stem(selected_name)}.json"
                if path.exists():
                    config = SiteConfig.model_validate_json(path.read_text(encoding="utf-8"))
                    self._current_site_name = config.site_name
                    return config
            sites = [
                path for path in sorted(self.directory.glob("*.json"))
                if self._is_site_file(path)
            ] if self.directory.exists() else []
            if sites:
                config = SiteConfig.model_validate_json(sites[0].read_text(encoding="utf-8"))
                self._current_site_name = config.site_name
                return config
            return SiteConfig(site_name="未命名案場")

    def save(self, config: SiteConfig) -> SiteConfig:
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / f"{self._file_stem(config.site_name)}.json"
            temporary_path = path.with_suffix(".tmp")
            temporary_path.write_text(
                config.model_dump_json(indent=2), encoding="utf-8"
            )
            temporary_path.replace(path)
            self._current_site_name = config.site_name
            return config

    def delete(self, site_name: str) -> bool:
        with self._lock:
            path = self.directory / f"{self._file_stem(site_name)}.json"
            if not path.exists() or not self._is_site_file(path):
                return False
            path.unlink()
            if self._current_site_name == site_name:
                self._current_site_name = None
            return True
