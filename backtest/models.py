from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import numpy as np


@dataclass(frozen=True)
class LogisticModel:
    feature_cols: list[str]
    coef: np.ndarray
    intercept: float
    mean: np.ndarray
    scale: np.ndarray

    @staticmethod
    def from_json(path: Path) -> "LogisticModel":
        raw: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        cols = list(raw["feature_cols"])
        coef = np.asarray(raw["coef"], dtype="float64")
        intercept = float(raw["intercept"])
        mean = np.asarray(raw["scaler"]["mean"], dtype="float64")
        scale = np.asarray(raw["scaler"]["scale"], dtype="float64")
        scale = np.where(scale == 0, 1.0, scale)
        if coef.shape[0] != len(cols):
            raise ValueError(f"coef length mismatch: {coef.shape[0]} vs {len(cols)}")
        return LogisticModel(cols, coef, intercept, mean, scale)

    def predict_proba(self, feats: Dict[str, float]) -> float:
        x = np.asarray([float(feats.get(c, 0.0) or 0.0) for c in self.feature_cols], dtype="float64")
        xs = (x - self.mean) / self.scale
        z = float(np.dot(self.coef, xs) + self.intercept)
        return float(1.0 / (1.0 + np.exp(-z)))

