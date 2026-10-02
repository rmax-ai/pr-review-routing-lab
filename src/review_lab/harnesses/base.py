"""Reviewer harness interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import ReviewVerdict


class ReviewerHarness(ABC):
    lane: str = "offline"

    @abstractmethod
    def run(
        self,
        packet_dir: str | Path,
        model: str = "gpt-6-sol",
        effort: str = "low",
        timeout_s: float = 90,
    ) -> ReviewVerdict:
        raise NotImplementedError
