"""Constants for sssom-curator."""

from __future__ import annotations

from typing import Literal, TypeAlias

__all__ = [
    "PredictionMethod",
    "RecognitionMethod",
]

RecognitionMethod: TypeAlias = Literal["ner", "grounding"]
PredictionMethod: TypeAlias = Literal["ner", "grounding", "embedding"]
