"""Export records as CSV files that also open correctly in Excel."""

import csv
import io
import json


def csv_bytes(rows, columns):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()

    for row in rows:
        clean_row = {}
        for column in columns:
            value = row.get(column, '')
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)

            # Spreadsheet apps may treat cells beginning with these signs as formulas.
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                value = "'" + value
            clean_row[column] = value

        writer.writerow(clean_row)

    # The BOM helps Excel recognise UTF-8 accents without manual import settings.
    return output.getvalue().encode('utf-8-sig')
