"""
JSON + GZIP compressed serialization format implementation.
"""

import gzip
import json
from typing import Any, Dict, Union
from src.serialization.base import BaseSerializer


class GzipJSONSerializer(BaseSerializer):
    """
    Compressed JSON serializer (JSON + GZIP).
    Encodes object to JSON bytes and compresses the result using GZIP.
    """

    def __init__(self, compresslevel: int = 6):
        """
        :param compresslevel: GZIP compression level (1-9, default 6).
        """
        if not (1 <= compresslevel <= 9):
            raise ValueError("Compresslevel must be between 1 and 9")
        self.compresslevel = compresslevel

    @property
    def name(self) -> str:
        return "json_gzip"

    def serialize(self, data: Union[Dict[str, Any], list]) -> bytes:
        """
        Serialize data to JSON bytes, then compress with GZIP.
        """
        if data is None:
            raise ValueError("Cannot serialize None")
        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        uncompressed_bytes = json_str.encode('utf-8')
        return gzip.compress(uncompressed_bytes, compresslevel=self.compresslevel)

    def deserialize(self, payload: bytes) -> Union[Dict[str, Any], list]:
        """
        Decompress GZIP payload and deserialize JSON into python object.
        """
        if not payload:
            raise ValueError("Cannot deserialize empty payload")
        try:
            decompressed_bytes = gzip.decompress(payload)
        except Exception as e:
            raise ValueError(f"Failed to decompress GZIP payload: {str(e)}") from e

        json_str = decompressed_bytes.decode('utf-8')
        return json.loads(json_str)
