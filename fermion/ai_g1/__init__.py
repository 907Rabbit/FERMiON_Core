"""AI-G1: an isolated, trainable spectral-field research track.

This package deliberately does not import or alter the frozen 193-parameter
FERMiON-HR reference specimen.  Its Gaussian oracle and neural components are
separate experimental artifacts.
"""

from .spectral import GaussianSpectralOracle, LearnableSpectralField, SpectralFieldOutput
from .core import (
    MLPBaseline,
    MultimodalSpectralGeneralist,
    ReplayBuffer,
    TransformerBaseline,
)

__all__ = [
    "GaussianSpectralOracle",
    "LearnableSpectralField",
    "SpectralFieldOutput",
    "MLPBaseline",
    "MultimodalSpectralGeneralist",
    "ReplayBuffer",
    "TransformerBaseline",
]
