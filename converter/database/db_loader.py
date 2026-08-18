"""SQLite database loader."""

import sqlite3
from pathlib import Path


def load(schema, table_data: dict, ddl_statements: list[str], dml: dict,
         db_path: str | Path = "output.db") -> None:
    """Create the schema and insert all records atomically into SQLite."""
    del schema, table_data  # The generated statements are the loader's DB-API boundary.
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.cursor()
        for statement in ddl_statements:
            cursor.execute(statement)
        for insert_sql, value_tuples in dml.values():
            cursor.executemany(insert_sql, value_tuples)
