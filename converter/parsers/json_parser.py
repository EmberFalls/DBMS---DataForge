"""JSON input parser."""

import json
from pathlib import Path

from parsers.base import DataParser


class JsonParser(DataParser):
    def parse(self, file_path: Path) -> list[dict]:
        with file_path.open("r", encoding="utf-8") as input_file:
            data = json.load(input_file)

        if isinstance(data, dict):
            return [data]
        if isinstance(data, list) and all(isinstance(record, dict) for record in data):
            return data
        raise ValueError("JSON input must be an object or an array of objects")
