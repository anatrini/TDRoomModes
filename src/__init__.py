"""
AcousticFEM v2 - Room Acoustics Finite Element Analysis

A modern Python implementation for analyzing room acoustics using FEM.
"""

__version__ = "2.0.0"
__author__ = "Your Name"
__license__ = "MIT"

# Import main classes for convenience
try:
    from .mesh.importer import MeshImporter, create_rectangular_room
    from .physics.decay import (
        AcousticRoom,
        sabine_t60,
        eyring_t60,
        modal_damping_ratio,
        schroeder_frequency
    )
except ImportError:
    # Allow import even if dependencies not installed
    pass

__all__ = [
    'MeshImporter',
    'create_rectangular_room',
    'AcousticRoom',
    'sabine_t60',
    'eyring_t60',
    'modal_damping_ratio',
    'schroeder_frequency',
]
