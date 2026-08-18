from pathlib import Path

from parsers.csv_parser import CsvParser
from parsers.json_parser import JsonParser
from parsers.text_parser import TextParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_csv_parser_reads_rows_as_dicts():
    records = CsvParser().parse(FIXTURES / "mixed_types.csv")
    assert records == [{"id": "1", "age": "25"}, {"id": "2", "age": "thirty"}]


def test_json_parser_returns_list_of_dicts():
    records = JsonParser().parse(FIXTURES / "heterogeneous_keys.json")
    assert len(records) == 2
    assert records[1]["email"] == "anita@example.com"


def test_text_parser_separates_records_and_decodes_arrays():
    records = TextParser().parse(FIXTURES / "key_value_records.txt")
    assert records == [
        {"name": "Rohan", "active": "true"},
        {"name": "Anita", "tags": ["mentor", "speaker"]},
    ]
