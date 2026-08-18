"""Table schema metadata."""

from dataclasses import dataclass, field

from models.column_schema import ColumnSchema


@dataclass
class TableSchema:
    name: str
    columns: list[ColumnSchema] = field(default_factory=list)

    def add_column(self, column: ColumnSchema) -> None:
        self.columns.append(column)

    def get_primary_key(self) -> ColumnSchema | None:
        return next((column for column in self.columns if column.is_primary_key), None)
