"""MySQL database loader."""


def load_mysql(ddl_statements: list[str], dml: dict, *, host: str, port: int,
               user: str, password: str, database: str) -> None:
    """Create tables and insert rows into an existing MySQL database."""
    try:
        import mysql.connector
    except ImportError as error:
        raise RuntimeError(
            "MySQL support is not installed. Run: python -m pip install -r requirements.txt"
        ) from error

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
