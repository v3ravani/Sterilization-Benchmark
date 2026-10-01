"""
MessagePack binary serialization format implementation.
"""

from typing import Any, Dict, Union
import msgpack
from src.serialization.base import BaseSerializer


class MessagePackSerializer(BaseSerializer):
    """
    MessagePack binary format serializer.
    Converts application objects to compact MessagePack binary representation.
    """

    @property
    def name(self) -> str:
        return "messagepack"

    def serialize(self, data: Union[Dict[str, Any], list]) -> bytes:
        """
        Serialize python dict or list into MessagePack binary bytes.
        """
        if data is None:
            raise ValueError("Cannot serialize None")
        return msgpack.packb(data, use_bin_type=True)

    def deserialize(self, payload: bytes) -> Union[Dict[str, Any], list]:
        """
        Deserialize MessagePack binary bytes into python object.
        """
        if not payload:
            raise ValueError("Cannot deserialize empty payload")
        try:
            return msgpack.unpackb(payload, raw=False)
        except Exception as e:
            raise ValueError(f"Failed to deserialize MessagePack payload: {str(e)}") from e
