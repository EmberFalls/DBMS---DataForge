from pathlib import Path

from engine.normalization_engine import normalize
from engine.sql_generator import generate_ddl, generate_dml
from parsers.csv_parser import CsvParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_reserved_words_are_quoted_in_ddl():
    schema, _ = normalize("t", CsvParser().parse(FIXTURES / "reserved_words.csv"))
    combined = "\n".join(generate_ddl(schema))
    assert '"order"' in combined
    assert '"group"' in combined


def test_generated_dml_includes_values_for_surrogate_primary_key():
    schema, table_data = normalize("people", CsvParser().parse(FIXTURES / "no_primary_key.csv"))
    _, values = generate_dml(schema, table_data)["people"]
    assert values[0][0] == 1
