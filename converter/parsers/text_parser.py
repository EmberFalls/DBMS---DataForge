"""Key-value text input parser."""

import json
import re
from pathlib import Path

from parsers.base import DataParser

LINE_PATTERN = re.compile(r"^\s*(?P<key>[\w\s]+?)\s*[:=]\s*(?P<value>.*?)\s*$")
RECORD_SEPARATOR = re.compile(r"^\s*---+\s*$")


class TextParser(DataParser):
    def parse(self, file_path: Path) -> list[dict]:
        records: list[dict] = []
        current: dict = {}
        with file_path.open("r", encoding="utf-8") as input_file:
            for raw_line in input_file:
                line = raw_line.rstrip("\n")
                if not line.strip() or RECORD_SEPARATOR.match(line):
                    if current:
                        records.append(current)
                        current = {}
                    continue
                match = LINE_PATTERN.match(line)
                if match:
                    current[match.group("key").strip()] = self._try_json_decode(
                        match.group("value").strip()
                    )
        if current:
            records.append(current)
        return records

    @staticmethod
    def _try_json_decode(value: str):
        if value.startswith(("[", "{")):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return value
