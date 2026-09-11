"""One robust linear fitter over caller-declared feature families.

No claim of identifying arbitrary dynamics or of calibrated probabilities.
Independent validation data is required. Underidentified designs abstain.
"""
from dataclasses import dataclass
import numpy as np


def features(family, x, u=None, g=None):
    x = np.asarray(x, dtype=float)
    if family == "recurrence":
        if x.ndim != 2:
            raise ValueError("recurrence input must be a matrix of lag values")
        return np.column_stack((x, np.ones(len(x))))
    if x.ndim != 1:
        raise ValueError("x must be a vector")
    if family == "affine":
        return np.column_stack((x, np.ones(len(x))))
    if family == "controlled":
        u = np.asarray(u, dtype=float)
        if u.shape != x.shape:
            raise ValueError("u must have x's shape")
        return np.column_stack((x, u, np.ones(len(x))))
    if family == "gated":
        g = np.asarray(g, dtype=float)
        if g.shape != x.shape or not np.all((g == 0) | (g == 1)):
            raise ValueError("g must be a binary vector with x's shape")
        return np.column_stack((g*x, g, (1-g)*x, 1-g))
    raise ValueError("unsupported feature family")


@dataclass(frozen=True)
class NumericModel:
    status: str
    coefficients: tuple = ()
    train_fraction: float = 0.0
    validation_fraction: float = 0.0
    reason: str = ""

    def predict(self, design):
        if self.status != "ANSWER":
            raise ValueError("cannot predict with a rejected/unidentified model")
        design = np.asarray(design, dtype=float)
        if not np.all(np.isfinite(design)):
            raise ValueError("design must be finite")
        return design @ np.array(self.coefficients)


def fit_linear(design, targets, validation_design, validation_targets, *,
               seed=0, trials=256, atol=1e-7, rtol=1e-7, min_fraction=0.55):
    x, y, vx, vy = [np.asarray(a, dtype=float) for a in
                    (design, targets, validation_design, validation_targets)]
    if (x.ndim != 2 or vx.ndim != 2 or y.shape != (len(x),)
            or vy.shape != (len(vx),) or vx.shape[1] != x.shape[1]
            or not all(np.all(np.isfinite(a)) for a in (x, y, vx, vy))):
        raise ValueError("incompatible or nonfinite training/validation arrays")
    if not 0.5 < min_fraction <= 1 or atol < 0 or rtol < 0 or trials < 1:
        raise ValueError("invalid fitter settings")
    p = x.shape[1]
    if p == 0 or len(x) < max(4*p, 8) or len(vx) < max(p+2, 6):
        return NumericModel("UNKNOWN", reason="insufficient evidence")
    scales = np.maximum(np.sqrt(np.mean(x*x, axis=0)), 1e-12)
    normalized = x / scales
    if np.linalg.matrix_rank(normalized) < p:
        return NumericModel("UNKNOWN", reason="rank-deficient feature design")
    rng = np.random.default_rng(seed)
    tolerance = atol + rtol*np.abs(y)
    best = None
    best_key = (-1, -np.inf)
    for _ in range(trials):
        index = rng.choice(len(x), p, replace=False)
        if np.linalg.matrix_rank(normalized[index]) < p:
            continue
        coef = np.linalg.lstsq(normalized[index], y[index], rcond=None)[0]
        residual = np.abs(normalized @ coef - y)
        inlier = residual <= tolerance
        key = (int(inlier.sum()), -float(np.median(residual)))
        if key > best_key:
            best_key, best = key, inlier
    if best is None or best.mean() < min_fraction:
        return NumericModel("UNKNOWN", reason="no supported linear consensus")
    if np.linalg.matrix_rank(normalized[best]) < p:
        return NumericModel("UNKNOWN", reason="inlier design is not identifiable")
    coef = np.linalg.lstsq(normalized[best], y[best], rcond=None)[0] / scales
    train_fraction = float(np.mean(np.abs(x @ coef-y) <= tolerance))
    validation_fraction = float(np.mean(np.abs(vx @ coef-vy) <= atol+rtol*np.abs(vy)))
    if train_fraction < min_fraction or validation_fraction < min_fraction:
        return NumericModel("UNKNOWN", (), train_fraction, validation_fraction,
                            "independent validation rejected family")
    return NumericModel("ANSWER", tuple(map(float, coef)), train_fraction,
                        validation_fraction, "validated within supplied feature family")
