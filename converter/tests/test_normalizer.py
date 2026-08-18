from pathlib import Path

from engine.normalization_engine import normalize
from parsers.json_parser import JsonParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_nested_array_creates_child_table_with_foreign_key():
    schema, table_data = normalize("students", JsonParser().parse(FIXTURES / "nested_orders.json"))
    assert {"students", "students_orders"} <= schema.tables.keys()
    child_table = schema.tables["students_orders"]
    foreign_keys = [column for column in child_table.columns if column.is_foreign_key]
    assert len(foreign_keys) == 1
    assert foreign_keys[0].name == "students_id"
    assert foreign_keys[0].references == "students(id)"
    assert len(table_data["students_orders"]) == 3


def test_missing_key_gets_populated_and_links_child_rows():
    schema, table_data = normalize("people", [{"name": "Rohan", "phones": [{"number": "1"}]}])
    assert table_data["people"][0]["people_id"] == 1
    assert table_data["people_phones"][0]["people_id"] == 1
    assert schema.tables["people_phones"].get_primary_key().name == "people_phones_id"
