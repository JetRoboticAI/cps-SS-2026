from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelPackConfig:
    """Paths and filenames for one InsightFace model pack."""

    directory: Path
    detector: str
    recognizer: str
    database: Path


@dataclass(frozen=True)
class SpoofConfig:
    """Runtime settings for the optional anti-spoofing model."""

    enabled: bool
    model: Path
    crop_scale: float
    live_class_index: int
    live_threshold: float


@dataclass(frozen=True)
class AppConfig:
    """Validated application configuration loaded from config.json."""

    active_model_pack: str
    model_pack: ModelPackConfig
    spoof: SpoofConfig
    detection_size: tuple[int, int]
    detection_threshold: float
    recognition_threshold: float
    camera_process_every: int


def load_config(path: Path) -> AppConfig:
    """Load config.json and resolve all relative paths from the config location."""

    path = path.resolve()
    try:
        with path.open("r", encoding="utf-8") as config_file:
            raw = json.load(config_file)
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Config file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON config: {path}: {error}") from error

    base_dir = path.parent
    active_pack = _required_string(raw, "active_model_pack")
    model_packs = _required_dict(raw, "model_packs")
    if active_pack not in model_packs:
        choices = ", ".join(sorted(model_packs))
        raise ValueError(
            f"Unknown active_model_pack '{active_pack}'. Available packs: {choices}"
        )

    pack_raw = _required_dict(model_packs, active_pack)
    spoof_raw = _required_dict(raw, "spoof")
    runtime_raw = _required_dict(raw, "runtime")
    detection_size = runtime_raw.get("detection_size", [640, 640])
    if (
        not isinstance(detection_size, list)
        or len(detection_size) != 2
        or not all(isinstance(value, int) and value > 0 for value in detection_size)
    ):
        raise ValueError("runtime.detection_size must contain two positive integers")

    model_pack = ModelPackConfig(
        directory=_resolve_path(base_dir, _required_string(pack_raw, "directory")),
        detector=_required_string(pack_raw, "detector"),
        recognizer=_required_string(pack_raw, "recognizer"),
        database=_resolve_path(base_dir, _required_string(pack_raw, "database")),
    )
    spoof = SpoofConfig(
        enabled=bool(spoof_raw.get("enabled", True)),
        model=_resolve_path(base_dir, _required_string(spoof_raw, "model")),
        crop_scale=float(spoof_raw.get("crop_scale", 2.7)),
        live_class_index=int(spoof_raw.get("live_class_index", 1)),
        live_threshold=float(spoof_raw.get("live_threshold", 0.6)),
    )
    return AppConfig(
        active_model_pack=active_pack,
        model_pack=model_pack,
        spoof=spoof,
        detection_size=(detection_size[0], detection_size[1]),
        detection_threshold=float(runtime_raw.get("detection_threshold", 0.5)),
        recognition_threshold=float(runtime_raw.get("recognition_threshold", 0.45)),
        camera_process_every=int(runtime_raw.get("camera_process_every", 3)),
    )


def _resolve_path(base_dir: Path, value: str) -> Path:
    """Resolve user paths while keeping config-relative paths portable."""

    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def _required_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Config field '{key}' must be an object")
    return value


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Config field '{key}' must be a non-empty string")
    return value