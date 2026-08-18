"""SQLite and MySQL database loaders."""

import sqlite3
from pathlib import Path


def load(schema, table_data: dict, ddl_statements: list[str], dml: dict,
         db_path: str | Path = "output.db") -> None:
    """Create the schema and insert all records atomically into SQLite."""
    del schema, table_data  # The generated statements are the loader's DB-API boundary.
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.cursor()
        for statement in ddl_statements:
            cursor.execute(statement)
        for insert_sql, value_tuples in dml.values():
            cursor.executemany(insert_sql, value_tuples)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def load_mysql(ddl_statements: list[str], dml: dict, *, host: str, port: int,
               user: str, password: str, database: str) -> None:
    """Create *database* if needed, then create tables and insert rows into MySQL."""
    try:
        import mysql.connector
    except ImportError as error:
        raise RuntimeError(
            "MySQL support is not installed. Run: python -m pip install -r requirements.txt"
        ) from error

    database_identifier = _quote_mysql_identifier(database)
    server_connection = mysql.connector.connect(
        host=host, port=port, user=user, password=password,
    )
    try:
        cursor = server_connection.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database_identifier}")
    finally:
        server_connection.close()

    connection = mysql.connector.connect(
        host=host, port=port, user=user, password=password, database=database,
    )
    try:
        cursor = connection.cursor()
        for statement in ddl_statements:
            cursor.execute(statement)
        for insert_sql, value_tuples in dml.values():
            cursor.executemany(insert_sql, value_tuples)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _quote_mysql_identifier(name: str) -> str:
    return f"`{name.replace('`', '``')}`"
