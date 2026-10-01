"""
JSON serialization format implementation.
"""

import json
from typing import Any, Dict, Union
from src.serialization.base import BaseSerializer


class JSONSerializer(BaseSerializer):
    """
    Standard uncompressed JSON serializer baseline.
    Converts application objects to UTF-8 encoded JSON bytes.
    """

    @property
    def name(self) -> str:
        return "json"

    def serialize(self, data: Union[Dict[str, Any], list]) -> bytes:
        """
        Serialize python dict or list into UTF-8 encoded JSON bytes.
        """
        if data is None:
            raise ValueError("Cannot serialize None")
        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        return json_str.encode('utf-8')

    def deserialize(self, payload: bytes) -> Union[Dict[str, Any], list]:
        """
        Deserialize UTF-8 encoded JSON bytes into python object.
        """
        if not payload:
            raise ValueError("Cannot deserialize empty payload")
        json_str = payload.decode('utf-8')
        return json.loads(json_str)
