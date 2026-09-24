"""Spreadsheet presentation only. Never use for canonical or raw evidence."""
import csv
import io


def spreadsheet_safe_csv(text: str) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    for row in csv.reader(io.StringIO(text, newline="")):
        writer.writerow([
            "'" + cell if cell.lstrip(" \t\r\n").startswith(("=", "+", "-", "@"))
            or cell.startswith(("\t", "\r", "\n")) else cell
            for cell in row
        ])
    return output.getvalue()
