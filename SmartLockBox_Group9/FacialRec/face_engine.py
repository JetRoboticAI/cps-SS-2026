from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from insightface.app.common import Face
from insightface.model_zoo import model_zoo


@dataclass(frozen=True)
class Match:
    """Best database match for a face embedding."""

    name: str
    similarity: float


class FaceDatabase:
    """Small on-disk face embedding database backed by a compressed NPZ file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.names: list[str] = []
        self.embeddings = np.empty((0, 512), dtype=np.float32)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return

        with np.load(self.path, allow_pickle=False) as data:
            self.names = data["names"].astype(str).tolist()
            self.embeddings = data["embeddings"].astype(np.float32)

    def add(self, name: str, embedding: np.ndarray) -> None:
        """Add a new identity or replace an existing identity's embedding."""

        embedding = _normalize(embedding).reshape(1, -1)
        if name in self.names:
            index = self.names.index(name)
            self.embeddings[index] = embedding[0]
        else:
            self.names.append(name)
            self.embeddings = np.vstack((self.embeddings, embedding))

        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            self.path,
            names=np.asarray(self.names),
            embeddings=self.embeddings,
        )

    def match(self, embedding: np.ndarray, threshold: float) -> Match:
        """Return the closest identity if cosine similarity passes the threshold."""

        if not self.names:
            return Match("unknown", 0.0)

        # Stored embeddings are normalized, so the dot product is cosine similarity.
        similarities = self.embeddings @ _normalize(embedding)
        index = int(np.argmax(similarities))
        similarity = float(similarities[index])
        name = self.names[index] if similarity >= threshold else "unknown"
        return Match(name, similarity)


class FaceEngine:
    """Wrapper around InsightFace detection and recognition ONNX models."""

    def __init__(
        self,
        model_dir: Path,
        detector_filename: str,
        recognizer_filename: str,
        detection_size: tuple[int, int] = (640, 640),
        detection_threshold: float = 0.5,
    ) -> None:
        detector_path = model_dir / detector_filename
        recognizer_path = model_dir / recognizer_filename
        for path in (detector_path, recognizer_path):
            if not path.is_file():
                raise FileNotFoundError(f"Model file not found: {path}")

        providers = ["CPUExecutionProvider"]
        self.detector = model_zoo.get_model(
            str(detector_path), providers=providers
        )
        self.recognizer = model_zoo.get_model(
            str(recognizer_path), providers=providers
        )
        self.detector.prepare(
            ctx_id=-1,
            input_size=detection_size,
            det_thresh=detection_threshold,
        )
        self.recognizer.prepare(ctx_id=-1)

    def detect(self, image: np.ndarray) -> list[Face]:
        """Detect every face in an image and attach a normalized embedding."""

        boxes, landmarks = self.detector.detect(image, max_num=0)
        if boxes is None:
            return []

        faces: list[Face] = []
        for index, box in enumerate(boxes):
            face = Face(
                bbox=box[:4],
                det_score=float(box[4]),
                kps=None if landmarks is None else landmarks[index],
            )
            self.recognizer.get(image, face)
            faces.append(face)
        return faces


def read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Unable to read image: {path}")
    return image


def draw_face(
    image: np.ndarray,
    face: Face,
    label: str,
    color: tuple[int, int, int],
) -> None:
    """Draw one labeled face box directly onto the image."""

    left, top, right, bottom = face.bbox.astype(int)
    cv2.rectangle(image, (left, top), (right, bottom), color, 2)
    text_y = max(top - 8, 20)
    cv2.putText(
        image,
        label,
        (left, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        color,
        2,
        cv2.LINE_AA,
    )


def _normalize(embedding: np.ndarray) -> np.ndarray:
    """Convert an embedding to unit length for cosine-similarity matching."""

    embedding = np.asarray(embedding, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(embedding))
    if norm == 0:
        raise ValueError("Face embedding is empty")
    return embedding / norm