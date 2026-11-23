from decimal import Decimal
from io import BytesIO
from pathlib import Path
from html import escape
from datetime import date, datetime
from math import ceil
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.graphics.shapes import Drawing, String, Rect, Line, PolyLine, Circle
from reportlab.graphics.charts.barcharts import VerticalBarChart, HorizontalBarChart
from reportlab.graphics.charts.doughnut import Doughnut


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, (float, Decimal)):
        return f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return str(value)


def make_report_pdf(title: str, sections: list[dict]) -> bytes:
    font = Path(__file__).resolve().parents[3] / "fonts" / "DejaVuSans.ttf"
    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", str(font)))
    if "DejaVuBold" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVuBold", str(font.with_name("DejaVuSans-Bold.ttf"))))
    output = BytesIO()
    width = landscape(A4)[0] - 48
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
    )
    style = ParagraphStyle("ru", fontName="DejaVu", fontSize=8, leading=11)
    heading = ParagraphStyle(
        "title", fontName="DejaVu", fontSize=14, leading=19, spaceAfter=10
    )
    story = [Paragraph(escape(title), heading)]
    for index, section in enumerate(sections):
        if index:
            story.append(PageBreak())
        story.append(Paragraph(escape(section.get("title", "")), heading))
        headers, rows = section["headers"], list(section["rows"])
        data = [[Paragraph(escape(format_value(v)), style) for v in headers]]
        row_styles = section.get("row_styles", [])
        name_column = section.get("name_column", 0)
        for row_index, row in enumerate(rows):
            meta = row_styles[row_index] if row_index < len(row_styles) else {}
            cells = []
            for col, value in enumerate(row):
                row_style = ParagraphStyle(
                    f"row-{index}-{row_index}-{col}", parent=style,
                    fontName="DejaVuBold" if meta.get("bold") else "DejaVu",
                    textColor=colors.HexColor("#087E8B") if meta.get("milestone") else colors.black,
                    leftIndent=min(8, int(meta.get("depth", 0))) * 10 if col == name_column else 0,
                )
                cells.append(Paragraph(escape(format_value(value)), row_style))
            data.append(cells)
        lengths = [
            min(
                60,
                max(
                    12,
                    len(str(label)),
                    *[len(format_value(row[col])) for row in rows if col < len(row)],
                ),
            )
            for col, label in enumerate(headers)
        ]
        minimums = [
            max(
                pdfmetrics.stringWidth(word, "DejaVu", 8)
                for value in [headers[col], *[row[col] for row in rows]]
                for word in (format_value(value).split() or [""])
            )
            + 14
            for col in range(len(headers))
        ]
        if sum(minimums) < width:
            widths = [
                minimums[col] + (width - sum(minimums)) * length / sum(lengths)
                for col, length in enumerate(lengths)
            ]
        else:
            widths = [width * length / sum(lengths) for length in lengths]
        table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0ECFC")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#D8D2EF")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#FAF9FC")],
                    ),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        for row_index, meta in enumerate(row_styles, 1):
            if meta.get("milestone") or meta.get("bold"):
                table.setStyle(TableStyle([("BACKGROUND", (0, row_index), (-1, row_index),
                    colors.HexColor("#E8F6F7" if meta.get("milestone") else "#F0F0F2"))]))
        story.append(table)
        spec = section.get("chart")
        if spec and rows:
            chunk_size = len(rows) if spec.get("type") == "line" else 12
            for offset in range(0, len(rows), chunk_size):
                chart_rows = rows[offset : offset + chunk_size]
                drawing = Drawing(width, 300)
                drawing.add(
                    String(20, 280, section["title"], fontName="DejaVu", fontSize=11)
                )
                palette = (
                    "#7360D8",
                    "#279C8B",
                    "#9C93E5",
                    "#4178A5",
                    "#E15C62",
                    "#787797",
                )
                columns = spec.get("columns", [1])
                if spec.get("type") == "line":
                    values = [
                        [float(row[col] or 0) for row in chart_rows] for col in columns
                    ]
                    highest = max(value for series in values for value in series)
                    step = max(1, ceil(highest / 4))
                    chart_left, chart_bottom, chart_width, chart_height = (
                        45,
                        75,
                        width - 75,
                        175,
                    )
                    for tick in range(5):
                        y = chart_bottom + tick * chart_height / 4
                        drawing.add(
                            Line(
                                chart_left,
                                y,
                                chart_left + chart_width,
                                y,
                                strokeColor=colors.HexColor("#EAE6F4"),
                            )
                        )
                        drawing.add(
                            String(
                                chart_left - 9,
                                y - 3,
                                str(tick * step),
                                textAnchor="end",
                                fontName="DejaVu",
                                fontSize=8,
                            )
                        )
                    labels = spec.get("labels") or [str(row[0]) for row in chart_rows]
                    label_step = max(1, ceil(len(chart_rows) / 10))
                    for i, label in enumerate(labels):
                        if i % label_step == 0 or i == len(labels) - 1:
                            x = chart_left + i * chart_width / max(
                                1, len(chart_rows) - 1
                            )
                            drawing.add(
                                String(
                                    x,
                                    chart_bottom - 18,
                                    label,
                                    textAnchor="middle",
                                    fontName="DejaVu",
                                    fontSize=7,
                                )
                            )
                    for index, series in enumerate(values):
                        color = colors.HexColor(palette[index % len(palette)])
                        points = [
                            (
                                chart_left + i * chart_width / max(1, len(series) - 1),
                                chart_bottom + value / (step * 4) * chart_height,
                            )
                            for i, value in enumerate(series)
                        ]
                        drawing.add(
                            PolyLine(
                                [
                                    coordinate
                                    for point in points
                                    for coordinate in point
                                ],
                                strokeColor=color,
                                strokeWidth=1.8,
                            )
                        )
                        for x, y in points:
                            drawing.add(
                                Circle(
                                    x,
                                    y,
                                    2.5,
                                    fillColor=color,
                                    strokeColor=colors.white,
                                    strokeWidth=0.5,
                                )
                            )
                        drawing.add(
                            String(
                                45 + index * 220,
                                12,
                                str(headers[columns[index]]),
                                fontName="DejaVu",
                                fontSize=9,
                                fillColor=color,
                            )
                        )
                    story.extend([Spacer(1, 14), drawing])
                    continue
                elif spec.get("type") in ("pie", "doughnut"):
                    chart = Doughnut()
                    chart.x, chart.y, chart.width, chart.height = 45, 40, 205, 205
                    chart.innerRadiusFraction = 0.65
                    chart.data = [float(row[columns[0]] or 0) for row in chart_rows]
                    total = sum(chart.data)
                    chart.slices.strokeColor = colors.white
                    for i, row in enumerate(chart_rows):
                        color = colors.HexColor(palette[i % len(palette)])
                        chart.slices[i].fillColor = color
                        y = 225 - i * 25
                        drawing.add(
                            Rect(300, y - 3, 10, 10, fillColor=color, strokeColor=None)
                        )
                        value = chart.data[i]
                        percentage = value / total * 100 if total else 0
                        label = f"{row[0]}  {format_value(value)} ({percentage:.0f}%)"
                        drawing.add(
                            String(320, y, label, fontName="DejaVu", fontSize=10)
                        )
                    drawing.add(
                        String(
                            147,
                            137,
                            format_value(total),
                            textAnchor="middle",
                            fontName="DejaVu",
                            fontSize=22,
                        )
                    )
                else:
                    horizontal = spec.get("type") == "bar"
                    chart = HorizontalBarChart() if horizontal else VerticalBarChart()
                    chart.x, chart.y, chart.width, chart.height = (
                        (290, 45, width - 315, 210)
                        if horizontal
                        else (45, 90, width - 65, 165)
                    )
                    chart.data = [
                        [float(row[col] or 0) for row in chart_rows] for col in columns
                    ]
                    chart.categoryAxis.categoryNames = [
                        str(row[0]) for row in chart_rows
                    ]
                    chart.categoryAxis.labels.fontName = "DejaVu"
                    chart.categoryAxis.labels.fontSize = 8 if horizontal else 7
                    if horizontal:
                        chart.categoryAxis.labels.maxWidth = 270
                        chart.categoryAxis.labels.boxAnchor = "e"
                    else:
                        chart.categoryAxis.labels.angle = 20
                    chart.valueAxis.labels.fontName = "DejaVu"
                    chart.valueAxis.labels.fontSize = 8
                    if all(value >= 0 for series in chart.data for value in series):
                        chart.valueAxis.valueMin = 0
                    for i, col in enumerate(columns):
                        color = colors.HexColor(palette[i % len(palette)])
                        chart.bars[i].fillColor = color
                        drawing.add(
                            String(
                                45 + i * 220,
                                12,
                                str(headers[col]),
                                fontName="DejaVu",
                                fontSize=9,
                                fillColor=color,
                            )
                        )
                drawing.add(chart)
                story.extend([Spacer(1, 14), drawing])
    doc.build(story)
    return output.getvalue()


def make_pdf(title: str, headers: list[str], rows) -> bytes:
    return make_report_pdf(
        title, [{"title": "", "headers": headers, "rows": list(rows)}]
    )
