from flask import render_template


def register_oi_treemap(
    app,
    SNAPSHOTS,
    DATA_LOCK
):

    @app.route("/oi-treemap")
    def oi_treemap():

        with DATA_LOCK:

            snapshots = list(
                SNAPSHOTS
            )

        if not snapshots:

            return render_template(
                "oi_treemap.html",
                snapshots=[]
            )

        # ====================================================
        # SNAPSHOTS ARE STORED NEWEST FIRST
        # ====================================================

        ordered = list(
            snapshots
        )

        treemap_snapshots = []

        # ====================================================
        # BUILD OI CHANGE
        # LATEST OI - PREVIOUS OI
        # ====================================================

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

            previous_rows = {}

            # ====================================================
            # PREVIOUS SNAPSHOT
            # Since snapshots[0] is latest,
            # previous snapshot is index + 1
            # ====================================================

            if index + 1 < len(
                ordered
            ):

                previous = ordered[
                    index + 1
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

            ce_boxes = []
            pe_boxes = []

            # ====================================================
            # EACH STRIKE
            # ====================================================

            for strike, current_row in current_rows.items():

                # ====================================================
                # NO PREVIOUS SNAPSHOT
                # ====================================================

                if index + 1 >= len(
                    ordered
                ):

                    ce_change = 0
                    pe_change = 0

                else:

                    previous_row = previous_rows.get(
                        strike
                    )

                    if previous_row is None:

                        ce_change = 0
                        pe_change = 0

                    else:

                        # ====================================================
                        # CE OI CHANGE
                        # LATEST OI - PREVIOUS OI
                        # ====================================================

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

                        # ====================================================
                        # PE OI CHANGE
                        # LATEST OI - PREVIOUS OI
                        # ====================================================

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

                # ====================================================
                # CE BOX
                # ====================================================

                if ce_change != 0:

                    ce_boxes.append({

                        "strike": strike,

                        "type": "CE",

                        "value": ce_change,

                        "absolute": abs(
                            ce_change
                        )

                    })

                # ====================================================
                # PE BOX
                # ====================================================

                if pe_change != 0:

                    pe_boxes.append({

                        "strike": strike,

                        "type": "PE",

                        "value": pe_change,

                        "absolute": abs(
                            pe_change
                        )

                    })

            # ====================================================
            # SORT HIGHEST CHANGE TO LOWEST
            # ====================================================

            ce_boxes.sort(
                key=lambda x: x["absolute"],
                reverse=True
            )

            pe_boxes.sort(
                key=lambda x: x["absolute"],
                reverse=True
            )

            # ====================================================
            # SNAPSHOT DATA
            # ====================================================

            treemap_snapshots.append({

                "timestamp": current.get(
                    "timestamp",
                    ""
                ),

                "spot": current.get(
                    "spot"
                ),

                "atm": current.get(
                    "atm"
                ),

                "expiry": current.get(
                    "expiry"
                ),

                "ce_boxes": ce_boxes,

                "pe_boxes": pe_boxes

            })

        # ====================================================
        # RENDER
        # ====================================================

        return render_template(

            "oi_treemap.html",

            snapshots=treemap_snapshots

        )