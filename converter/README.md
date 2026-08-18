# Multi-Format to SQL Converter — Implementation Guide

This document is a build spec. It describes exactly what to build, in what order, using what
libraries, and how to test it. It is written so that a teammate (or an LLM) can pick up any
single section and implement it without needing the rest of the conversation history.

**Guiding constraint: minimal external libraries.** Prefer Python's standard library
everywhere possible. Only reach for a third-party package when the standard library
genuinely cannot do the job (Excel reading is the one unavoidable case).

---

## 1. Project Setup

```bash
mkdir converter && cd converter
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install openpyxl pytest
pip freeze > requirements.txt
```

That's it — two third-party packages total:
- `openpyxl` — required, no standard-library way to read `.xlsx` files
- `pytest` — required for the testing strategy in Section 6 (optional if you prefer `unittest`,
  which is in the standard library, but `pytest` is worth the one extra dependency)

Everything else (`csv`, `json`, `re`, `sqlite3`, `dataclasses`, `argparse`, `pathlib`) is
built into Python 3.11+ and needs no installation.

---

## 2. File Structure

Create this exact folder layout before writing any logic. Every file listed here should exist
(even empty, with just a docstring) before implementation starts — it forces the interfaces to
be agreed on first.

```
converter/
├── main.py                        # CLI entry point
├── requirements.txt
├── parsers/
│   ├── __init__.py
│   ├── base.py                    # DataParser abstract base class
│   ├── csv_parser.py              # csv module
│   ├── excel_parser.py            # openpyxl
│   ├── text_parser.py             # re (regex key-value parser)
│   └── json_parser.py             # json module
├── models/
│   ├── __init__.py
│   ├── column_schema.py           # dataclass: one column's metadata
│   ├── table_schema.py            # dataclass: one table's metadata
│   └── relational_schema.py       # full schema graph (all tables)
├── engine/
│   ├── __init__.py
│   ├── schema_inferencer.py       # union scan + type detection
│   ├── normalization_engine.py    # 1NF flattening & array decomposition
│   └── sql_generator.py           # DDL + DML text generation
├── database/
│   ├── __init__.py
│   └── db_loader.py               # sqlite3 / DB-API batch executor
└── tests/
    ├── __init__.py
    ├── fixtures/                  # sample input files used by tests (Section 6)
    ├── test_parsers.py
    ├── test_inferencer.py
    ├── test_normalizer.py
    └── test_sql_generator.py
```

---

## 3. Parsers — the contract every format must follow

### 3.1 `parsers/base.py`

Every parser implements this. Nothing downstream of the parser layer should ever import
`csv`, `openpyxl`, or format-specific logic directly — it should only ever see `list[dict]`.

```python
from abc import ABC, abstractmethod
from pathlib import Path


class DataParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path) -> list[dict]:
        # Return a list of records. Each record is a flat or nested dict.
        # Nested dicts/lists inside a record represent 1:1 / 1:N relationships
        # that the normalizer will process later — parsers should NOT flatten
        # or split anything themselves.
        raise NotImplementedError
```

**Rule for the team:** if you're implementing a new parser and find yourself writing
normalization logic (splitting arrays, flattening nested keys) inside the parser file,
stop — that belongs in `engine/normalization_engine.py`, not here. Parsers only convert
"file on disk" into "list of Python dicts." Nothing more.

### 3.2 `parsers/json_parser.py` — build this one first

The simplest parser. JSON already matches the target shape.

```python
import json
from pathlib import Path
from parsers.base import DataParser


class JsonParser(DataParser):
    def parse(self, file_path: Path) -> list[dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Support both a top-level array of objects, and a single object
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]

        raise ValueError(f"Unsupported JSON root type: {type(data)}")
```

### 3.3 `parsers/csv_parser.py`

Uses the built-in `csv` module. Two responsibilities: (1) turn rows into dicts,
(2) detect cells that actually contain embedded JSON and decode them.

```python
import csv
import json
from pathlib import Path
from parsers.base import DataParser


class CsvParser(DataParser):
    def parse(self, file_path: Path) -> list[dict]:
        records = []
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(self._decode_nested_cells(row))
        return records

    def _decode_nested_cells(self, row: dict) -> dict:
        decoded = {}
        for key, value in row.items():
            decoded[key] = self._try_json_decode(value)
        return decoded

    @staticmethod
    def _try_json_decode(value: str):
        if value is None:
            return None
        stripped = value.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value  # looked like JSON but wasn't — keep as plain text
        return value
```

### 3.4 `parsers/excel_parser.py`

Uses `openpyxl`. One sheet = one entity/table. Use `data_only=True` so formula cells
return their last computed value, not the formula text.

```python
from pathlib import Path
from openpyxl import load_workbook
from parsers.base import DataParser
from parsers.csv_parser import CsvParser  # reuse its nested-cell decoder


class ExcelParser(DataParser):
    def parse(self, file_path: Path) -> list[dict]:
        # NOTE: this returns records from the FIRST sheet only.
        # If your input files have multiple meaningful sheets, call
        # parse_all_sheets() instead and handle each sheet as a separate table.
        workbook = load_workbook(file_path, data_only=True)
        sheet = workbook[workbook.sheetnames[0]]
        return self._sheet_to_records(sheet)

    def parse_all_sheets(self, file_path: Path) -> dict[str, list[dict]]:
        workbook = load_workbook(file_path, data_only=True)
        return {
            name: self._sheet_to_records(workbook[name])
            for name in workbook.sheetnames
        }

    def _sheet_to_records(self, sheet) -> list[dict]:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []

        headers = [str(h).strip() if h is not None else f"col_{i}"
                   for i, h in enumerate(rows[0])]

        records = []
        for row in rows[1:]:
            if all(cell is None for cell in row):
                continue  # skip fully blank rows
            record = dict(zip(headers, row))
            records.append(self._decode_nested_cells(record))
        return records

    @staticmethod
    def _decode_nested_cells(record: dict) -> dict:
        decoded = {}
        for key, value in record.items():
            if isinstance(value, str):
                decoded[key] = CsvParser._try_json_decode(value)
            else:
                decoded[key] = value  # already a native type (int, float, datetime)
        return decoded
```

### 3.5 `parsers/text_parser.py`

Uses `re` to extract `key: value` or `key = value` lines. This is the least
standardized format — expect to tune the regex per real input file.

```python
import re
import json
from pathlib import Path
from parsers.base import DataParser

LINE_PATTERN = re.compile(r'^\s*(?P<key>[\w\s]+?)\s*[:=]\s*(?P<value>.*?)\s*$')
RECORD_SEPARATOR = re.compile(r'^\s*---+\s*$')  # blank/dashed line ends a record


class TextParser(DataParser):
    def parse(self, file_path: Path) -> list[dict]:
        records = []
        current: dict = {}

        with open(file_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.rstrip("\n")

                if not line.strip() or RECORD_SEPARATOR.match(line):
                    if current:
                        records.append(current)
                        current = {}
                    continue

                match = LINE_PATTERN.match(line)
                if match:
                    key = match.group("key").strip()
                    value = self._try_json_decode(match.group("value").strip())
                    current[key] = value

        if current:
            records.append(current)
        return records

    @staticmethod
    def _try_json_decode(value: str):
        if value.startswith("[") or value.startswith("{"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
```

### 3.6 Parser selection (in `main.py`)

```python
from pathlib import Path
from parsers.csv_parser import CsvParser
from parsers.excel_parser import ExcelParser
from parsers.text_parser import TextParser
from parsers.json_parser import JsonParser

PARSER_BY_EXTENSION = {
    ".csv": CsvParser,
    ".tsv": CsvParser,
    ".xlsx": ExcelParser,
    ".txt": TextParser,
    ".json": JsonParser,
}


def get_parser(file_path: Path):
    ext = file_path.suffix.lower()
    parser_cls = PARSER_BY_EXTENSION.get(ext)
    if parser_cls is None:
        raise ValueError(f"No parser registered for extension: {ext}")
    return parser_cls()
```

---

## 4. Models — schema metadata containers (no data, just structure)

### 4.1 `models/column_schema.py`

```python
from dataclasses import dataclass
from enum import Enum


class SqlType(Enum):
    INTEGER = "INTEGER"
    BIGINT = "BIGINT"
    DECIMAL = "DECIMAL(12,4)"
    BOOLEAN = "BOOLEAN"
    TIMESTAMP = "TIMESTAMP"
    VARCHAR = "VARCHAR(255)"
    TEXT = "TEXT"


@dataclass
class ColumnSchema:
    name: str
    sql_type: SqlType
    nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: str | None = None  # e.g. "students(id)" if is_foreign_key
```

### 4.2 `models/table_schema.py`

```python
from dataclasses import dataclass, field
from models.column_schema import ColumnSchema


@dataclass
class TableSchema:
    name: str
    columns: list[ColumnSchema] = field(default_factory=list)

    def add_column(self, column: ColumnSchema):
        self.columns.append(column)

    def get_primary_key(self) -> ColumnSchema | None:
        return next((c for c in self.columns if c.is_primary_key), None)
```

### 4.3 `models/relational_schema.py`

```python
from dataclasses import dataclass, field
from models.table_schema import TableSchema


@dataclass
class RelationalSchema:
    tables: dict[str, TableSchema] = field(default_factory=dict)

    def add_table(self, table: TableSchema):
        self.tables[table.name] = table

    def get_table(self, name: str) -> TableSchema | None:
        return self.tables.get(name)
```

---

## 5. Engine — inference, normalization, SQL generation

### 5.1 `engine/schema_inferencer.py` — the union scan

This is the "matching keys" logic. Do NOT infer types from a single record — always
scan the full dataset first.

```python
from datetime import datetime
from models.column_schema import ColumnSchema, SqlType

ISO_TIMESTAMP_RE = None  # see note below; use re for date detection

BOOL_STRINGS = {"true", "false", "yes", "no", "1", "0"}


def infer_table_schema(table_name: str, records: list[dict]) -> "TableSchema":
    from models.table_schema import TableSchema

    # Step 1: union every key seen across ALL records
    all_keys: set[str] = set()
    for record in records:
        all_keys.update(record.keys())

    schema = TableSchema(name=table_name)

    for key in sorted(all_keys):
        values = [r.get(key) for r in records if key in r and r.get(key) not in (None, "")]

        # Nested list -> flag for the normalizer, not a scalar column
        if any(isinstance(v, list) for v in values):
            schema.add_column(ColumnSchema(name=f"__nested_array__{key}", sql_type=SqlType.TEXT))
            continue

        # Nested dict -> flag for flattening
        if any(isinstance(v, dict) for v in values):
            schema.add_column(ColumnSchema(name=f"__nested_object__{key}", sql_type=SqlType.TEXT))
            continue

        resolved_type = _resolve_type(values)
        is_nullable = len(values) < len(records)
        schema.add_column(ColumnSchema(name=key, sql_type=resolved_type, nullable=is_nullable))

    _assign_primary_key(schema)
    return schema


def _resolve_type(values: list) -> SqlType:
    if not values:
        return SqlType.VARCHAR

    seen_types = {_scalar_type(v) for v in values}

    if seen_types == {SqlType.INTEGER}:
        return SqlType.INTEGER
    if seen_types <= {SqlType.INTEGER, SqlType.BIGINT}:
        return SqlType.BIGINT
    if seen_types <= {SqlType.INTEGER, SqlType.DECIMAL, SqlType.BIGINT}:
        return SqlType.DECIMAL
    if seen_types == {SqlType.BOOLEAN}:
        return SqlType.BOOLEAN
    if seen_types == {SqlType.TIMESTAMP}:
        return SqlType.TIMESTAMP

    # Any mismatch (e.g. int + arbitrary string) -> fall back to text
    return SqlType.VARCHAR


def _scalar_type(value) -> SqlType:
    if isinstance(value, bool):
        return SqlType.BOOLEAN
    if isinstance(value, int):
        return SqlType.INTEGER if -2**31 <= value <= 2**31 - 1 else SqlType.BIGINT
    if isinstance(value, float):
        return SqlType.DECIMAL

    text = str(value).strip()
    if text.lower() in BOOL_STRINGS:
        return SqlType.BOOLEAN
    if _looks_like_int(text):
        n = int(text)
        return SqlType.INTEGER if -2**31 <= n <= 2**31 - 1 else SqlType.BIGINT
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
        return "." in text
    except ValueError:
        return False


def _looks_like_timestamp(text: str) -> bool:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def _assign_primary_key(schema) -> None:
    # Prefer a column literally named "id" or "<table>_id"; else synthesize one.
    for col in schema.columns:
        if col.name.lower() in ("id", f"{schema.name.rstrip('s')}_id"):
            col.is_primary_key = True
            col.nullable = False
            return

    from models.column_schema import ColumnSchema as CS
    surrogate = CS(name=f"{schema.name}_id", sql_type=SqlType.INTEGER,
                    nullable=False, is_primary_key=True)
    schema.columns.insert(0, surrogate)
```

**Reserved-keyword handling:** add a `RESERVED_WORDS` set (`order`, `group`, `select`,
`table`, `user`, ...) and, when generating SQL later, wrap any column/table name that
matches with double quotes: `"order"`. Keep this check in `sql_generator.py`, not here —
the inferencer should only decide types, not worry about SQL syntax.

### 5.2 `engine/normalization_engine.py`

```python
from models.relational_schema import RelationalSchema
from engine.schema_inferencer import infer_table_schema
from models.column_schema import ColumnSchema, SqlType


def normalize(table_name: str, records: list[dict]) -> tuple[RelationalSchema, dict[str, list[dict]]]:
    """
    Returns:
      - a RelationalSchema containing the parent table and any child tables
      - a dict mapping table_name -> the actual row data for that table
        (used later by sql_generator.py to build INSERT statements)
    """
    schema = RelationalSchema()
    table_data: dict[str, list[dict]] = {table_name: []}

    parent_schema = infer_table_schema(table_name, records)
    array_fields = [c.name.replace("__nested_array__", "")
                    for c in parent_schema.columns if c.name.startswith("__nested_array__")]
    object_fields = [c.name.replace("__nested_object__", "")
                      for c in parent_schema.columns if c.name.startswith("__nested_object__")]

    # Remove the placeholder flag-columns; real columns get added below
    parent_schema.columns = [c for c in parent_schema.columns
                              if not c.name.startswith("__nested_")]

    parent_pk = parent_schema.get_primary_key()

    for record in records:
        flat_record = dict(record)

        # Strategy A: flatten nested objects (1:1) into prefixed columns
        for field_name in object_fields:
            nested = flat_record.pop(field_name, {}) or {}
            for sub_key, sub_val in nested.items():
                flat_record[f"{field_name}_{sub_key}"] = sub_val

        # Strategy B: pull nested arrays (1:N) out into child table rows
        for field_name in array_fields:
            items = flat_record.pop(field_name, []) or []
            child_table_name = f"{table_name}_{field_name}"
            if child_table_name not in table_data:
                table_data[child_table_name] = []
            for item in items:
                child_row = dict(item)
                child_row[f"{parent_pk.name}"] = flat_record.get(parent_pk.name)
                table_data[child_table_name].append(child_row)

        table_data[table_name].append(flat_record)

    # Re-infer the parent schema now that nested fields have been flattened/removed
    parent_schema = infer_table_schema(table_name, table_data[table_name])
    schema.add_table(parent_schema)

    # Infer + link each child table
    for field_name in array_fields:
        child_table_name = f"{table_name}_{field_name}"
        child_rows = table_data.get(child_table_name, [])
        if not child_rows:
            continue
        child_schema = infer_table_schema(child_table_name, child_rows)
        child_schema.add_column(ColumnSchema(
            name=parent_pk.name, sql_type=parent_pk.sql_type,
            nullable=False, is_foreign_key=True,
            references=f"{table_name}({parent_pk.name})"
        ))
        schema.add_table(child_schema)

    return schema, table_data
```

### 5.3 `engine/sql_generator.py`

```python
RESERVED_WORDS = {"order", "group", "user", "select", "table", "key", "index"}


def quote_identifier(name: str) -> str:
    return f'"{name}"' if name.lower() in RESERVED_WORDS else name


def generate_ddl(schema) -> list[str]:
    statements = []
    for table in schema.tables.values():
        col_defs = []
        for col in table.columns:
            col_name = quote_identifier(col.name)
            parts = [col_name, col.sql_type.value]
            if col.is_primary_key:
                parts.append("PRIMARY KEY")
            elif not col.nullable:
                parts.append("NOT NULL")
            col_defs.append(" ".join(parts))

        for col in table.columns:
            if col.is_foreign_key and col.references:
                col_defs.append(f"FOREIGN KEY ({quote_identifier(col.name)}) REFERENCES {col.references}")

        ddl = f"CREATE TABLE {quote_identifier(table.name)} (\n  " + ",\n  ".join(col_defs) + "\n);"
        statements.append(ddl)
    return statements


def generate_dml(schema, table_data: dict[str, list[dict]]) -> dict[str, tuple[str, list[tuple]]]:
    """
    Returns, per table: (parameterized INSERT statement, list of value tuples)
    ready to be passed straight to cursor.executemany().
    """
    result = {}
    for table_name, rows in table_data.items():
        table = schema.get_table(table_name)
        if table is None or not rows:
            continue
        col_names = [c.name for c in table.columns]
        placeholders = ", ".join(["?"] * len(col_names))
        col_list = ", ".join(quote_identifier(c) for c in col_names)
        insert_sql = f"INSERT INTO {quote_identifier(table_name)} ({col_list}) VALUES ({placeholders})"
        value_tuples = [tuple(row.get(c) for c in col_names) for row in rows]
        result[table_name] = (insert_sql, value_tuples)
    return result
```

### 5.4 `database/db_loader.py`

```python
import sqlite3


def load(schema, table_data: dict, ddl_statements: list[str], dml: dict, db_path: str = "output.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for ddl in ddl_statements:
        cursor.execute(ddl)

    for table_name, (insert_sql, value_tuples) in dml.items():
        cursor.executemany(insert_sql, value_tuples)

    conn.commit()
    conn.close()
```

*(To target MySQL/PostgreSQL later, swap only this file's connection object — see
Section 7.)*

---

## 6. Testing Strategy

Use `pytest`. Build **one small adversarial fixture file per known edge case** rather
than one big "realistic" dataset — small files are easy to hand-verify.

### 6.1 Fixture files (`tests/fixtures/`)

Create these exact files:

**`mixed_types.csv`** — tests type fallback:
```csv
id,age
1,25
2,thirty
```
Expected: `age` resolves to `VARCHAR`, not `INTEGER`, because of the mismatch.

**`heterogeneous_keys.json`** — tests the union scan:
```json
[
  {"id": 1, "name": "Rohan"},
  {"id": 2, "name": "Anita", "email": "anita@example.com"}
]
```
Expected: the inferred schema has three columns (`id`, `name`, `email`), and `email` is
nullable.

**`reserved_words.csv`** — tests identifier escaping:
```csv
id,order,group
1,5,A
```
Expected: generated DDL contains `"order"` and `"group"` in quotes.

**`no_primary_key.csv`** — tests surrogate key generation:
```csv
name,city
Rohan,Pune
Anita,Mumbai
```
Expected: schema gets an auto-generated `<table>_id` primary key column.

**`nested_orders.json`** — tests array decomposition:
```json
[
  {"id": 101, "name": "Rohan", "orders": [{"item": "Laptop", "qty": 1}]},
  {"id": 102, "name": "Anita", "orders": [{"item": "Mouse", "qty": 2}, {"item": "Pen", "qty": 5}]}
]
```
Expected: two tables produced — `students` and `students_orders` — linked by
`id` -> `students_id` foreign key.

### 6.2 Example test files

**`tests/test_parsers.py`**
```python
from pathlib import Path
from parsers.csv_parser import CsvParser
from parsers.json_parser import JsonParser

FIXTURES = Path(__file__).parent / "fixtures"


def test_csv_parser_reads_rows_as_dicts():
    records = CsvParser().parse(FIXTURES / "mixed_types.csv")
    assert records == [{"id": "1", "age": "25"}, {"id": "2", "age": "thirty"}]


def test_json_parser_returns_list_of_dicts():
    records = JsonParser().parse(FIXTURES / "heterogeneous_keys.json")
    assert len(records) == 2
    assert records[1]["email"] == "anita@example.com"
```

**`tests/test_inferencer.py`**
```python
from pathlib import Path
from parsers.csv_parser import CsvParser
from parsers.json_parser import JsonParser
from engine.schema_inferencer import infer_table_schema
from models.column_schema import SqlType

FIXTURES = Path(__file__).parent / "fixtures"


def test_mixed_type_column_falls_back_to_varchar():
    records = CsvParser().parse(FIXTURES / "mixed_types.csv")
    schema = infer_table_schema("t", records)
    age_col = next(c for c in schema.columns if c.name == "age")
    assert age_col.sql_type == SqlType.VARCHAR


def test_union_scan_catches_key_present_in_only_one_record():
    records = JsonParser().parse(FIXTURES / "heterogeneous_keys.json")
    schema = infer_table_schema("t", records)
    col_names = {c.name for c in schema.columns}
    assert "email" in col_names
    email_col = next(c for c in schema.columns if c.name == "email")
    assert email_col.nullable is True


def test_surrogate_primary_key_generated_when_missing():
    records = CsvParser().parse(FIXTURES / "no_primary_key.csv")
    schema = infer_table_schema("people", records)
    pk = schema.get_primary_key()
    assert pk is not None
    assert pk.name == "people_id"
```

**`tests/test_normalizer.py`**
```python
from pathlib import Path
from parsers.json_parser import JsonParser
from engine.normalization_engine import normalize

FIXTURES = Path(__file__).parent / "fixtures"


def test_nested_array_creates_child_table_with_foreign_key():
    records = JsonParser().parse(FIXTURES / "nested_orders.json")
    schema, table_data = normalize("students", records)

    assert "students" in schema.tables
    assert "students_orders" in schema.tables

    child_table = schema.tables["students_orders"]
    fk_columns = [c for c in child_table.columns if c.is_foreign_key]
    assert len(fk_columns) == 1
    assert "students" in fk_columns[0].references

    assert len(table_data["students_orders"]) == 3  # 1 + 2 order rows total
```

**`tests/test_sql_generator.py`**
```python
from pathlib import Path
from parsers.csv_parser import CsvParser
from engine.schema_inferencer import infer_table_schema
from engine.normalization_engine import normalize
from engine.sql_generator import generate_ddl

FIXTURES = Path(__file__).parent / "fixtures"


def test_reserved_words_are_quoted_in_ddl():
    records = CsvParser().parse(FIXTURES / "reserved_words.csv")
    schema, _ = normalize("t", records)
    ddl_statements = generate_ddl(schema)
    combined = "\n".join(ddl_statements)
    assert '"order"' in combined
    assert '"group"' in combined
```

### 6.3 Running the tests

```bash
pytest tests/ -v
```

### 6.4 End-to-end / manual test

After unit tests pass, run the whole pipeline against each fixture and inspect the
actual `.db` file it produces:

```bash
python main.py tests/fixtures/nested_orders.json
sqlite3 output.db ".tables"
sqlite3 output.db "SELECT * FROM students;"
sqlite3 output.db "SELECT * FROM students_orders;"
```

Confirm row counts and foreign key values match what you'd expect by hand — this is
the check that actually matters for a demo, more than the unit test count.

---

## 7. Swapping SQLite for MySQL/PostgreSQL Later

Only `database/db_loader.py` needs to change. Everything above it (parsers, models,
engine) has no knowledge of which database will run the generated SQL.

```python
# MySQL version — only the connection changes:
import mysql.connector  # pip install mysql-connector-python

def load(schema, table_data, ddl_statements, dml, **db_config):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    for ddl in ddl_statements:
        cursor.execute(ddl)
    for table_name, (insert_sql, value_tuples) in dml.items():
        cursor.executemany(insert_sql.replace("?", "%s"), value_tuples)
    conn.commit()
    conn.close()
```

Note the one syntax quirk: SQLite uses `?` placeholders, MySQL uses `%s`. Keep a small
`PLACEHOLDER_STYLE` constant per dialect if you need to support both from the same
codebase.

---

## 8. Build Order Checklist

Work through this in order — each step should be runnable and testable before moving
to the next:

- [ ] Project skeleton created, empty files with docstrings in place
- [ ] `JsonParser` implemented and tested
- [ ] `schema_inferencer.py` implemented for flat (non-nested) records, tested
- [ ] `sql_generator.py` DDL generation for flat schemas, tested
- [ ] `db_loader.py` writes to SQLite, confirmed with a manual `sqlite3` query
- [ ] `CsvParser` and `ExcelParser` implemented, tested against fixtures
- [ ] `TextParser` implemented, tested against a sample log-style file
- [ ] Nested object flattening added to `normalization_engine.py`, tested
- [ ] Nested array decomposition (child tables + FKs) added, tested
- [ ] Reserved-keyword escaping added to `sql_generator.py`, tested
- [ ] Surrogate primary key generation added to inferencer, tested
- [ ] All five fixture files pass their corresponding tests
- [ ] Full `main.py` CLI wired up end-to-end, demoed against each format
