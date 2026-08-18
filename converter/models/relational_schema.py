"""Full relational schema graph."""

from dataclasses import dataclass, field

from models.table_schema import TableSchema


@dataclass
class RelationalSchema:
    tables: dict[str, TableSchema] = field(default_factory=dict)

    def add_table(self, table: TableSchema) -> None:
        self.tables[table.name] = table

    def get_table(self, name: str) -> TableSchema | None:
        return self.tables.get(name)
