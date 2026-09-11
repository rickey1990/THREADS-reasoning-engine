"""Deterministic numerical lowering with explicit floating-point failure."""
import numpy as np


def _vector(value):
    value = np.asarray(value, dtype=float)
    if value.ndim != 1 or not np.all(np.isfinite(value)):
        raise ValueError("expected a finite one-dimensional array")
    return value


def convolve(x, kernel, backend="auto"):
    x, kernel = _vector(x), _vector(kernel)
    if not len(x) or not len(kernel):
        raise ValueError("convolution inputs must be nonempty")
    if backend == "auto":
        backend = "fft" if len(x) * len(kernel) >= 1_000_000 else "direct"
    with np.errstate(over="raise", invalid="raise"):
        if backend == "direct":
            result = np.convolve(x, kernel)
        elif backend == "fft":
            length = len(x) + len(kernel) - 1
            size = 1 << (length - 1).bit_length()
            result = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(kernel, size), size)[:length]
        else:
            raise ValueError("backend must be auto, direct, or fft")
    if not np.all(np.isfinite(result)):
        raise FloatingPointError("nonfinite convolution result")
    return result, backend


def affine_recurrence(a, b, initial=0.0, backend="auto"):
    a, b = _vector(a), _vector(b)
    if len(a) != len(b) or not np.isfinite(initial):
        raise ValueError("coefficient lengths must match; initial must be finite")
    if backend == "auto":
        backend = "scan" if len(a) >= 1024 else "direct"
    if backend == "scan" and np.any(np.abs(a) > 1):
        # Expansive composed transforms can overflow or catastrophically cancel
        # even when every sequential state is finite (e.g. x'=2*x-1, x0=1).
        # Conservatively retain sequential semantics on this whole family.
        result, _ = affine_recurrence(a, b, initial, backend="direct")
        return result, "direct-fallback"
    with np.errstate(over="raise", invalid="raise"):
        if backend == "direct":
            result = np.empty(len(a))
            state = np.float64(initial)
            for i in range(len(a)):
                state = a[i] * state + b[i]
                result[i] = state
        elif backend == "scan":
            # Hillis-Steele: logarithmic depth, O(n log n) work, O(n) arrays.
            aa, bb = a.copy(), b.copy()
            offset = 1
            while offset < len(a):
                aa[offset:], bb[offset:] = (aa[offset:] * aa[:-offset],
                                            aa[offset:] * bb[:-offset] + bb[offset:])
                offset *= 2
            result = aa * initial + bb
        else:
            raise ValueError("backend must be auto, direct, or scan")
    if not np.all(np.isfinite(result)):
        raise FloatingPointError("nonfinite recurrence result")
    return result, backend
