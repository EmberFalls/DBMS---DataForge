"""CSV and TSV input parser."""

import csv
import json
from pathlib import Path

from parsers.base import DataParser


class CsvParser(DataParser):
    def parse(self, file_path: Path) -> list[dict]:
        delimiter = "\t" if file_path.suffix.lower() == ".tsv" else ","
        with file_path.open("r", encoding="utf-8-sig", newline="") as input_file:
            reader = csv.DictReader(input_file, delimiter=delimiter)
            return [self._decode_nested_cells(row) for row in reader]

    @classmethod
    def _decode_nested_cells(cls, row: dict) -> dict:
        return {key: cls._try_json_decode(value) for key, value in row.items()}

    @staticmethod
    def _try_json_decode(value):
        if value is None or not isinstance(value, str):
            return value
        stripped = value.strip()
        if stripped.startswith(("[", "{")):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
        return value
