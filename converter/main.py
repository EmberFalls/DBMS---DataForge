"""Command-line entry point for the multi-format SQL converter."""

import argparse
from pathlib import Path

from database.db_loader import load
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
    argument_parser = argparse.ArgumentParser(description="Convert a data file into a SQLite database.")
    argument_parser.add_argument("input_file", type=Path)
    argument_parser.add_argument("--table-name", help="Destination table name (defaults to input stem).")
    argument_parser.add_argument("--output", type=Path, default=Path("output.db"))
    args = argument_parser.parse_args()

    if not args.input_file.is_file():
        argument_parser.error(f"Input file does not exist: {args.input_file}")
    if args.output.exists():
        argument_parser.error(f"Output database already exists: {args.output}")

    records = get_parser(args.input_file).parse(args.input_file)
    table_name = args.table_name or args.input_file.stem
    schema, table_data = normalize(table_name, records)
    ddl = generate_ddl(schema)
    dml = generate_dml(schema, table_data)
    load(schema, table_data, ddl, dml, args.output)
    print(f"Created {args.output} with {len(schema.tables)} table(s).")


if __name__ == "__main__":
    main()
