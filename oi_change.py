from flask import render_template, make_response

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)

import csv
import io


def register_oi_change(
    app,
    SNAPSHOTS,
    DATA_LOCK
):

    # ============================================================
    # BUILD DATA
    # ============================================================

    def build_data():

        with DATA_LOCK:
            snapshots = list(SNAPSHOTS)

        if not snapshots:

            return {
                "spot": None,
                "atm": None,
                "expiry": None,
                "columns": [],
                "rows": [],
                "volume_rows": []
            }

        latest = snapshots[0]

        # ========================================================
        # TIMESTAMP COLUMNS
        # ========================================================

        columns = []

        for snapshot in reversed(snapshots):

            timestamp = snapshot.get(
                "timestamp"
            )

            if timestamp:
                columns.append(
                    timestamp
                )

        if not columns:
            columns.append(
                "Current"
            )

        # ========================================================
        # ORDER SNAPSHOTS
        # ========================================================

        ordered = list(
            reversed(snapshots)
        )

        latest_rows = latest.get(
            "rows",
            []
        )

        # ========================================================
        # OI CHANGE ROWS
        # ========================================================

        rows = []

        for latest_row in latest_rows:

            strike = float(
                latest_row["strike"]
            )

            row_data = {

                "strike": strike,

                "atm": (
                    strike
                    == float(
                        latest["atm"]
                    )
                ),

                "changes": []

            }

            for index, current in enumerate(
                ordered
            ):

                current_rows = {

                    float(
                        row["strike"]
                    ): row

                    for row in current.get(
                        "rows",
                        []
                    )

                }

                current_row = current_rows.get(
                    strike
                )

                if current_row is None:

                    row_data["changes"].append({
                        "ce": 0,
                        "pe": 0
                    })

                    continue

                if index == 0:

                    ce_change = 0
                    pe_change = 0

                else:

                    previous = ordered[
                        index - 1
                    ]

                    previous_rows = {

                        float(
                            row["strike"]
                        ): row

                        for row in previous.get(
                            "rows",
                            []
                        )

                    }

                    previous_row = previous_rows.get(
                        strike
                    )

                    if previous_row is None:

                        ce_change = 0
                        pe_change = 0

                    else:

                        ce_change = (
                            float(
                                current_row.get(
                                    "ce_oi"
                                ) or 0
                            )
                            -
                            float(
                                previous_row.get(
                                    "ce_oi"
                                ) or 0
                            )
                        )

                        pe_change = (
                            float(
                                current_row.get(
                                    "pe_oi"
                                ) or 0
                            )
                            -
                            float(
                                previous_row.get(
                                    "pe_oi"
                                ) or 0
                            )
                        )

                row_data["changes"].append({
                    "ce": ce_change,
                    "pe": pe_change
                })

            rows.append(
                row_data
            )

        # ========================================================
        # VOLUME CHANGE ROWS
        # ========================================================

        volume_rows = []

        for latest_row in latest_rows:

            strike = float(
                latest_row["strike"]
            )

            row_data = {

                "strike": strike,

                "atm": (
                    strike
                    == float(
                        latest["atm"]
                    )
                ),

                "changes": []

            }

            for index, current in enumerate(
                ordered
            ):

                current_rows = {

                    float(
                        row["strike"]
                    ): row

                    for row in current.get(
                        "rows",
                        []
                    )

                }

                current_row = current_rows.get(
                    strike
                )

                if current_row is None:

                    row_data["changes"].append({
                        "ce": 0,
                        "pe": 0
                    })

                    continue

                if index == 0:

                    ce_change = 0
                    pe_change = 0

                else:

                    previous = ordered[
                        index - 1
                    ]

                    previous_rows = {

                        float(
                            row["strike"]
                        ): row

                        for row in previous.get(
                            "rows",
                            []
                        )

                    }

                    previous_row = previous_rows.get(
                        strike
                    )

                    if previous_row is None:

                        ce_change = 0
                        pe_change = 0

                    else:

                        ce_change = (
                            float(
                                current_row.get(
                                    "ce_volume"
                                ) or 0
                            )
                            -
                            float(
                                previous_row.get(
                                    "ce_volume"
                                ) or 0
                            )
                        )

                        pe_change = (
                            float(
                                current_row.get(
                                    "pe_volume"
                                ) or 0
                            )
                            -
                            float(
                                previous_row.get(
                                    "pe_volume"
                                ) or 0
                            )
                        )

                row_data["changes"].append({
                    "ce": ce_change,
                    "pe": pe_change
                })

            volume_rows.append(
                row_data
            )

        return {
            "spot": latest.get(
                "spot"
            ),
            "atm": latest.get(
                "atm"
            ),
            "expiry": latest.get(
                "expiry"
            ),
            "columns": columns,
            "rows": rows,
            "volume_rows": volume_rows
        }

    # ============================================================
    # OI CHANGE PAGE
    # ============================================================

    @app.route("/oi-change")
    def oi_change():

        data = build_data()

        return render_template(
            "oi_change.html",

            spot=data["spot"],

            atm=data["atm"],

            expiry=data["expiry"],

            columns=data["columns"],

            rows=data["rows"],

            volume_rows=data["volume_rows"]
        )

    # ============================================================
    # DOWNLOAD CSV
    # ============================================================

    @app.route("/download-oi-change-csv")
    def download_oi_change_csv():

        data = build_data()

        csv_buffer = io.StringIO()

        writer = csv.writer(
            csv_buffer
        )

        # ========================================================
        # BASIC INFORMATION
        # ========================================================

        writer.writerow([
            "NIFTY OI Change"
        ])

        writer.writerow([
            "SPOT",
            data["spot"]
            if data["spot"] is not None
            else ""
        ])

        writer.writerow([
            "ATM",
            data["atm"]
            if data["atm"] is not None
            else ""
        ])

        writer.writerow([
            "EXPIRY",
            data["expiry"]
            if data["expiry"]
            else ""
        ])

        writer.writerow([])

        # ========================================================
        # OI CHANGE
        # ========================================================

        writer.writerow([
            "OI Change"
        ])

        oi_header = [
            "STRIKE"
        ]

        for timestamp in data["columns"]:

            oi_header.extend([
                f"{timestamp} CE OI",
                f"{timestamp} PE OI"
            ])

        writer.writerow(
            oi_header
        )

        for row in data["rows"]:

            csv_row = [
                row["strike"]
            ]

            for change in row["changes"]:

                csv_row.extend([
                    change["ce"],
                    change["pe"]
                ])

            writer.writerow(
                csv_row
            )

        writer.writerow([])

        # ========================================================
        # VOLUME CHANGE
        # ========================================================

        writer.writerow([
            "Volume Change"
        ])

        volume_header = [
            "STRIKE"
        ]

        for timestamp in data["columns"]:

            volume_header.extend([
                f"{timestamp} CE VOLUME",
                f"{timestamp} PE VOLUME"
            ])

        writer.writerow(
            volume_header
        )

        for row in data["volume_rows"]:

            csv_row = [
                row["strike"]
            ]

            for change in row["changes"]:

                csv_row.extend([
                    change["ce"],
                    change["pe"]
                ])

            writer.writerow(
                csv_row
            )

        response = make_response(
            csv_buffer.getvalue()
        )

        response.headers[
            "Content-Type"
        ] = "text/csv; charset=utf-8"

        response.headers[
            "Content-Disposition"
        ] = (
            "attachment; "
            "filename=oi_change.csv"
        )

        return response

    # ============================================================
    # DOWNLOAD PDF
    # ============================================================

    @app.route("/download-oi-change")
    def download_oi_change():

        data = build_data()

        pdf_buffer = io.BytesIO()

        document = SimpleDocTemplate(

            pdf_buffer,

            pagesize=landscape(A4),

            rightMargin=8 * mm,

            leftMargin=8 * mm,

            topMargin=8 * mm,

            bottomMargin=8 * mm
        )

        styles = getSampleStyleSheet()

        title_style = styles["Title"]

        heading_style = styles["Heading2"]

        normal_style = styles["Normal"]

        normal_style.fontSize = 7

        normal_style.leading = 8

        title_style.fontSize = 14

        heading_style.fontSize = 10

        story = []

        # ========================================================
        # TITLE
        # ========================================================

        story.append(
            Paragraph(
                "NIFTY OI Change",
                title_style
            )
        )

        story.append(
            Spacer(
                1,
                3 * mm
            )
        )

        # ========================================================
        # BASIC INFORMATION
        # ========================================================

        spot = data["spot"]

        atm = data["atm"]

        expiry = data["expiry"]

        info_data = [[

            "SPOT",

            f"{spot:.2f}"
            if spot is not None
            else "--",

            "ATM",

            f"{atm:.0f}"
            if atm is not None
            else "--",

            "EXPIRY",

            str(expiry)
            if expiry
            else "--"

        ]]

        info_table = Table(
            info_data
        )

        info_table.setStyle(
            TableStyle([

                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor(
                        "#f1f5f9"
                    )
                ),

                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey
                ),

                (
                    "FONTNAME",
                    (0, 0),
                    (-1, -1),
                    "Helvetica-Bold"
                ),

                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8
                ),

                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER"
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5
                )

            ])
        )

        story.append(
            info_table
        )

        story.append(
            Spacer(
                1,
                5 * mm
            )
        )

        # ========================================================
        # OI CHANGE TABLE
        # ========================================================

        story.append(
            Paragraph(
                "OI Change",
                heading_style
            )
        )

        columns = data["columns"]

        oi_header_1 = [
            "STRIKE"
        ]

        oi_header_2 = [
            ""
        ]

        for timestamp in columns:

            oi_header_1.extend([
                timestamp,
                ""
            ])

            oi_header_2.extend([
                "CE OI",
                "PE OI"
            ])

        oi_table_data = [
            oi_header_1,
            oi_header_2
        ]

        for row in data["rows"]:

            pdf_row = [
                f'{row["strike"]:,.0f}'
            ]

            for change in row["changes"]:

                pdf_row.extend([

                    f'{change["ce"]:,.0f}',

                    f'{change["pe"]:,.0f}'

                ])

            oi_table_data.append(
                pdf_row
            )

        if len(oi_table_data) > 2:

            oi_table = Table(
                oi_table_data,

                repeatRows=2
            )

            oi_styles = [

                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.grey
                ),

                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor(
                        "#fef3c7"
                    )
                ),

                (
                    "BACKGROUND",
                    (1, 0),
                    (-1, 0),
                    colors.HexColor(
                        "#e5e7eb"
                    )
                ),

                (
                    "BACKGROUND",
                    (1, 1),
                    (-1, 1),
                    colors.HexColor(
                        "#f8fafc"
                    )
                ),

                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 1),
                    "Helvetica-Bold"
                ),

                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    6
                ),

                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER"
                ),

                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE"
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    2
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    2
                )

            ]

            for row_index, row in enumerate(
                data["rows"],
                start=2
            ):

                if row["atm"]:

                    oi_styles.append(
                        (
                            "BACKGROUND",
                            (0, row_index),
                            (-1, row_index),
                            colors.HexColor(
                                "#fee2e2"
                            )
                        )
                    )

            oi_table.setStyle(
                TableStyle(
                    oi_styles
                )
            )

            story.append(
                oi_table
            )

        else:

            story.append(
                Paragraph(
                    "No OI data available.",
                    normal_style
                )
            )

        story.append(
            Spacer(
                1,
                6 * mm
            )
        )

        # ========================================================
        # VOLUME CHANGE TABLE
        # ========================================================

        story.append(
            Paragraph(
                "Volume Change",
                heading_style
            )
        )

        volume_header_1 = [
            "STRIKE"
        ]

        volume_header_2 = [
            ""
        ]

        for timestamp in columns:

            volume_header_1.extend([
                timestamp,
                ""
            ])

            volume_header_2.extend([
                "CE VOLUME",
                "PE VOLUME"
            ])

        volume_table_data = [
            volume_header_1,
            volume_header_2
        ]

        for row in data["volume_rows"]:

            pdf_row = [
                f'{row["strike"]:,.0f}'
            ]

            for change in row["changes"]:

                pdf_row.extend([

                    f'{change["ce"]:,.0f}',

                    f'{change["pe"]:,.0f}'

                ])

            volume_table_data.append(
                pdf_row
            )

        if len(volume_table_data) > 2:

            volume_table = Table(
                volume_table_data,

                repeatRows=2
            )

            volume_styles = [

                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.grey
                ),

                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor(
                        "#fef3c7"
                    )
                ),

                (
                    "BACKGROUND",
                    (1, 0),
                    (-1, 0),
                    colors.HexColor(
                        "#e5e7eb"
                    )
                ),

                (
                    "BACKGROUND",
                    (1, 1),
                    (-1, 1),
                    colors.HexColor(
                        "#f8fafc"
                    )
                ),

                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 1),
                    "Helvetica-Bold"
                ),

                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    6
                ),

                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER"
                ),

                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE"
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    2
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    2
                )

            ]

            for row_index, row in enumerate(
                data["volume_rows"],
                start=2
            ):

                if row["atm"]:

                    volume_styles.append(
                        (
                            "BACKGROUND",
                            (0, row_index),
                            (-1, row_index),
                            colors.HexColor(
                                "#fee2e2"
                            )
                        )
                    )

            volume_table.setStyle(
                TableStyle(
                    volume_styles
                )
            )

            story.append(
                volume_table
            )

        else:

            story.append(
                Paragraph(
                    "No volume data available.",
                    normal_style
                )
            )

        # ========================================================
        # BUILD PDF
        # ========================================================

        document.build(
            story
        )

        pdf_buffer.seek(0)

        response = make_response(
            pdf_buffer.getvalue()
        )

        response.headers[
            "Content-Type"
        ] = "application/pdf"

        response.headers[
            "Content-Disposition"
        ] = (
            "attachment; "
            "filename=oi_change.pdf"
        )

        return response