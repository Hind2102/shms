"""Runtime configuration, read from environment variables (or a .env file).

All variables are prefixed with ``SHMS_``. See ``.env.example`` for the full list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, existing environment wins."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env(name: str, default: str) -> str:
    return os.environ.get(f"SHMS_{name}", default)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", f"sqlite:///{PROJECT_DIR / 'shms.db'}"))
    upload_dir: Path = field(default_factory=lambda: Path(_env("UPLOAD_DIR", str(PROJECT_DIR / "uploads"))))
    # Which AI detector the app uses: "yolo", "ollama" or "mock".
    detector: str = field(default_factory=lambda: _env("DETECTOR", "mock"))
    yolo_weights: str = field(
        default_factory=lambda: _env("YOLO_WEIGHTS", str(PROJECT_DIR / "models" / "sh17_yolo8s.pt"))
    )
    yolo_conf: float = field(default_factory=lambda: float(_env("YOLO_CONF", "0.35")))
    yolo_device: str = field(default_factory=lambda: _env("YOLO_DEVICE", ""))  # "", "cpu", "mps", "cuda:0"
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen2.5vl:7b"))
    ollama_timeout_s: float = field(default_factory=lambda: float(_env("OLLAMA_TIMEOUT_S", "120")))
    # Minimum AI confidence for a suggestion to be pre-selected in the report form.
    suggest_threshold: float = field(default_factory=lambda: float(_env("SUGGEST_THRESHOLD", "0.35")))


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _load_dotenv(PROJECT_DIR / ".env")
        _settings = Settings()
    return _settings


def override_settings(**kwargs) -> Settings:
    """Replace the cached settings (used by tests and scripts)."""
    global _settings
    base = get_settings()
    _settings = Settings(**{**base.__dict__, **kwargs})
    return _settings
