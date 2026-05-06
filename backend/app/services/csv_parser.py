import csv
import io


def parse_csv_content(content: bytes) -> tuple[list[str], list[list[str]]]:
    if not content:
        raise ValueError("CSV file is empty.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV file must be UTF-8 encoded.") from exc

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("CSV file is empty.")

    columns = [column.strip() for column in rows[0]]
    if not any(columns):
        raise ValueError("CSV file must include a header row.")

    data_rows = [row for row in rows[1:] if any(cell.strip() for cell in row)]
    return columns, data_rows


def preview_rows(columns: list[str], rows: list[list[str]], limit: int = 5) -> list[dict[str, str]]:
    preview: list[dict[str, str]] = []
    for row in rows[:limit]:
        preview.append(
            {
                column: row[index].strip() if index < len(row) else ""
                for index, column in enumerate(columns)
            }
        )
    return preview
