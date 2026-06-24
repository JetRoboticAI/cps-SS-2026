from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


@dataclass(frozen=True)
class SpoofResult:
    """Liveness prediction returned by the anti-spoofing model."""

    is_live: bool
    live_score: float
    predicted_class: int


class SpoofDetector:
    """ONNX anti-spoofing model wrapper for one detected face crop."""

    def __init__(
        self,
        model_path: Path,
        crop_scale: float = 2.7,
        live_class_index: int = 1,
        live_threshold: float = 0.6,
    ) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"Spoof model not found: {model_path}")
        if crop_scale <= 0:
            raise ValueError("Spoof crop scale must be positive")
        if not 0.0 <= live_threshold <= 1.0:
            raise ValueError("Spoof live threshold must be between 0 and 1")

        self.session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        input_config = self.session.get_inputs()[0]
        output_config = self.session.get_outputs()[0]
        input_shape = input_config.shape
        if len(input_shape) != 4 or not all(
            isinstance(value, int) for value in input_shape[2:]
        ):
            raise ValueError(f"Unsupported spoof model input shape: {input_shape}")

        self.input_name = input_config.name
        self.output_name = output_config.name
        self.input_height = int(input_shape[2])
        self.input_width = int(input_shape[3])
        self.crop_scale = crop_scale
        self.live_class_index = live_class_index
        self.live_threshold = live_threshold

    def predict(self, image: np.ndarray, bbox: np.ndarray) -> SpoofResult:
        """Run liveness detection for a face bounding box."""

        crop = self._crop_face(image, bbox)
        # ONNXRuntime expects the model input in NCHW format.
        tensor = crop.astype(np.float32).transpose(2, 0, 1)[None, ...]
        logits = self.session.run(
            [self.output_name],
            {self.input_name: tensor},
        )[0]
        probabilities = _softmax(logits)[0]
        if not 0 <= self.live_class_index < len(probabilities):
            raise ValueError(
                f"Live class index {self.live_class_index} is outside model output"
            )

        predicted_class = int(np.argmax(probabilities))
        live_score = float(probabilities[self.live_class_index])
        return SpoofResult(
            is_live=(
                predicted_class == self.live_class_index
                and live_score >= self.live_threshold
            ),
            live_score=live_score,
            predicted_class=predicted_class,
        )

    def _crop_face(self, image: np.ndarray, bbox: np.ndarray) -> np.ndarray:
        """Expand a face box, clamp it to the image, and resize it for the model."""

        image_height, image_width = image.shape[:2]
        left, top, right, bottom = np.asarray(bbox, dtype=np.float32)
        box_width = max(float(right - left), 1.0)
        box_height = max(float(bottom - top), 1.0)
        # Limit the expansion so the crop never grows beyond the source image.
        scale = min(
            (image_height - 1) / box_height,
            (image_width - 1) / box_width,
            self.crop_scale,
        )

        center_x = left + box_width / 2
        center_y = top + box_height / 2
        scaled_width = box_width * scale
        scaled_height = box_height * scale
        x1 = max(0, int(center_x - scaled_width / 2))
        y1 = max(0, int(center_y - scaled_height / 2))
        x2 = min(image_width - 1, int(center_x + scaled_width / 2))
        y2 = min(image_height - 1, int(center_y + scaled_height / 2))
        if x2 <= x1 or y2 <= y1:
            raise ValueError("Detected face has an invalid crop region")

        crop = image[y1 : y2 + 1, x1 : x2 + 1]
        return cv2.resize(crop, (self.input_width, self.input_height))


def _softmax(values: np.ndarray) -> np.ndarray:
    """Convert raw logits to probabilities in a numerically stable way."""

    shifted = values - np.max(values, axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / exponentials.sum(axis=1, keepdims=True)