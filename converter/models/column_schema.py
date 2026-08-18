"""Column schema metadata."""

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
    references: str | None = None
