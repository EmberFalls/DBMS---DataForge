# DataForge converter

Convert JSON, CSV/TSV, Excel, or key-value text records into normalized MySQL tables.

## MySQL setup

1. Create and start a local MySQL server (for example, through MySQL Installer).
2. In PyCharm, set the `MYSQL_PASSWORD` environment variable in the run configuration.
3. Use this script-parameters value:

   ```text
   tests\fixtures\nested_orders.json --table-name students --database dataforge --host localhost --port 3306 --user root
   ```

The program creates the `dataforge` database if it does not already exist, then creates
the `students` and `students_orders` tables. It does not overwrite tables that already
exist; use a new database name for a fresh import.

To keep the previous local-file behavior, add `--dialect sqlite --output students.db`.
