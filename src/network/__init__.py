"""
Network simulation profiles and Windows network controller modules.
"""

from src.network.profiles import (
    NetworkProfile,
    PROFILES,
    FAST,
    MODERATE,
    SLOW,
    VERY_SLOW,
    PROFILE_ORDER,
    get_profile,
    list_profiles,
)
from src.network.controller import (
    NetworkController,
    SimulationOverhead,
    get_controller,
)

__all__ = [
    # Profiles
    "NetworkProfile",
    "PROFILES",
    "FAST",
    "MODERATE",
    "SLOW",
    "VERY_SLOW",
    "PROFILE_ORDER",
    "get_profile",
    "list_profiles",
    # Controller
    "NetworkController",
    "SimulationOverhead",
    "get_controller",
]
