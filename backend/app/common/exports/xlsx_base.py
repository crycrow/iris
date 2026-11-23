from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Iterable
import math
import xlsxwriter

COLORS = ["#7360D8", "#279C8B", "#9C93E5", "#4178A5", "#E15C62", "#787797"]


def cell_value(value):
    if value is None:
        return ""
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = float(value)
        return number if math.isfinite(number) else ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d.%m.%Y")
    return str(value)


def make_report_xlsx(title: str, sections: list[dict]) -> bytes:
    output = BytesIO()
    book = xlsxwriter.Workbook(
        output,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    )
    base = {"font_name": "Arial", "font_size": 11, "valign": "top"}
    plain = book.add_format({**base, "text_wrap": True})
    number = book.add_format({**base, "num_format": "#,##0.##"})
    head = book.add_format(
        {
            **base,
            "bold": True,
            "bg_color": "#F0ECFC",
            "text_wrap": True,
            "bottom": 1,
            "bottom_color": "#D8D2EF",
        }
    )
    heading = book.add_format(
        {**base, "font_size": 16, "bold": True, "font_color": "#201C57"}
    )
    row_formats = {}
    def row_format(meta, numeric=False, indent=False):
        key = (bool(meta.get("bold")), bool(meta.get("milestone")),
               min(15, int(meta.get("depth", 0))) if indent else 0, numeric)
        if key not in row_formats:
            options = {**base, "text_wrap": True, "bold": key[0], "indent": key[2]}
            if key[1]:
                options.update(font_color="#087E8B", bg_color="#E8F6F7")
            elif key[0]:
                options.update(bg_color="#F0F0F2")
            if numeric:
                options["num_format"] = "#,##0.##"
            row_formats[key] = book.add_format(options)
        return row_formats[key]
    used_names = set()
    for index, section in enumerate(sections):
        name = section.get("title", "Отчёт")[:28]
        for character in "[]:*?/\\":
            name = name.replace(character, " ")
        if name in used_names:
            name += str(index + 1)
        used_names.add(name)
        sheet = book.add_worksheet(name)
        headers = section["headers"]
        rows = [[cell_value(value) for value in row] for row in section["rows"]]
        sheet.set_default_row(22)
        sheet.hide_gridlines(2)
        sheet.write(0, 0, title, heading)
        if len(headers) > 1:
            sheet.merge_range(1, 0, 1, len(headers) - 1, section.get("title", ""), head)
        else:
            sheet.write(1, 0, section.get("title", ""), head)
        for col, label in enumerate(headers):
            sheet.write(3, col, label, head)
        widths = [
            min(
                58,
                max(
                    14,
                    len(str(label)) + 2,
                    *[len(str(row[col])) + 2 for row in rows if col < len(row)]
                ),
            )
            for col, label in enumerate(headers)
        ]
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width, plain)
        sheet.set_row(
            3,
            max(
                30,
                max(
                    math.ceil(len(str(label)) / max(1, widths[col] - 2))
                    for col, label in enumerate(headers)
                )
                * 16,
            ),
        )
        styles = section.get("row_styles", [])
        name_column = section.get("name_column", 0)
        for rownum, row in enumerate(rows, 4):
            meta = styles[rownum - 4] if rownum - 4 < len(styles) else {}
            for col, value in enumerate(row):
                sheet.write(
                    rownum,
                    col,
                    value,
                    row_format(meta, isinstance(value, (int, float)), col == name_column)
                    if meta else number if isinstance(value, (int, float)) else plain,
                )
            lines = max(
                (
                    math.ceil(len(str(value)) / max(1, widths[col] - 2))
                    for col, value in enumerate(row)
                ),
                default=1,
            )
            sheet.set_row(rownum, min(150, max(22, lines * 15)))
        sheet.freeze_panes(4, 1)
        if rows:
            sheet.autofilter(3, 0, len(rows) + 3, len(headers) - 1)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.repeat_rows(0, 3)
        spec = section.get("chart")
        if spec and rows:
            chart = book.add_chart({"type": spec.get("type", "column")})
            chart_column = len(headers) + 1
            category_column = 0
            if spec.get("labels"):
                category_column = chart_column + 14
                for rownum, label in enumerate(spec["labels"], 4):
                    sheet.write(rownum, category_column, label, plain)
                sheet.set_column(
                    category_column, category_column, None, None, {"hidden": True}
                )
                chart.show_hidden_data()
            for series_index, col in enumerate(spec.get("columns", [1])):
                chart.add_series(
                    {
                        "name": [name, 3, col],
                        "categories": [
                            name,
                            4,
                            category_column,
                            len(rows) + 3,
                            category_column,
                        ],
                        "values": [name, 4, col, len(rows) + 3, col],
                        "fill": {"color": COLORS[series_index % len(COLORS)]},
                        "line": {"color": COLORS[series_index % len(COLORS)]},
                        **(
                            {"marker": {"type": "circle", "size": 5}}
                            if spec.get("type") == "line"
                            else {}
                        ),
                        **(
                            {
                                "points": [
                                    {"fill": {"color": COLORS[i % len(COLORS)]}}
                                    for i in range(len(rows))
                                ]
                            }
                            if spec.get("type") in ("pie", "doughnut")
                            else {}
                        ),
                    }
                )
            chart.set_title(
                {"name": section["title"], "name_font": {"name": "Arial", "size": 12}}
            )
            chart.set_legend(
                {"position": "bottom", "font": {"name": "Arial", "size": 10}}
            )
            chart.set_x_axis(
                {
                    "num_font": {"name": "Arial", "size": 10},
                    **(
                        {"interval_unit": max(1, math.ceil(len(rows) / 12))}
                        if spec.get("type") == "line"
                        else {}
                    ),
                }
            )
            chart.set_y_axis(
                {
                    "name": spec.get("unit", "ч"),
                    "num_font": {"name": "Arial", "size": 10},
                    "major_gridlines": {"visible": True, "line": {"color": "#EAE6F4"}},
                    **(
                        {
                            "min": 0,
                            "major_unit": max(
                                1,
                                math.ceil(
                                    max(
                                        float(row[col] or 0)
                                        for row in rows
                                        for col in spec.get("columns", [1])
                                    )
                                    / 4
                                ),
                            ),
                        }
                        if spec.get("integer")
                        else {}
                    ),
                }
            )
            chart.set_chartarea({"border": {"none": True}})
            chart.set_size({"width": 760, "height": 360})
            sheet.set_column(chart_column, chart_column + 11, 10)
            sheet.insert_chart(3, chart_column, chart, {"object_position": 1})
            sheet.print_area(0, 0, max(len(rows) + 3, 22), chart_column + 11)
    book.close()
    return output.getvalue()


def make_xlsx(title: str, headers: list[str], rows: Iterable) -> bytes:
    return make_report_xlsx(
        title, [{"title": "Отчёт", "headers": headers, "rows": list(rows)}]
    )
