"""Generate SQLite-compatible DDL and parameterized DML."""

RESERVED_WORDS = {
    "order", "group", "user", "select", "table", "key", "index", "from", "where",
}


def quote_identifier(name: str) -> str:
    """Safely quote reserved words and unusual SQL identifiers."""
    if name.lower() in RESERVED_WORDS or not name.replace("_", "").isalnum() or name[:1].isdigit():
        return f'"{name.replace(chr(34), chr(34) * 2)}"'
    return name


def generate_ddl(schema) -> list[str]:
    statements = []
    for table in schema.tables.values():
        definitions = []
        for column in table.columns:
            parts = [quote_identifier(column.name), column.sql_type.value]
            if column.is_primary_key:
                parts.append("PRIMARY KEY")
            elif not column.nullable:
                parts.append("NOT NULL")
            definitions.append(" ".join(parts))
        for column in table.columns:
            if column.is_foreign_key and column.references:
                definitions.append(
                    f"FOREIGN KEY ({quote_identifier(column.name)}) REFERENCES {_quote_reference(column.references)}"
                )
        statements.append(
            f"CREATE TABLE {quote_identifier(table.name)} (\n  " + ",\n  ".join(definitions) + "\n);"
        )
    return statements


def generate_dml(schema, table_data: dict[str, list[dict]]) -> dict[str, tuple[str, list[tuple]]]:
    result = {}
    for table_name, rows in table_data.items():
        table = schema.get_table(table_name)
        if table is None or not rows:
            continue
        names = [column.name for column in table.columns]
        columns = ", ".join(quote_identifier(name) for name in names)
        placeholders = ", ".join("?" for _ in names)
        statement = f"INSERT INTO {quote_identifier(table_name)} ({columns}) VALUES ({placeholders})"
        result[table_name] = (statement, [tuple(row.get(name) for name in names) for row in rows])
    return result


def _quote_reference(reference: str) -> str:
    table_name, separator, column_name = reference.partition("(")
    if not separator or not column_name.endswith(")"):
        return reference
    return f"{quote_identifier(table_name)}({quote_identifier(column_name[:-1])})"
