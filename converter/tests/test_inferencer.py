from pathlib import Path

from engine.schema_inferencer import infer_table_schema
from models.column_schema import SqlType
from parsers.csv_parser import CsvParser
from parsers.json_parser import JsonParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_mixed_type_column_falls_back_to_varchar():
    schema = infer_table_schema("t", CsvParser().parse(FIXTURES / "mixed_types.csv"))
    assert next(column for column in schema.columns if column.name == "age").sql_type == SqlType.VARCHAR


def test_union_scan_catches_key_present_in_only_one_record():
    schema = infer_table_schema("t", JsonParser().parse(FIXTURES / "heterogeneous_keys.json"))
    email = next(column for column in schema.columns if column.name == "email")
    assert email.nullable is True


def test_surrogate_primary_key_generated_when_missing():
    schema = infer_table_schema("people", CsvParser().parse(FIXTURES / "no_primary_key.csv"))
    assert schema.get_primary_key().name == "people_id"
