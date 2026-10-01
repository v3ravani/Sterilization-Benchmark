"""
Comprehensive test suite for all serialization format handlers and the registry.

Tests cover:
  - Roundtrip integrity (serialize -> deserialize matches original) for JSON, GZIP JSON, MessagePack.
  - All supported data structures: flat, nested, arrays, mixed types.
  - Payload non-empty and byte type checks.
  - SerializerRegistry: listing, retrieval, error on unknown name.
  - GZIP compression effectiveness: compressed payload < JSON payload for redundant data.
  - Error handling: empty payload, None input.
"""

import pytest
from src.serialization import (
    JSONSerializer,
    GzipJSONSerializer,
    MessagePackSerializer,
    SerializerRegistry,
    get_serializer,
    list_serializers,
)
from src.serialization.base import BaseSerializer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def json_ser():
    return JSONSerializer()


@pytest.fixture
def gzip_ser():
    return GzipJSONSerializer(compresslevel=6)


@pytest.fixture
def msgpack_ser():
    return MessagePackSerializer()


@pytest.fixture
def all_serializers(json_ser, gzip_ser, msgpack_ser):
    return [json_ser, gzip_ser, msgpack_ser]


@pytest.fixture
def flat_dict():
    return {
        "id": 1,
        "name": "benchmark_test",
        "score": 99.75,
        "active": True,
        "tags": None,
    }


@pytest.fixture
def nested_dict():
    return {
        "experiment": {
            "id": "exp_001",
            "format": "json",
            "network": {
                "profile": "SLOW",
                "bandwidth_mbps": 10.0,
                "latency_ms": 50.0,
            },
            "payload": {
                "size_bytes": 512000,
                "compression_ratio": 0.45,
            },
        },
        "runs": [
            {"run_id": 1, "latency_ms": 120.3, "valid": True},
            {"run_id": 2, "latency_ms": 118.7, "valid": True},
            {"run_id": 3, "latency_ms": 125.1, "valid": False},
        ],
    }


@pytest.fixture
def array_dict():
    return {
        "measurements": [i * 0.1 for i in range(100)],
        "labels": [f"sample_{i}" for i in range(100)],
        "flags": [bool(i % 2) for i in range(100)],
    }


@pytest.fixture
def redundant_dict():
    """Data with high redundancy - ideal for testing GZIP compression effectiveness."""
    repeated_word = "benchmark-data-field"
    return {
        f"key_{i}": f"{repeated_word}-{repeated_word}-{repeated_word}"
        for i in range(200)
    }


# ---------------------------------------------------------------------------
# Tests: BaseSerializer interface
# ---------------------------------------------------------------------------

class TestBaseSerializerInterface:
    def test_json_is_base_serializer(self, json_ser):
        assert isinstance(json_ser, BaseSerializer)

    def test_gzip_is_base_serializer(self, gzip_ser):
        assert isinstance(gzip_ser, BaseSerializer)

    def test_msgpack_is_base_serializer(self, msgpack_ser):
        assert isinstance(msgpack_ser, BaseSerializer)

    def test_json_name(self, json_ser):
        assert json_ser.name == "json"

    def test_gzip_name(self, gzip_ser):
        assert gzip_ser.name == "json_gzip"

    def test_msgpack_name(self, msgpack_ser):
        assert msgpack_ser.name == "messagepack"


# ---------------------------------------------------------------------------
# Tests: Roundtrip integrity - flat dict
# ---------------------------------------------------------------------------

class TestRoundtripFlat:
    def test_json_flat(self, json_ser, flat_dict):
        payload = json_ser.serialize(flat_dict)
        result = json_ser.deserialize(payload)
        assert result == flat_dict

    def test_gzip_flat(self, gzip_ser, flat_dict):
        payload = gzip_ser.serialize(flat_dict)
        result = gzip_ser.deserialize(payload)
        assert result == flat_dict

    def test_msgpack_flat(self, msgpack_ser, flat_dict):
        payload = msgpack_ser.serialize(flat_dict)
        result = msgpack_ser.deserialize(payload)
        assert result == flat_dict


# ---------------------------------------------------------------------------
# Tests: Roundtrip integrity - nested dict
# ---------------------------------------------------------------------------

class TestRoundtripNested:
    def test_json_nested(self, json_ser, nested_dict):
        payload = json_ser.serialize(nested_dict)
        result = json_ser.deserialize(payload)
        assert result == nested_dict

    def test_gzip_nested(self, gzip_ser, nested_dict):
        payload = gzip_ser.serialize(nested_dict)
        result = gzip_ser.deserialize(payload)
        assert result == nested_dict

    def test_msgpack_nested(self, msgpack_ser, nested_dict):
        payload = msgpack_ser.serialize(nested_dict)
        result = msgpack_ser.deserialize(payload)
        assert result == nested_dict


# ---------------------------------------------------------------------------
# Tests: Roundtrip integrity - arrays and large data
# ---------------------------------------------------------------------------

class TestRoundtripArrays:
    def test_json_arrays(self, json_ser, array_dict):
        payload = json_ser.serialize(array_dict)
        result = json_ser.deserialize(payload)
        assert result == array_dict

    def test_gzip_arrays(self, gzip_ser, array_dict):
        payload = gzip_ser.serialize(array_dict)
        result = gzip_ser.deserialize(payload)
        assert result == array_dict

    def test_msgpack_arrays(self, msgpack_ser, array_dict):
        payload = msgpack_ser.serialize(array_dict)
        result = msgpack_ser.deserialize(payload)
        assert result == array_dict


# ---------------------------------------------------------------------------
# Tests: Payload is bytes and non-empty
# ---------------------------------------------------------------------------

class TestPayloadType:
    def test_json_returns_bytes(self, json_ser, flat_dict):
        payload = json_ser.serialize(flat_dict)
        assert isinstance(payload, bytes)
        assert len(payload) > 0

    def test_gzip_returns_bytes(self, gzip_ser, flat_dict):
        payload = gzip_ser.serialize(flat_dict)
        assert isinstance(payload, bytes)
        assert len(payload) > 0

    def test_msgpack_returns_bytes(self, msgpack_ser, flat_dict):
        payload = msgpack_ser.serialize(flat_dict)
        assert isinstance(payload, bytes)
        assert len(payload) > 0


# ---------------------------------------------------------------------------
# Tests: GZIP compression effectiveness
# ---------------------------------------------------------------------------

class TestGzipCompressionEffectiveness:
    def test_gzip_smaller_than_json_for_redundant_data(
        self, json_ser, gzip_ser, redundant_dict
    ):
        json_payload = json_ser.serialize(redundant_dict)
        gzip_payload = gzip_ser.serialize(redundant_dict)
        assert len(gzip_payload) < len(json_payload), (
            f"Expected GZIP payload ({len(gzip_payload)} bytes) to be smaller "
            f"than JSON payload ({len(json_payload)} bytes) for redundant data"
        )

    def test_gzip_compression_ratio(self, json_ser, gzip_ser, redundant_dict):
        json_payload = json_ser.serialize(redundant_dict)
        gzip_payload = gzip_ser.serialize(redundant_dict)
        compression_ratio = len(gzip_payload) / len(json_payload)
        # Should achieve at least 50% reduction on highly redundant data
        assert compression_ratio < 0.5, (
            f"Expected compression ratio < 0.5, got {compression_ratio:.3f}"
        )

    def test_gzip_compresslevel_effect(self, redundant_dict):
        low = GzipJSONSerializer(compresslevel=1)
        high = GzipJSONSerializer(compresslevel=9)
        payload_low = low.serialize(redundant_dict)
        payload_high = high.serialize(redundant_dict)
        # Higher compression level should produce smaller or equal payload
        assert len(payload_high) <= len(payload_low)


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_dict_json(self, json_ser):
        payload = json_ser.serialize({})
        result = json_ser.deserialize(payload)
        assert result == {}

    def test_empty_dict_gzip(self, gzip_ser):
        payload = gzip_ser.serialize({})
        result = gzip_ser.deserialize(payload)
        assert result == {}

    def test_empty_dict_msgpack(self, msgpack_ser):
        payload = msgpack_ser.serialize({})
        result = msgpack_ser.deserialize(payload)
        assert result == {}

    def test_json_none_raises(self, json_ser):
        with pytest.raises(ValueError):
            json_ser.serialize(None)

    def test_gzip_none_raises(self, gzip_ser):
        with pytest.raises(ValueError):
            gzip_ser.serialize(None)

    def test_msgpack_none_raises(self, msgpack_ser):
        with pytest.raises(ValueError):
            msgpack_ser.serialize(None)

    def test_json_empty_payload_raises(self, json_ser):
        with pytest.raises(ValueError):
            json_ser.deserialize(b"")

    def test_gzip_empty_payload_raises(self, gzip_ser):
        with pytest.raises(ValueError):
            gzip_ser.deserialize(b"")

    def test_msgpack_empty_payload_raises(self, msgpack_ser):
        with pytest.raises(ValueError):
            msgpack_ser.deserialize(b"")

    def test_gzip_invalid_compresslevel_low(self):
        with pytest.raises(ValueError):
            GzipJSONSerializer(compresslevel=0)

    def test_gzip_invalid_compresslevel_high(self):
        with pytest.raises(ValueError):
            GzipJSONSerializer(compresslevel=10)


# ---------------------------------------------------------------------------
# Tests: SerializerRegistry
# ---------------------------------------------------------------------------

class TestSerializerRegistry:
    def test_registry_lists_three_serializers(self):
        registry = SerializerRegistry()
        names = registry.list_serializers()
        assert "json" in names
        assert "json_gzip" in names
        assert "messagepack" in names
        assert len(names) == 3

    def test_registry_sorted(self):
        registry = SerializerRegistry()
        names = registry.list_serializers()
        assert names == sorted(names)

    def test_registry_get_json(self):
        registry = SerializerRegistry()
        s = registry.get("json")
        assert isinstance(s, JSONSerializer)

    def test_registry_get_gzip(self):
        registry = SerializerRegistry()
        s = registry.get("json_gzip")
        assert isinstance(s, GzipJSONSerializer)

    def test_registry_get_msgpack(self):
        registry = SerializerRegistry()
        s = registry.get("messagepack")
        assert isinstance(s, MessagePackSerializer)

    def test_registry_unknown_key_raises(self):
        registry = SerializerRegistry()
        with pytest.raises(KeyError):
            registry.get("unknown_format")

    def test_registry_register_invalid_type_raises(self):
        registry = SerializerRegistry()
        with pytest.raises(TypeError):
            registry.register("not_a_serializer")  # type: ignore

    def test_module_level_get_serializer(self):
        s = get_serializer("json")
        assert s.name == "json"

    def test_module_level_list_serializers(self):
        names = list_serializers()
        assert "json" in names
        assert "json_gzip" in names
        assert "messagepack" in names


# ---------------------------------------------------------------------------
# Tests: Cross-format payload sizes (informational)
# ---------------------------------------------------------------------------

class TestPayloadSizeComparison:
    """
    Validate relative payload size expectations based on benchmark study assumptions.
    MessagePack is expected to produce smaller payloads than JSON for typical data.
    """

    def test_msgpack_smaller_than_json_for_nested_data(
        self, json_ser, msgpack_ser, nested_dict
    ):
        json_payload = json_ser.serialize(nested_dict)
        mp_payload = msgpack_ser.serialize(nested_dict)
        # MessagePack should produce smaller payloads than JSON for typical dicts
        assert len(mp_payload) < len(json_payload), (
            f"Expected MessagePack ({len(mp_payload)} bytes) < JSON ({len(json_payload)} bytes)"
        )

    def test_all_formats_produce_non_empty_payload(self, all_serializers, nested_dict):
        for serializer in all_serializers:
            payload = serializer.serialize(nested_dict)
            assert len(payload) > 0, f"{serializer.name} produced empty payload"
