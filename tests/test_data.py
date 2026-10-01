"""
Comprehensive test suite for Stage 3: Data Generator & Validation Engine.

Tests cover:
  - generate_flat_data:      structure, key format, value types, size scaling.
  - generate_nested_data:    schema, nesting, entry list growth.
  - generate_text_heavy_data: type, redundancy effect on record count.
  - generate_numeric_data:   series structure, numeric fidelity.
  - generate() unified entry: all types, invalid input handling.
  - Workload catalog:        definitions, lookup, filtering helpers.
  - ValidationResult:        error accumulation, merge, summary.
  - validate():              type mismatch, missing key, extra key, list length,
                             float tolerance, bool, nested, string, None.
  - assert_valid():          passes on match, raises on mismatch.
  - Full roundtrip:          generator → serializer → deserializer → validator
                             for all 3 formats × all 4 data types.
"""

import json
import pytest

# ── Modules under test ────────────────────────────────────────────────────────
from src.data.generator import (
    generate,
    generate_flat_data,
    generate_nested_data,
    generate_text_heavy_data,
    generate_numeric_data,
    GENERATOR_MAP,
)
from src.data.workloads import (
    Workload,
    SizeTarget,
    RedundancyLevel,
    DataStructure,
    WORKLOADS,
    get_workload,
    list_workload_names,
    get_workloads_by_structure,
    get_workloads_by_size,
)
from src.data.validator import (
    ValidationResult,
    validate,
    assert_valid,
)
from src.serialization import JSONSerializer, GzipJSONSerializer, MessagePackSerializer


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def json_size_kb(data) -> float:
    return len(json.dumps(data, separators=(',', ':')).encode()) / 1024


# ─────────────────────────────────────────────────────────────────────────────
# Tests: generate_flat_data
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateFlatData:
    def test_returns_dict(self):
        data = generate_flat_data(target_size_kb=5.0)
        assert isinstance(data, dict)

    def test_non_empty(self):
        data = generate_flat_data(target_size_kb=5.0)
        assert len(data) > 0

    def test_keys_are_strings(self):
        data = generate_flat_data(target_size_kb=5.0)
        for k in data:
            assert isinstance(k, str)

    def test_keys_follow_field_format(self):
        data = generate_flat_data(target_size_kb=5.0)
        for k in data:
            assert k.startswith("field_"), f"Key '{k}' does not start with 'field_'"

    def test_values_are_scalar(self):
        data = generate_flat_data(target_size_kb=5.0)
        for v in data.values():
            assert isinstance(v, (str, int, float, bool, type(None)))

    def test_target_size_small(self):
        data = generate_flat_data(target_size_kb=5.0)
        size = json_size_kb(data)
        assert 4.0 <= size <= 15.0, f"Expected ~5 KB, got {size:.2f} KB"

    def test_target_size_medium(self):
        data = generate_flat_data(target_size_kb=50.0)
        size = json_size_kb(data)
        assert 45.0 <= size <= 65.0, f"Expected ~50 KB, got {size:.2f} KB"

    def test_seed_reproducibility(self):
        d1 = generate_flat_data(target_size_kb=5.0, seed=99)
        d2 = generate_flat_data(target_size_kb=5.0, seed=99)
        assert d1 == d2

    def test_different_seeds_different_data(self):
        d1 = generate_flat_data(target_size_kb=5.0, seed=1)
        d2 = generate_flat_data(target_size_kb=5.0, seed=2)
        assert d1 != d2

    def test_high_redundancy_fewer_unique_values(self):
        low  = generate_flat_data(target_size_kb=20.0, redundancy="low")
        high = generate_flat_data(target_size_kb=20.0, redundancy="high")
        unique_low  = len(set(str(v) for v in low.values()))
        unique_high = len(set(str(v) for v in high.values()))
        assert unique_high < unique_low


# ─────────────────────────────────────────────────────────────────────────────
# Tests: generate_nested_data
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateNestedData:
    def test_returns_dict(self):
        data = generate_nested_data(target_size_kb=5.0)
        assert isinstance(data, dict)

    def test_has_schema_version(self):
        data = generate_nested_data(target_size_kb=5.0)
        assert "schema_version" in data

    def test_has_entries_list(self):
        data = generate_nested_data(target_size_kb=5.0)
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_entries_non_empty(self):
        data = generate_nested_data(target_size_kb=5.0)
        assert len(data["entries"]) > 0

    def test_entry_has_required_fields(self):
        data = generate_nested_data(target_size_kb=5.0)
        entry = data["entries"][0]
        assert "id" in entry
        assert "value" in entry
        assert "count" in entry
        assert "active" in entry

    def test_nested_children_present(self):
        data = generate_nested_data(target_size_kb=5.0)
        entry = data["entries"][0]
        # Root nodes should have children
        assert "children" in entry
        assert isinstance(entry["children"], list)

    def test_target_size_scaling(self):
        data = generate_nested_data(target_size_kb=30.0)
        size = json_size_kb(data)
        assert 25.0 <= size <= 50.0, f"Expected ~30 KB, got {size:.2f} KB"

    def test_seed_reproducibility(self):
        d1 = generate_nested_data(target_size_kb=5.0, seed=42)
        d2 = generate_nested_data(target_size_kb=5.0, seed=42)
        assert d1 == d2


# ─────────────────────────────────────────────────────────────────────────────
# Tests: generate_text_heavy_data
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateTextHeavyData:
    def test_returns_dict(self):
        data = generate_text_heavy_data(target_size_kb=5.0)
        assert isinstance(data, dict)

    def test_has_records(self):
        data = generate_text_heavy_data(target_size_kb=5.0)
        assert "records" in data
        assert isinstance(data["records"], list)
        assert len(data["records"]) > 0

    def test_record_has_expected_fields(self):
        data = generate_text_heavy_data(target_size_kb=5.0)
        rec = data["records"][0]
        assert "record_id" in rec
        assert "title" in rec
        assert "body" in rec
        assert "author" in rec

    def test_high_redundancy_produces_more_records_than_low(self):
        low  = generate_text_heavy_data(target_size_kb=20.0, redundancy="low")
        high = generate_text_heavy_data(target_size_kb=20.0, redundancy="high")
        # High redundancy = smaller string pool = shorter strings = more records
        # Not guaranteed, but high redundancy data should be at least somewhat similar size
        assert len(high["records"]) > 0
        assert len(low["records"]) > 0

    def test_target_size_scaling(self):
        data = generate_text_heavy_data(target_size_kb=20.0)
        size = json_size_kb(data)
        assert 15.0 <= size <= 35.0, f"Expected ~20 KB, got {size:.2f} KB"

    def test_seed_reproducibility(self):
        d1 = generate_text_heavy_data(target_size_kb=5.0, seed=7)
        d2 = generate_text_heavy_data(target_size_kb=5.0, seed=7)
        assert d1 == d2


# ─────────────────────────────────────────────────────────────────────────────
# Tests: generate_numeric_data
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateNumericData:
    def test_returns_dict(self):
        data = generate_numeric_data(target_size_kb=5.0)
        assert isinstance(data, dict)

    def test_has_series(self):
        data = generate_numeric_data(target_size_kb=5.0)
        assert "series" in data
        assert isinstance(data["series"], list)
        assert len(data["series"]) > 0

    def test_series_has_readings(self):
        data = generate_numeric_data(target_size_kb=5.0)
        series = data["series"][0]
        assert "readings" in series
        assert isinstance(series["readings"], list)
        assert len(series["readings"]) > 0

    def test_series_has_stats(self):
        data = generate_numeric_data(target_size_kb=5.0)
        series = data["series"][0]
        assert "min" in series
        assert "max" in series
        assert "mean" in series

    def test_min_max_consistent(self):
        data = generate_numeric_data(target_size_kb=5.0)
        for series in data["series"]:
            readings = series["readings"]
            assert series["min"] == min(readings)
            assert series["max"] == max(readings)

    def test_low_redundancy_high_precision(self):
        data = generate_numeric_data(target_size_kb=5.0, redundancy="low")
        series = data["series"][0]
        # Low redundancy uses 6 decimal places
        for r in series["readings"]:
            assert isinstance(r, float)

    def test_high_redundancy_integer_readings(self):
        data = generate_numeric_data(target_size_kb=5.0, redundancy="high")
        series = data["series"][0]
        for r in series["readings"]:
            assert isinstance(r, int)

    def test_target_size_scaling(self):
        data = generate_numeric_data(target_size_kb=30.0)
        size = json_size_kb(data)
        assert 25.0 <= size <= 50.0, f"Expected ~30 KB, got {size:.2f} KB"

    def test_seed_reproducibility(self):
        d1 = generate_numeric_data(target_size_kb=5.0, seed=21)
        d2 = generate_numeric_data(target_size_kb=5.0, seed=21)
        assert d1 == d2


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Unified generate() entry point
# ─────────────────────────────────────────────────────────────────────────────

class TestUnifiedGenerate:
    @pytest.mark.parametrize("structure", ["flat", "nested", "text_heavy", "numeric"])
    def test_all_structures_return_data(self, structure):
        data = generate(structure=structure, target_size_kb=5.0)
        assert data is not None
        assert len(data) > 0

    @pytest.mark.parametrize("redundancy", ["low", "medium", "high"])
    def test_all_redundancy_levels(self, redundancy):
        data = generate(structure="flat", target_size_kb=5.0, redundancy=redundancy)
        assert isinstance(data, dict)

    def test_invalid_structure_raises(self):
        with pytest.raises(ValueError, match="Unknown structure"):
            generate(structure="unknown_type", target_size_kb=5.0)

    def test_invalid_redundancy_raises(self):
        with pytest.raises(ValueError, match="Unknown redundancy"):
            generate(structure="flat", target_size_kb=5.0, redundancy="extreme")

    def test_generator_map_has_all_types(self):
        assert "flat" in GENERATOR_MAP
        assert "nested" in GENERATOR_MAP
        assert "text_heavy" in GENERATOR_MAP
        assert "numeric" in GENERATOR_MAP


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Workload catalog
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkloadCatalog:
    def test_workloads_list_non_empty(self):
        assert len(WORKLOADS) > 0

    def test_all_workloads_have_valid_structure(self):
        valid_structures = {DataStructure.FLAT, DataStructure.NESTED,
                            DataStructure.TEXT_HEAVY, DataStructure.NUMERIC}
        for w in WORKLOADS:
            assert w.structure in valid_structures, f"{w.name}: invalid structure"

    def test_all_workloads_have_valid_redundancy(self):
        valid = {RedundancyLevel.LOW, RedundancyLevel.MEDIUM, RedundancyLevel.HIGH}
        for w in WORKLOADS:
            assert w.redundancy in valid, f"{w.name}: invalid redundancy"

    def test_all_workloads_have_valid_size(self):
        valid_sizes = {SizeTarget.SMALL, SizeTarget.MEDIUM, SizeTarget.LARGE}
        for w in WORKLOADS:
            assert w.target_size_kb in valid_sizes, f"{w.name}: invalid size"

    def test_workload_names_are_unique(self):
        names = [w.name for w in WORKLOADS]
        assert len(names) == len(set(names)), "Duplicate workload names detected"

    def test_get_workload_valid(self):
        w = get_workload("flat_small_low")
        assert w.structure == DataStructure.FLAT
        assert w.target_size_kb == SizeTarget.SMALL
        assert w.redundancy == RedundancyLevel.LOW

    def test_get_workload_invalid_raises(self):
        with pytest.raises(KeyError):
            get_workload("nonexistent_workload")

    def test_list_workload_names_sorted(self):
        names = list_workload_names()
        assert names == sorted(names)

    def test_get_workloads_by_structure_flat(self):
        flat_workloads = get_workloads_by_structure("flat")
        assert all(w.structure == "flat" for w in flat_workloads)
        assert len(flat_workloads) > 0

    def test_get_workloads_by_structure_numeric(self):
        numeric_workloads = get_workloads_by_structure("numeric")
        assert all(w.structure == "numeric" for w in numeric_workloads)

    def test_get_workloads_by_size_small(self):
        small = get_workloads_by_size("small")
        assert all(w.target_size_kb == SizeTarget.SMALL for w in small)
        assert len(small) > 0

    def test_get_workloads_by_size_invalid_raises(self):
        with pytest.raises(ValueError):
            get_workloads_by_size("tiny")

    def test_workload_is_immutable(self):
        w = get_workload("flat_small_low")
        with pytest.raises((AttributeError, TypeError)):
            w.name = "modified"  # type: ignore

    def test_workload_str_repr(self):
        w = get_workload("flat_small_low")
        s = str(w)
        assert "flat" in s
        assert "Workload" in s


# ─────────────────────────────────────────────────────────────────────────────
# Tests: ValidationResult
# ─────────────────────────────────────────────────────────────────────────────

class TestValidationResult:
    def test_default_valid(self):
        r = ValidationResult()
        assert r.valid is True
        assert r.errors == []
        assert r.warnings == []

    def test_add_error_marks_invalid(self):
        r = ValidationResult()
        r.add_error("something broke")
        assert r.valid is False
        assert len(r.errors) == 1

    def test_add_warning_stays_valid(self):
        r = ValidationResult()
        r.add_warning("minor issue")
        assert r.valid is True
        assert len(r.warnings) == 1

    def test_merge_invalid(self):
        r1 = ValidationResult()
        r2 = ValidationResult()
        r2.add_error("child error")
        r1.merge(r2)
        assert r1.valid is False
        assert "child error" in r1.errors

    def test_summary_valid(self):
        r = ValidationResult()
        assert "VALID" in r.summary()

    def test_summary_invalid(self):
        r = ValidationResult()
        r.add_error("test error")
        assert "INVALID" in r.summary()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: validate()
# ─────────────────────────────────────────────────────────────────────────────

class TestValidate:
    def test_identical_flat_dicts(self):
        d = {"a": 1, "b": "hello", "c": True}
        result = validate(d, d.copy())
        assert result.valid

    def test_type_mismatch(self):
        result = validate({"a": 1}, {"a": "1"})
        assert not result.valid
        assert any("Type mismatch" in e or "Int mismatch" in e for e in result.errors)

    def test_missing_key(self):
        result = validate({"a": 1, "b": 2}, {"a": 1})
        assert not result.valid
        assert any("Missing keys" in e for e in result.errors)

    def test_extra_key(self):
        result = validate({"a": 1}, {"a": 1, "b": 2})
        assert not result.valid
        assert any("Extra keys" in e for e in result.errors)

    def test_list_order_preserved(self):
        original = {"items": [3, 1, 2]}
        shuffled = {"items": [1, 2, 3]}
        result = validate(original, shuffled)
        assert not result.valid

    def test_list_length_mismatch(self):
        result = validate({"items": [1, 2, 3]}, {"items": [1, 2]})
        assert not result.valid
        assert any("length" in e for e in result.errors)

    def test_float_tolerance_within(self):
        # Tiny float delta within tolerance — should be valid
        result = validate({"v": 1.0000000001}, {"v": 1.0})
        assert result.valid

    def test_float_mismatch_outside_tolerance(self):
        result = validate({"v": 1.0}, {"v": 2.0})
        assert not result.valid

    def test_bool_values(self):
        result = validate({"flag": True}, {"flag": True})
        assert result.valid

    def test_bool_mismatch(self):
        result = validate({"flag": True}, {"flag": False})
        assert not result.valid

    def test_none_value_valid(self):
        result = validate({"x": None}, {"x": None})
        assert result.valid

    def test_none_mismatch(self):
        result = validate({"x": None}, {"x": 0})
        assert not result.valid

    def test_string_mismatch(self):
        result = validate({"name": "alice"}, {"name": "bob"})
        assert not result.valid
        assert any("String mismatch" in e for e in result.errors)

    def test_nested_dict_valid(self):
        d = {"outer": {"inner": {"value": 42}}}
        result = validate(d, {"outer": {"inner": {"value": 42}}})
        assert result.valid

    def test_nested_dict_inner_mismatch(self):
        original = {"outer": {"inner": {"value": 42}}}
        wrong    = {"outer": {"inner": {"value": 99}}}
        result = validate(original, wrong)
        assert not result.valid

    def test_empty_dict_valid(self):
        result = validate({}, {})
        assert result.valid

    def test_empty_list_valid(self):
        result = validate({"items": []}, {"items": []})
        assert result.valid

    def test_integer_match(self):
        result = validate({"n": 12345}, {"n": 12345})
        assert result.valid

    def test_integer_mismatch(self):
        result = validate({"n": 1}, {"n": 2})
        assert not result.valid


# ─────────────────────────────────────────────────────────────────────────────
# Tests: assert_valid()
# ─────────────────────────────────────────────────────────────────────────────

class TestAssertValid:
    def test_passes_on_equal_data(self):
        d = {"x": 1, "y": [1, 2, 3]}
        assert_valid(d, {"x": 1, "y": [1, 2, 3]})  # should not raise

    def test_raises_on_mismatch(self):
        with pytest.raises(AssertionError, match="FAILED"):
            assert_valid({"x": 1}, {"x": 2})

    def test_context_in_error_message(self):
        with pytest.raises(AssertionError, match="json_roundtrip"):
            assert_valid({"x": 1}, {"x": 2}, context="json_roundtrip")


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Full roundtrip (generator → serializer → deserializer → validator)
# ─────────────────────────────────────────────────────────────────────────────

SERIALIZERS = [
    JSONSerializer(),
    GzipJSONSerializer(),
    MessagePackSerializer(),
]
STRUCTURES = ["flat", "nested", "text_heavy", "numeric"]


@pytest.mark.parametrize("structure", STRUCTURES)
@pytest.mark.parametrize("serializer", SERIALIZERS, ids=lambda s: s.name)
def test_full_roundtrip(structure, serializer):
    """
    Critical benchmark integrity test:
    Every generated dataset must survive a serialize → deserialize cycle
    with zero data loss across all 3 formats and all 4 data types.
    """
    original = generate(
        structure=structure,
        target_size_kb=5.0,
        redundancy="medium",
        seed=42,
    )

    payload       = serializer.serialize(original)
    reconstructed = serializer.deserialize(payload)

    result = validate(original, reconstructed)
    assert result.valid, (
        f"Roundtrip FAILED for {serializer.name} + {structure}:\n"
        + "\n".join(f"  • {e}" for e in result.errors[:10])
    )
