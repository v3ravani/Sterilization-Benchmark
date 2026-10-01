"""
Serialization package - exports all format handlers and the registry interface.
"""

from src.serialization.base import BaseSerializer
from src.serialization.json_serializer import JSONSerializer
from src.serialization.gzip_json import GzipJSONSerializer
from src.serialization.messagepack_serializer import MessagePackSerializer
from src.serialization.registry import (
    SerializerRegistry,
    get_serializer,
    list_serializers,
)

__all__ = [
    "BaseSerializer",
    "JSONSerializer",
    "GzipJSONSerializer",
    "MessagePackSerializer",
    "SerializerRegistry",
    "get_serializer",
    "list_serializers",
]
