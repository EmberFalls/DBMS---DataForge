"""Command-line entry point for the multi-format SQL converter."""

import argparse
import getpass
import os
from pathlib import Path

from database.db_loader import load_mysql
from engine.normalization_engine import normalize
from engine.sql_generator import generate_ddl, generate_dml
from parsers.csv_parser import CsvParser
from parsers.excel_parser import ExcelParser
from parsers.json_parser import JsonParser
from parsers.text_parser import TextParser

PARSER_BY_EXTENSION = {
    ".csv": CsvParser,
    ".tsv": CsvParser,
    ".xlsx": ExcelParser,
    ".txt": TextParser,
    ".json": JsonParser,
}


def get_parser(file_path: Path):
    parser_class = PARSER_BY_EXTENSION.get(file_path.suffix.lower())
    if parser_class is None:
        raise ValueError(f"No parser registered for extension: {file_path.suffix}")
    return parser_class()


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Convert a data file into a MySQL database.")
    argument_parser.add_argument("input_file", type=Path)
    argument_parser.add_argument("--table-name", help="Destination table name (defaults to input stem).")
    argument_parser.add_argument("--database", default="dataforge", help="Existing MySQL database name.")
    argument_parser.add_argument("--host", default="localhost", help="MySQL host.")
    argument_parser.add_argument("--port", type=int, default=3306, help="MySQL port.")
    argument_parser.add_argument("--user", default="root", help="MySQL username.")
    args = argument_parser.parse_args()

    if not args.input_file.is_file():
        argument_parser.error(f"Input file does not exist: {args.input_file}")
    records = get_parser(args.input_file).parse(args.input_file)
    table_name = args.table_name or args.input_file.stem
    schema, table_data = normalize(table_name, records)
    ddl = generate_ddl(schema)
    dml = generate_dml(schema, table_data)
    password = os.environ.get("MYSQL_PASSWORD") or getpass.getpass("MySQL password: ")
    load_mysql(ddl, dml, host=args.host, port=args.port, user=args.user,
               password=password, database=args.database)
    print(f"Loaded {len(schema.tables)} table(s) into MySQL database '{args.database}'.")


if __name__ == "__main__":
    main()
