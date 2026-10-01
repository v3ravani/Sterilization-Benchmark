"""
Serializer registry - factory pattern for managing all format handlers.
"""

from typing import Dict, List
from src.serialization.base import BaseSerializer
from src.serialization.json_serializer import JSONSerializer
from src.serialization.gzip_json import GzipJSONSerializer
from src.serialization.messagepack_serializer import MessagePackSerializer


class SerializerRegistry:
    """
    Factory registry for dynamically looking up and instantiating serializers.
    All three baseline formats are pre-registered on init.
    """

    def __init__(self):
        self._registry: Dict[str, BaseSerializer] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the three core benchmark serializers."""
        self.register(JSONSerializer())
        self.register(GzipJSONSerializer())
        self.register(MessagePackSerializer())

    def register(self, serializer: BaseSerializer) -> None:
        """
        Register a serializer instance.

        :param serializer: Instance of BaseSerializer to register.
        :raises TypeError: If serializer does not inherit from BaseSerializer.
        """
        if not isinstance(serializer, BaseSerializer):
            raise TypeError(
                f"serializer must be a subclass of BaseSerializer, got {type(serializer).__name__}"
            )
        self._registry[serializer.name] = serializer

    def get(self, name: str) -> BaseSerializer:
        """
        Retrieve a serializer by name.

        :param name: Serializer identifier (e.g. 'json', 'json_gzip', 'messagepack').
        :raises KeyError: If no serializer with the given name is registered.
        :return: BaseSerializer instance.
        """
        if name not in self._registry:
            available = self.list_serializers()
            raise KeyError(
                f"No serializer registered with name '{name}'. "
                f"Available serializers: {available}"
            )
        return self._registry[name]

    def list_serializers(self) -> List[str]:
        """
        Return a list of all registered serializer names.

        :return: Sorted list of serializer name strings.
        """
        return sorted(self._registry.keys())

    def __repr__(self) -> str:
        return f"SerializerRegistry(registered={self.list_serializers()})"


# Module-level default registry instance
_default_registry = SerializerRegistry()


def get_serializer(name: str) -> BaseSerializer:
    """
    Convenience function to retrieve a serializer from the default registry.

    :param name: Serializer identifier.
    :return: BaseSerializer instance.
    """
    return _default_registry.get(name)


def list_serializers() -> List[str]:
    """
    Convenience function to list all registered serializers.

    :return: Sorted list of serializer name strings.
    """
    return _default_registry.list_serializers()
