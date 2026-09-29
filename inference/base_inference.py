"""Base inference interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseInferenceEngine(ABC):
    status: Dict[str, Any]

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name for truthful UI and diagnostics."""
        raise NotImplementedError

    @abstractmethod
    def availability(self) -> Dict[str, Any]:
        """Return explicit runtime/artifact availability without raising."""
        raise NotImplementedError

    @abstractmethod
    def predict(self, image: Any) -> Dict[str, Any]:
        raise NotImplementedError
