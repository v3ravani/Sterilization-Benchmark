"""
Strict data validator for benchmark integrity checking.

Every benchmark run must validate that the reconstructed object (after
serialize → transmit → deserialize) is bit-for-bit equivalent to the
original object. A run is only marked valid if this check passes.

Validation checks:
  1. Type equality     — original and reconstructed have the same Python type.
  2. Key equality      — all dict keys present in both directions (no extras/missing).
  3. Value equality    — recursive field-by-field deep comparison.
  4. Array ordering    — list element order is preserved exactly.
  5. Numeric fidelity  — float/int values match within tolerance.
  6. Nested integrity  — all sub-objects validated recursively.

ValidationResult is returned instead of raising exceptions so callers can
log results without crashing the entire benchmark run.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Union


# ─────────────────────────────────────────────────────────────────────────────
# Result container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """
    Result of a single data validation check.

    Attributes:
        valid:     True if original and reconstructed are equivalent.
        errors:    List of human-readable error descriptions.
        warnings:  List of non-critical discrepancies noted during validation.
    """
    valid:    bool        = True
    errors:   List[str]  = field(default_factory=list)
    warnings: List[str]  = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.valid = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def merge(self, other: "ValidationResult") -> None:
        """Merge another result into this one (used for recursive checks)."""
        if not other.valid:
            self.valid = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def summary(self) -> str:
        if self.valid:
            return f"VALID (warnings={len(self.warnings)})"
        return f"INVALID — {len(self.errors)} error(s): {'; '.join(self.errors[:3])}"

    def __repr__(self) -> str:
        return (
            f"ValidationResult(valid={self.valid}, "
            f"errors={len(self.errors)}, warnings={len(self.warnings)})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Core validator
# ─────────────────────────────────────────────────────────────────────────────

# Float comparison tolerance (handles floating-point serialization precision loss)
_FLOAT_REL_TOLERANCE = 1e-9
_FLOAT_ABS_TOLERANCE = 1e-12

# Maximum recursion depth guard
_MAX_DEPTH = 100


def _path_str(path: List[str]) -> str:
    """Format the current path for error messages."""
    return ".".join(path) if path else "<root>"


def _validate_recursive(
    original: Any,
    reconstructed: Any,
    path: List[str],
    result: ValidationResult,
    depth: int = 0,
) -> None:
    """
    Recursively validate that `reconstructed` equals `original`.

    :param original:      Original pre-serialization value.
    :param reconstructed: Decoded post-deserialization value.
    :param path:          Current key path for error reporting.
    :param result:        Accumulating ValidationResult.
    :param depth:         Current recursion depth.
    """
    if depth > _MAX_DEPTH:
        result.add_error(f"[{_path_str(path)}] Exceeded max recursion depth {_MAX_DEPTH}")
        return

    # ── None ────────────────────────────────────────────────────────────────
    if original is None:
        if reconstructed is not None:
            result.add_error(
                f"[{_path_str(path)}] Expected None, got {type(reconstructed).__name__}: {reconstructed!r}"
            )
        return

    # ── Type check ───────────────────────────────────────────────────────────
    # Allow int/float interchange from MessagePack decoding (int 1 decoded as int not float)
    orig_type = type(original)
    recon_type = type(reconstructed)

    numeric_types = (int, float)
    if orig_type != recon_type:
        if not (orig_type in numeric_types and recon_type in numeric_types):
            result.add_error(
                f"[{_path_str(path)}] Type mismatch: expected {orig_type.__name__}, "
                f"got {recon_type.__name__}"
            )
            return

    # ── Dict ─────────────────────────────────────────────────────────────────
    if isinstance(original, dict):
        if not isinstance(reconstructed, dict):
            result.add_error(
                f"[{_path_str(path)}] Expected dict, got {type(reconstructed).__name__}"
            )
            return

        orig_keys = set(original.keys())
        recon_keys = set(reconstructed.keys())

        missing = orig_keys - recon_keys
        extra = recon_keys - orig_keys

        if missing:
            result.add_error(
                f"[{_path_str(path)}] Missing keys in reconstructed: {sorted(missing)}"
            )
        if extra:
            result.add_error(
                f"[{_path_str(path)}] Extra keys in reconstructed: {sorted(extra)}"
            )

        # Validate all keys present in both
        for key in orig_keys & recon_keys:
            child_path = path + [str(key)]
            _validate_recursive(
                original[key], reconstructed[key], child_path, result, depth + 1
            )
        return

    # ── List ─────────────────────────────────────────────────────────────────
    if isinstance(original, list):
        if not isinstance(reconstructed, list):
            result.add_error(
                f"[{_path_str(path)}] Expected list, got {type(reconstructed).__name__}"
            )
            return

        if len(original) != len(reconstructed):
            result.add_error(
                f"[{_path_str(path)}] List length mismatch: "
                f"expected {len(original)}, got {len(reconstructed)}"
            )
            # Still validate up to min length for better diagnostics
            max_check = min(len(original), len(reconstructed))
        else:
            max_check = len(original)

        for i in range(max_check):
            child_path = path + [f"[{i}]"]
            _validate_recursive(
                original[i], reconstructed[i], child_path, result, depth + 1
            )
        return

    # ── Float ────────────────────────────────────────────────────────────────
    if isinstance(original, float):
        recon_float = float(reconstructed)
        import math
        if math.isnan(original) and math.isnan(recon_float):
            return  # NaN == NaN for our purposes
        if math.isinf(original):
            if original != recon_float:
                result.add_error(
                    f"[{_path_str(path)}] Infinity mismatch: {original} vs {recon_float}"
                )
            return
        abs_diff = abs(original - recon_float)
        rel_diff = abs_diff / (abs(original) + 1e-300)
        if abs_diff > _FLOAT_ABS_TOLERANCE and rel_diff > _FLOAT_REL_TOLERANCE:
            result.add_error(
                f"[{_path_str(path)}] Float mismatch: "
                f"expected {original!r}, got {recon_float!r} "
                f"(abs_diff={abs_diff:.2e})"
            )
        return

    # ── Bool (must come before int check) ─────────────────────────────────
    if isinstance(original, bool):
        if original is not reconstructed and original != reconstructed:
            result.add_error(
                f"[{_path_str(path)}] Bool mismatch: expected {original!r}, got {reconstructed!r}"
            )
        return

    # ── Int ──────────────────────────────────────────────────────────────────
    if isinstance(original, int):
        if int(original) != int(reconstructed):
            result.add_error(
                f"[{_path_str(path)}] Int mismatch: expected {original!r}, got {reconstructed!r}"
            )
        return

    # ── String ───────────────────────────────────────────────────────────────
    if isinstance(original, str):
        if original != reconstructed:
            preview_orig  = original[:80] + ("…" if len(original) > 80 else "")
            preview_recon = str(reconstructed)[:80]
            result.add_error(
                f"[{_path_str(path)}] String mismatch: "
                f"expected {preview_orig!r}, got {preview_recon!r}"
            )
        return

    # ── Fallback scalar ──────────────────────────────────────────────────────
    if original != reconstructed:
        result.add_error(
            f"[{_path_str(path)}] Value mismatch: expected {original!r}, got {reconstructed!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Public interface
# ─────────────────────────────────────────────────────────────────────────────

def validate(
    original: Any,
    reconstructed: Any,
) -> ValidationResult:
    """
    Perform a strict deep structural validation between original and reconstructed data.

    :param original:      The original data object before serialization.
    :param reconstructed: The reconstructed object after deserialization.
    :return: ValidationResult with valid=True if objects are equivalent.
    """
    result = ValidationResult()
    _validate_recursive(original, reconstructed, path=[], result=result, depth=0)
    return result


def assert_valid(
    original: Any,
    reconstructed: Any,
    context: str = "",
) -> None:
    """
    Validate and raise AssertionError if data is not equivalent.

    Convenience wrapper for test assertions.

    :param original:      Original data object.
    :param reconstructed: Reconstructed data object.
    :param context:       Optional label to include in the error message.
    :raises AssertionError: If validation fails.
    """
    result = validate(original, reconstructed)
    if not result.valid:
        ctx = f"[{context}] " if context else ""
        raise AssertionError(
            f"{ctx}Data validation FAILED with {len(result.errors)} error(s):\n"
            + "\n".join(f"  • {e}" for e in result.errors)
        )
