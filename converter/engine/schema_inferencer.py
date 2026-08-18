"""Infer SQL-compatible schemas from a union of record keys."""

from datetime import date, datetime

from models.column_schema import ColumnSchema, SqlType
from models.table_schema import TableSchema

BOOL_STRINGS = {"true", "false", "yes", "no", "1", "0"}


def infer_table_schema(table_name: str, records: list[dict]) -> TableSchema:
    """Infer every scalar column from all records, never only the first one."""
    all_keys = {key for record in records for key in record}
    schema = TableSchema(name=table_name)

    for key in sorted(all_keys):
        values = [record[key] for record in records if key in record and record[key] not in (None, "")]
        if any(isinstance(value, list) for value in values):
            schema.add_column(ColumnSchema(f"__nested_array__{key}", SqlType.TEXT))
        elif any(isinstance(value, dict) for value in values):
            schema.add_column(ColumnSchema(f"__nested_object__{key}", SqlType.TEXT))
        else:
            schema.add_column(ColumnSchema(key, _resolve_type(values), nullable=len(values) < len(records)))

    _assign_primary_key(schema)
    return schema


def _resolve_type(values: list) -> SqlType:
    if not values:
        return SqlType.VARCHAR
    seen_types = {_scalar_type(value) for value in values}
    if seen_types == {SqlType.INTEGER}:
        return SqlType.INTEGER
    if seen_types <= {SqlType.INTEGER, SqlType.BIGINT}:
        return SqlType.BIGINT
    if seen_types <= {SqlType.INTEGER, SqlType.BIGINT, SqlType.DECIMAL}:
        return SqlType.DECIMAL
    if seen_types == {SqlType.BOOLEAN}:
        return SqlType.BOOLEAN
    if seen_types == {SqlType.TIMESTAMP}:
        return SqlType.TIMESTAMP
    return SqlType.VARCHAR


def _scalar_type(value) -> SqlType:
    if isinstance(value, bool):
        return SqlType.BOOLEAN
    if isinstance(value, int):
        return SqlType.INTEGER if -(2 ** 31) <= value <= (2 ** 31 - 1) else SqlType.BIGINT
    if isinstance(value, float):
        return SqlType.DECIMAL
    if isinstance(value, (date, datetime)):
        return SqlType.TIMESTAMP

    text = str(value).strip()
    if text.lower() in BOOL_STRINGS:
        return SqlType.BOOLEAN
    if _looks_like_int(text):
        integer = int(text)
        return SqlType.INTEGER if -(2 ** 31) <= integer <= (2 **31 - 1) else SqlType.BIGINT
    if _looks_like_float(text):
        return SqlType.DECIMAL
    if _looks_like_timestamp(text):
        return SqlType.TIMESTAMP
    return SqlType.VARCHAR


def _looks_like_int(text: str) -> bool:
    try:
        int(text)
        return True
    except ValueError:
        return False


def _looks_like_float(text: str) -> bool:
    try:
        float(text)
        return "." in text or "e" in text.lower()
    except ValueError:
        return False


def _looks_like_timestamp(text: str) -> bool:
    for pattern in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            datetime.strptime(text, pattern)
            return True
        except ValueError:
            continue
    return False


def _assign_primary_key(schema: TableSchema) -> None:
    expected_names = {
        f"{schema.name.rstrip('s')}_id".lower(),
        f"{schema.name}_id".lower(),
    }
    for index, column in enumerate(schema.columns):
        if column.name.lower() == "id" or column.name.lower() in expected_names:
            column.is_primary_key = True
            column.nullable = False
            if index:
                schema.columns.insert(0, schema.columns.pop(index))
            return
    schema.columns.insert(0, ColumnSchema(
        name=f"{schema.name}_id", sql_type=SqlType.INTEGER,
        nullable=False, is_primary_key=True,
    ))
