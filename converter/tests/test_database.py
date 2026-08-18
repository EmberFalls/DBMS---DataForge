import sqlite3
from pathlib import Path

from database.db_loader import load
from engine.normalization_engine import normalize
from engine.sql_generator import generate_ddl, generate_dml
from parsers.json_parser import JsonParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_loader_creates_and_populates_linked_tables(tmp_path):
    schema, table_data = normalize("students", JsonParser().parse(FIXTURES / "nested_orders.json"))
    db_path = tmp_path / "converted.db"
    load(schema, table_data, generate_ddl(schema), generate_dml(schema, table_data), db_path)
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM students_orders").fetchone()[0] == 3
