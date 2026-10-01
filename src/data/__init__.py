"""
Data generation, workload configuration, and data validation modules.
"""

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

__all__ = [
    # Generator
    "generate",
    "generate_flat_data",
    "generate_nested_data",
    "generate_text_heavy_data",
    "generate_numeric_data",
    "GENERATOR_MAP",
    # Workloads
    "Workload",
    "SizeTarget",
    "RedundancyLevel",
    "DataStructure",
    "WORKLOADS",
    "get_workload",
    "list_workload_names",
    "get_workloads_by_structure",
    "get_workloads_by_size",
    # Validator
    "ValidationResult",
    "validate",
    "assert_valid",
]
