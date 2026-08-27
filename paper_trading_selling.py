import threading
from datetime import datetime

from flask import render_template, jsonify, request


# ============================================================
# PAPER SHORT SELLING
# ============================================================

SHORT_ACCOUNT_LOCK = threading.Lock()

INITIAL_BALANCE = 1000000.00

SHORT_ACCOUNT = {
    "initial_balance": INITIAL_BALANCE,
    "realized_pnl": 0.0,
    "positions": {},
    "trades": []
}


LOT_SIZES = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "GOLD": 100,
    "SILVER": 30,
    "CRUDEOIL": 100
}


def register_short_selling(
    app,
    get_snapshots,
    get_current_index,
    get_current_expiry
):

    # ========================================================
    # HELPERS
    # ========================================================

    def number(value, default=0.0):

        try:

            if value is None or value == "":
                return default

            return float(
                str(value).replace(",", "").strip()
            )

        except (
            ValueError,
            TypeError
        ):

            return default


    def get_lot_size(index_name):

        return LOT_SIZES.get(
            str(index_name or "").upper(),
            1
        )


    def get_position_key(
        index_name,
        expiry,
        strike,
        option_type
    ):

        return (
            str(index_name or "").strip().upper()
            + "|"
            + str(expiry or "").strip().upper()
            + "|"
            + str(number(strike))
            + "|"
            + str(option_type or "").strip().upper()
        )


    def get_current_market_price(
        index_name,
        expiry,
        strike,
        option_type
    ):

        snapshots = get_snapshots() or []

        index_name = str(
            index_name or ""
        ).strip().upper()

        expiry = str(
            expiry or ""
        ).strip().upper()

        option_type = str(
            option_type or ""
        ).strip().upper()

        target_strike = number(strike)

        for snapshot in snapshots:

            snapshot_index = str(
                snapshot.get("index", "")
            ).strip().upper()

            snapshot_expiry = str(
                snapshot.get("expiry", "")
            ).strip().upper()

            if snapshot_index != index_name:
                continue

            if snapshot_expiry != expiry:
                continue

            for row in snapshot.get("rows", []):

                row_strike = number(
                    row.get("strike")
                )

                if abs(row_strike - target_strike) > 0.000001:
                    continue

                if option_type == "CE":

                    price = number(
                        row.get("ce_ltp")
                    )

                else:

                    price = number(
                        row.get("pe_ltp")
                    )

                if price > 0:
                    return price

        return None


    def serialize_position(position):

        return {
            "index": position["index"],
            "expiry": position["expiry"],
            "strike": position["strike"],
            "option_type": position["option_type"],
            "quantity": position["quantity"],
            "lot_size": position["lot_size"],
            "avg_price": position["avg_price"],
            "current_price": position["current_price"],
            "lots": (
                position["quantity"] / position["lot_size"]
                if position["lot_size"]
                else position["quantity"]
            )
        }


    def get_positions():

        result = []

        for position in SHORT_ACCOUNT["positions"].values():

            current_price = get_current_market_price(
                position["index"],
                position["expiry"],
                position["strike"],
                position["option_type"]
            )

            if current_price is not None:
                position["current_price"] = current_price

            result.append(
                serialize_position(position)
            )

        return result


    def calculate_unrealized():

        total = 0.0

        for position in SHORT_ACCOUNT["positions"].values():

            current_price = get_current_market_price(
                position["index"],
                position["expiry"],
                position["strike"],
                position["option_type"]
            )

            if current_price is None:
                current_price = position["current_price"]

            quantity = position["quantity"]
            avg_price = position["avg_price"]

            total += (
                avg_price - current_price
            ) * quantity

        return total


    def calculate_account():

        unrealized = calculate_unrealized()

        realized = SHORT_ACCOUNT["realized_pnl"]

        total = realized + unrealized

        return {
            "initial_balance": SHORT_ACCOUNT["initial_balance"],
            "balance": (
                SHORT_ACCOUNT["initial_balance"]
                + realized
                + unrealized
            ),
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": total,
            "positions": get_positions(),
            "trades": list(
                reversed(
                    SHORT_ACCOUNT["trades"]
                )
            )
        }


    # ========================================================
    # SELLING PAGE
    # ========================================================

    @app.route("/paper-trading-selling")
    def paper_trading_selling_page():

        return render_template(
            "paper_trading_selling.html"
        )


    # ========================================================
    # SELL ORDER
    # ========================================================

    @app.route(
        "/api/paper-trading-selling/order",
        methods=["POST"]
    )
    def short_sell_order():

        try:

            data = request.get_json(
                silent=True
            )

            if not isinstance(data, dict):

                return jsonify({
                    "status": "error",
                    "message": "Invalid JSON request"
                }), 400

            action = str(
                data.get("action", "")
            ).strip().upper()

            option_type = str(
                data.get("option_type", "")
            ).strip().upper()

            index_name = str(
                data.get(
                    "index",
                    get_current_index()
                )
            ).strip().upper()

            expiry = str(
                data.get(
                    "expiry",
                    get_current_expiry()
                )
            ).strip().upper()

            strike = number(
                data.get("strike")
            )

            quantity = number(
                data.get("quantity")
            )

            if action not in (
                "SELL",
                "BUY"
            ):

                return jsonify({
                    "status": "error",
                    "message": "Action must be SELL or BUY"
                }), 400

            if option_type not in (
                "CE",
                "PE"
            ):

                return jsonify({
                    "status": "error",
                    "message": "Invalid option type"
                }), 400

            if not index_name:

                return jsonify({
                    "status": "error",
                    "message": "Index is required"
                }), 400

            if not expiry:

                return jsonify({
                    "status": "error",
                    "message": "Expiry is required"
                }), 400

            if strike <= 0:

                return jsonify({
                    "status": "error",
                    "message": "Invalid strike"
                }), 400

            if quantity <= 0:

                return jsonify({
                    "status": "error",
                    "message": "Quantity must be greater than zero"
                }), 400

            lot_size = get_lot_size(
                index_name
            )

            if quantity % lot_size != 0:

                return jsonify({
                    "status": "error",
                    "message":
                        f"Quantity must be in multiples of "
                        f"{lot_size}"
                }), 400

            price = get_current_market_price(
                index_name,
                expiry,
                strike,
                option_type
            )

            if price is None or price <= 0:

                return jsonify({
                    "status": "error",
                    "message":
                        "Current market price is unavailable"
                }), 400

            key = get_position_key(
                index_name,
                expiry,
                strike,
                option_type
            )

            with SHORT_ACCOUNT_LOCK:

                # ====================================================
                # SHORT SELL
                # ====================================================

                if action == "SELL":

                    position = SHORT_ACCOUNT[
                        "positions"
                    ].get(key)

                    if position is None:

                        position = {
                            "index": index_name,
                            "expiry": expiry,
                            "strike": strike,
                            "option_type": option_type,
                            "quantity": 0,
                            "lot_size": lot_size,
                            "avg_price": 0.0,
                            "current_price": price
                        }

                        SHORT_ACCOUNT[
                            "positions"
                        ][key] = position

                    old_quantity = position[
                        "quantity"
                    ]

                    old_average = position[
                        "avg_price"
                    ]

                    new_quantity = (
                        old_quantity
                        + quantity
                    )

                    if new_quantity > 0:

                        position[
                            "avg_price"
                        ] = (
                            (
                                old_average
                                * old_quantity
                            )
                            + (
                                price
                                * quantity
                            )
                        ) / new_quantity

                    position[
                        "quantity"
                    ] = new_quantity

                    position[
                        "current_price"
                    ] = price

                    SHORT_ACCOUNT[
                        "trades"
                    ].append({

                        "timestamp":
                            datetime.now().strftime(
                                "%d-%b-%Y %I:%M:%S %p"
                            ),

                        "action":
                            "SELL",

                        "index":
                            index_name,

                        "expiry":
                            expiry,

                        "strike":
                            strike,

                        "option_type":
                            option_type,

                        "quantity":
                            quantity,

                        "lot_size":
                            lot_size,

                        "price":
                            price,

                        "value":
                            price * quantity,

                        "pnl":
                            0.0

                    })

                    lots = quantity / lot_size

                    return jsonify({

                        "status":
                            "success",

                        "message":
                            f"SHORT SOLD "
                            f"{lots:g} lot(s) "
                            f"{option_type} "
                            f"{strike:g} @ {price:.2f}",

                        "price":
                            price,

                        "quantity":
                            quantity,

                        "lots":
                            lots,

                        "account":
                            calculate_account()

                    })


                # ====================================================
                # BUY TO COVER
                # ====================================================

                position = SHORT_ACCOUNT[
                    "positions"
                ].get(key)

                if position is None:

                    return jsonify({
                        "status": "error",
                        "message":
                            "No open short position exists "
                            "for this contract"
                    }), 400

                available_quantity = position[
                    "quantity"
                ]

                if quantity > available_quantity:

                    return jsonify({
                        "status": "error",
                        "message":
                            f"Cannot buy {quantity:g} units. "
                            f"Open short quantity is "
                            f"{available_quantity:g}"
                    }), 400

                avg_sell_price = position[
                    "avg_price"
                ]

                realized_pnl = (
                    avg_sell_price
                    - price
                ) * quantity

                SHORT_ACCOUNT[
                    "realized_pnl"
                ] += realized_pnl

                position[
                    "quantity"
                ] -= quantity

                position[
                    "current_price"
                ] = price

                SHORT_ACCOUNT[
                    "trades"
                ].append({

                    "timestamp":
                        datetime.now().strftime(
                            "%d-%b-%Y %I:%M:%S %p"
                        ),

                    "action":
                        "BUY",

                    "index":
                        index_name,

                    "expiry":
                        expiry,

                    "strike":
                        strike,

                    "option_type":
                        option_type,

                    "quantity":
                        quantity,

                    "lot_size":
                        lot_size,

                    "price":
                        price,

                    "sell_price":
                        avg_sell_price,

                    "value":
                        price * quantity,

                    "pnl":
                        realized_pnl

                })

                if position["quantity"] <= 0:

                    del SHORT_ACCOUNT[
                        "positions"
                    ][key]

                lots = quantity / lot_size

                return jsonify({

                    "status":
                        "success",

                    "message":
                        f"BOUGHT TO COVER "
                        f"{lots:g} lot(s) "
                        f"{option_type} "
                        f"{strike:g} @ {price:.2f}",

                    "price":
                        price,

                    "quantity":
                        quantity,

                    "lots":
                        lots,

                    "realized_pnl":
                        realized_pnl,

                    "account":
                        calculate_account()

                })

        except Exception as exc:

            return jsonify({

                "status": "error",

                "message": str(exc)

            }), 500


    # ========================================================
    # ACCOUNT
    # ========================================================

    @app.route(
        "/api/paper-trading-selling/account"
    )
    def short_account():

        try:

            with SHORT_ACCOUNT_LOCK:

                account = calculate_account()

            return jsonify({

                "status":
                    "success",

                "account":
                    account

            })

        except Exception as exc:

            return jsonify({

                "status":
                    "error",

                "message":
                    str(exc)

            }), 500


    # ========================================================
    # RESET
    # ========================================================

    @app.route(
        "/api/paper-trading-selling/reset",
        methods=["POST"]
    )
    def reset_short_account():

        with SHORT_ACCOUNT_LOCK:

            SHORT_ACCOUNT[
                "realized_pnl"
            ] = 0.0

            SHORT_ACCOUNT[
                "positions"
            ].clear()

            SHORT_ACCOUNT[
                "trades"
            ].clear()

        return jsonify({

            "status":
                "success",

            "message":
                "Short selling paper account reset"

        })