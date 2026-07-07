"""Contract-style train-only strategy lab for v9."""

from .schema import ContractCandidate
from .simulator import simulate_candidate

__all__ = ["ContractCandidate", "simulate_candidate"]
