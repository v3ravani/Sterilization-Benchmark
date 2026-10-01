"""
Abstract base class definition for serialization handlers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Union


class BaseSerializer(ABC):
    """
    Abstract interface for all serialization format handlers.
    Every serializer implementation must inherit from BaseSerializer and enforce
    the serialize/deserialize contract.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier name of the serialization format.
        """
        pass

    @abstractmethod
    def serialize(self, data: Union[Dict[str, Any], list]) -> bytes:
        """
        Convert python dictionary or list object into serialized bytes.

        :param data: Python data structure to serialize.
        :return: Serialized byte string.
        """
        pass

    @abstractmethod
    def deserialize(self, payload: bytes) -> Union[Dict[str, Any], list]:
        """
        Convert serialized bytes back into python dictionary or list object.

        :param payload: Byte sequence to deserialize.
        :return: Reconstructed python data structure.
        """
        pass
