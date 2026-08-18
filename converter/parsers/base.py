"""Common parser contract."""

from abc import ABC, abstractmethod
from pathlib import Path


class DataParser(ABC):
    """Convert one input file into records without normalizing them."""

    @abstractmethod
    def parse(self, file_path: Path) -> list[dict]:
        """Return flat or nested dictionary records from *file_path*."""
        raise NotImplementedError
