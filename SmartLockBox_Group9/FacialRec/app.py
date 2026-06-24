from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
from insightface.app.common import Face

import numpy as np

from SmartLockBox_Group9.FacialRec.config import AppConfig, load_config
from SmartLockBox_Group9.FacialRec.face_engine import FaceDatabase, FaceEngine, Match, draw_face, read_image
from SmartLockBox_Group9.FacialRec.spoof_engine import SpoofDetector, SpoofResult

from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = PROJECT_DIR / "config.json"


@dataclass(frozen=True)
class FaceResult:
    """Combined recognition and anti-spoofing result for one detected face."""

    face: Face
    match: Match | None
    spoof: SpoofResult | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lightweight local face recognition")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    enroll_parser = subparsers.add_parser(
        "enroll",
        help="Enroll or update one identity from an image",
    )
    enroll_parser.add_argument("name")
    enroll_parser.add_argument("image", type=Path)

    recognize_parser = subparsers.add_parser(
        "recognize",
        help="Recognize faces in an image",
    )
    recognize_parser.add_argument("image", type=Path)
    recognize_parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "output.jpg",
    )

    camera_parser = subparsers.add_parser(
        "camera",
        help="Run real-time recognition from a camera",
    )
    camera_parser.add_argument("--camera-id", type=int, default=0)
    return parser


def create_engine(config: AppConfig) -> FaceEngine:
    """Build the face detector and recognizer from the selected model pack."""

    pack = config.model_pack
    return FaceEngine(
        model_dir=pack.directory,
        detector_filename=pack.detector,
        recognizer_filename=pack.recognizer,
        detection_size=config.detection_size,
        detection_threshold=config.detection_threshold,
    )


def create_spoof_detector(config: AppConfig) -> SpoofDetector | None:
    """Create the spoof detector only when it is enabled in the config."""

    if not config.spoof.enabled:
        return None
    return SpoofDetector(
        model_path=config.spoof.model,
        crop_scale=config.spoof.crop_scale,
        live_class_index=config.spoof.live_class_index,
        live_threshold=config.spoof.live_threshold,
    )


def enroll(args: argparse.Namespace, config: AppConfig) -> None:
    engine = create_engine(config)
    image = read_image(args.image)
    faces = engine.detect(image)
    # Enrollment must use a single clear face so the saved embedding belongs to
    # exactly one identity.
    if len(faces) != 1:
        raise ValueError(
            f"Enrollment image must contain exactly one face; detected {len(faces)}"
        )

    database = FaceDatabase(config.model_pack.database)
    database.add(args.name, faces[0].normed_embedding)
    print(
        f"Enrolled '{args.name}' with {config.active_model_pack}. "
        f"Database: {config.model_pack.database}"
    )


def analyze_faces(
    image,
    engine: FaceEngine,
    database: FaceDatabase,
    spoof_detector: SpoofDetector | None,
    recognition_threshold: float,
) -> list[FaceResult]:
    """Detect faces, reject spoofed faces, and match live faces against the DB."""

    results: list[FaceResult] = []
    for face in engine.detect(image):
        spoof = (
            spoof_detector.predict(image, face.bbox)
            if spoof_detector is not None
            else None
        )
        match = None
        # Skip recognition for faces that fail the liveness check.
        if spoof is None or spoof.is_live:
            match = database.match(face.normed_embedding, recognition_threshold)
        results.append(FaceResult(face=face, match=match, spoof=spoof))
    return results


def format_result(result: FaceResult) -> tuple[str, tuple[int, int, int]]:
    if result.spoof is not None and not result.spoof.is_live:
        return f"spoof live={result.spoof.live_score:.2f}", (30, 30, 220)

    if result.match is None:
        return "unknown", (30, 30, 220)

    label = f"{result.match.name} {result.match.similarity:.2f}"
    color = (40, 190, 40) if result.match.name != "unknown" else (30, 165, 255)
    if result.spoof is not None:
        label += f" live={result.spoof.live_score:.2f}"
    return label, color


def recognize(config: AppConfig,image: np.ndarray) -> list[FaceResult]:
    engine = create_engine(config)
    database = FaceDatabase(config.model_pack.database)
    spoof_detector = create_spoof_detector(config)
    # image = read_image(args.image)
    results = analyze_faces(
        image,
        engine,
        database,
        spoof_detector,
        config.recognition_threshold,
    )

    for result in results:
        label, color = format_result(result)
        draw_face(image, result.face, label, color)
        print(label)

    return results


def camera(args: argparse.Namespace, config: AppConfig) -> None:
    engine = create_engine(config)
    database = FaceDatabase(config.model_pack.database)
    spoof_detector = create_spoof_detector(config)
    capture = cv2.VideoCapture(args.camera_id)
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open camera: {args.camera_id}")

    frame_index = 0
    results: list[FaceResult] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError("Unable to read a camera frame")

            # Running the models every frame can be expensive on CPU, so reuse
            # the latest results between processed frames.
            if frame_index % max(config.camera_process_every, 1) == 0:
                results = analyze_faces(
                    frame,
                    engine,
                    database,
                    spoof_detector,
                    config.recognition_threshold,
                )

            for result in results:
                label, color = format_result(result)
                draw_face(frame, result.face, label, color)

            cv2.imshow("FacialRec - press q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            frame_index += 1
    finally:
        capture.release()
        cv2.destroyAllWindows()


def main() -> None:
    args = build_parser().parse_args()
    try:
        config = load_config(args.config)
        print(
            f"Model pack: {config.active_model_pack}; "
            f"spoof detection: {'on' if config.spoof.enabled else 'off'}"
        )
        commands = {
            "enroll": enroll,
            "recognize": recognize,
            "camera": camera,
        }
        commands[args.command](args, config)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()