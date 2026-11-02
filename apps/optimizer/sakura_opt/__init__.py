"""Cœur de Sakura Optimizer, bientôt exposé comme outils pour Sakura AI."""

from .sensors import Sampler

__version__ = "0.1.0"

_sampler: Sampler | None = None


def get_status():
    """Outil de mesures partagé, exposé plus tard à Sakura AI."""
    global _sampler
    if _sampler is None:
        _sampler = Sampler()
    return _sampler.sample()
