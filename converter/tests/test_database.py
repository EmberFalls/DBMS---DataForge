from pathlib import Path

from engine.normalization_engine import normalize
from engine.sql_generator import generate_ddl, generate_dml
from parsers.json_parser import JsonParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_mysql_statements_create_and_populate_linked_tables():
    schema, table_data = normalize("students", JsonParser().parse(FIXTURES / "nested_orders.json"))
    ddl = "\n".join(generate_ddl(schema))
    dml = generate_dml(schema, table_data)
    assert "CREATE TABLE students" in ddl
    assert "CREATE TABLE students_orders" in ddl
    assert "FOREIGN KEY (students_id) REFERENCES students(id)" in ddl
    assert len(dml["students"][1]) == 2
    assert len(dml["students_orders"][1]) == 3
