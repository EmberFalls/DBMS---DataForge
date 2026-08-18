"""Convert nested records into first-normal-form tables."""

from engine.schema_inferencer import infer_table_schema
from models.column_schema import ColumnSchema, SqlType
from models.relational_schema import RelationalSchema
from models.table_schema import TableSchema


def normalize(table_name: str, records: list[dict]) -> tuple[RelationalSchema, dict[str, list[dict]]]:
    """Flatten nested objects and move nested arrays to child tables."""
    initial_schema = infer_table_schema(table_name, records)
    array_fields = [column.name.removeprefix("__nested_array__") for column in initial_schema.columns
                    if column.name.startswith("__nested_array__")]
    object_fields = [column.name.removeprefix("__nested_object__") for column in initial_schema.columns
                     if column.name.startswith("__nested_object__")]
    initial_pk = initial_schema.get_primary_key()
    assert initial_pk is not None

    table_data: dict[str, list[dict]] = {table_name: []}
    uses_surrogate_key = all(initial_pk.name not in record for record in records)
    for row_number, record in enumerate(records, start=1):
        flat_record = dict(record)
        if uses_surrogate_key:
            flat_record[initial_pk.name] = row_number

        for field_name in object_fields:
            nested = flat_record.pop(field_name, None)
            if isinstance(nested, dict):
                for key, value in nested.items():
                    flat_record[f"{field_name}_{key}"] = value

        for field_name in array_fields:
            items = flat_record.pop(field_name, None) or []
            if not isinstance(items, list):
                items = [items]
            child_name = f"{table_name}_{field_name}"
            foreign_key_name = _foreign_key_name(table_name, initial_pk.name)
            child_rows = table_data.setdefault(child_name, [])
            for item in items:
                child_row = dict(item) if isinstance(item, dict) else {"value": item}
                child_row[foreign_key_name] = flat_record.get(initial_pk.name)
                child_rows.append(child_row)
        table_data[table_name].append(flat_record)

    schema = RelationalSchema()
    parent_schema = infer_table_schema(table_name, table_data[table_name])
    schema.add_table(parent_schema)
    parent_pk = parent_schema.get_primary_key()
    assert parent_pk is not None

    for field_name in array_fields:
        child_name = f"{table_name}_{field_name}"
        child_rows = table_data.get(child_name, [])
        if not child_rows:
            continue
        child_schema = infer_table_schema(child_name, child_rows)
        child_pk = child_schema.get_primary_key()
        assert child_pk is not None
        if all(child_pk.name not in row for row in child_rows):
            for row_number, row in enumerate(child_rows, start=1):
                row[child_pk.name] = row_number
        _add_or_mark_foreign_key(
            child_schema, _foreign_key_name(table_name, parent_pk.name), parent_pk, table_name
        )
        schema.add_table(child_schema)
    return schema, table_data


def _foreign_key_name(parent_name: str, parent_key_name: str) -> str:
    return parent_key_name if parent_key_name.startswith(f"{parent_name}_") else f"{parent_name}_{parent_key_name}"


def _add_or_mark_foreign_key(child_schema: TableSchema, foreign_key_name: str,
                             parent_pk: ColumnSchema, parent_name: str) -> None:
    reference = f"{parent_name}({parent_pk.name})"
    existing = next((column for column in child_schema.columns if column.name == foreign_key_name), None)
    if existing is not None:
        existing.sql_type = parent_pk.sql_type
        existing.nullable = False
        existing.is_foreign_key = True
        existing.references = reference
        return
    child_schema.add_column(ColumnSchema(
        name=foreign_key_name, sql_type=parent_pk.sql_type, nullable=False,
        is_foreign_key=True, references=reference,
    ))
