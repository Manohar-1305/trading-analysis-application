import threading
from datetime import datetime
from flask import render_template, jsonify, request


# ============================================================
# PAPER TRADING
# ============================================================
# This module NEVER sends an order to Angel One.
# It uses the exact option-chain snapshot data already
# collected by the existing application.
#
# Register with:
#
# from paper_trading import register_paper_trading
#
# register_paper_trading(
#     app,
#     get_snapshots=lambda: SNAPSHOTS,
#     get_current_index=lambda: CURRENT_INDEX,
#     get_current_expiry=lambda: CURRENT_EXPIRY,
# )
# ============================================================


PAPER_INITIAL_BALANCE = 1000000.0

paper_lock = threading.Lock()

paper_account = {
    "initial_balance": PAPER_INITIAL_BALANCE,
    "balance": PAPER_INITIAL_BALANCE,
    "realized_pnl": 0.0,
    "trades": [],
    "positions": {},
}


def _number(value, default=0.0):
    try:
        if value is None or value == "":
            return default

        return float(str(value).replace(",", "").strip())

    except (ValueError, TypeError):
        return default


def _get_latest_snapshot(get_snapshots):
    snapshots = list(get_snapshots() or [])

    return snapshots[0] if snapshots else None


def _find_option(snapshot, strike, option_type):
    if not snapshot:
        return None

    option_type = str(option_type).strip().upper()

    for row in snapshot.get("rows", []):
        row_strike = _number(row.get("strike"), None)

        if row_strike is None:
            continue

        if abs(row_strike - strike) > 0.001:
            continue

        if option_type == "CE":
            return {
                "strike": row_strike,
                "option_type": "CE",
                "ltp": _number(row.get("ce_ltp")),
                "change": _number(row.get("ce_change")),
                "oi": _number(row.get("ce_oi")),
                "oi_change": _number(row.get("ce_oi_change")),
                "volume": _number(row.get("ce_volume")),
            }

        if option_type == "PE":
            return {
                "strike": row_strike,
                "option_type": "PE",
                "ltp": _number(row.get("pe_ltp")),
                "change": _number(row.get("pe_change")),
                "oi": _number(row.get("pe_oi")),
                "oi_change": _number(row.get("pe_oi_change")),
                "volume": _number(row.get("pe_volume")),
            }

    return None


def _position_key(index, expiry, strike, option_type):
    return (
        f"{index}|{expiry}|{float(strike):.2f}|"
        f"{str(option_type).upper()}"
    )


def _position_view(position, current_price):
    quantity = int(position["quantity"])

    avg_price = float(position["avg_price"])

    current_price = float(current_price)

    market_value = current_price * quantity

    invested_value = avg_price * quantity

    unrealized_pnl = (
        current_price - avg_price
    ) * quantity

    result = dict(position)

    result["current_price"] = current_price

    result["market_value"] = market_value

    result["invested_value"] = invested_value

    result["unrealized_pnl"] = unrealized_pnl

    if invested_value:
        result["pnl_percent"] = (
            unrealized_pnl / invested_value
        ) * 100
    else:
        result["pnl_percent"] = 0.0

    return result


def _get_account_view(get_snapshots):
    snapshot = _get_latest_snapshot(get_snapshots)

    positions = []

    total_unrealized = 0.0

    with paper_lock:
        stored_positions = list(
            paper_account["positions"].values()
        )

        for position in stored_positions:
            option = _find_option(
                snapshot,
                float(position["strike"]),
                position["option_type"],
            )

            current_price = (
                option["ltp"]
                if option
                else float(position["avg_price"])
            )

            viewed = _position_view(
                position,
                current_price,
            )

            positions.append(viewed)

            total_unrealized += viewed["unrealized_pnl"]

        balance = float(
            paper_account["balance"]
        )

        realized_pnl = float(
            paper_account["realized_pnl"]
        )

        initial_balance = float(
            paper_account["initial_balance"]
        )

        trades = list(
            reversed(paper_account["trades"])
        )

    equity = balance + total_unrealized

    return {
        "initial_balance": initial_balance,
        "balance": balance,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": total_unrealized,
        "equity": equity,
        "total_pnl": equity - initial_balance,
        "positions": positions,
        "trades": trades,
    }


def _validate_order_request(data):
    data = data or {}

    option_type = str(
        data.get("option_type", "")
    ).strip().upper()

    try:
        strike = float(data.get("strike"))
    except (TypeError, ValueError):
        return None, None, None, (
            "Invalid strike"
        )

    try:
        quantity = int(data.get("quantity"))
    except (TypeError, ValueError):
        return None, None, None, (
            "Invalid quantity"
        )

    if option_type not in ("CE", "PE"):
        return None, None, None, (
            "Option type must be CE or PE"
        )

    if quantity <= 0:
        return None, None, None, (
            "Quantity must be greater than zero"
        )

    return (
        option_type,
        strike,
        quantity,
        None,
    )


def _execute_buy(
    get_snapshots,
    get_current_index,
    get_current_expiry,
    option_type,
    strike,
    quantity,
):
    snapshot = _get_latest_snapshot(get_snapshots)

    if not snapshot:
        return jsonify({
            "status": "error",
            "message": (
                "No option-chain snapshot available"
            ),
        }), 400

    option = _find_option(
        snapshot,
        strike,
        option_type,
    )

    if not option:
        return jsonify({
            "status": "error",
            "message": (
                f"{option_type} {strike:g} "
                "is not available in the current snapshot"
            ),
        }), 400

    price = float(option["ltp"])

    if price <= 0:
        return jsonify({
            "status": "error",
            "message": (
                f"Invalid LTP for "
                f"{option_type} {strike:g}"
            ),
        }), 400

    index = snapshot.get(
        "index",
        get_current_index(),
    )

    expiry = snapshot.get(
        "expiry",
        get_current_expiry(),
    )

    key = _position_key(
        index,
        expiry,
        strike,
        option_type,
    )

    now = datetime.now().strftime(
        "%d-%b-%Y %I:%M:%S %p"
    )

    with paper_lock:
        position = paper_account["positions"].get(key)

        order_value = price * quantity

        if order_value > paper_account["balance"]:
            return jsonify({
                "status": "error",
                "message": (
                    "Insufficient paper balance"
                ),
            }), 400

        if position:
            old_quantity = int(
                position["quantity"]
            )

            old_avg = float(
                position["avg_price"]
            )

            new_quantity = (
                old_quantity + quantity
            )

            new_avg = (
                (old_avg * old_quantity)
                + (price * quantity)
            ) / new_quantity

            position["quantity"] = new_quantity

            position["avg_price"] = new_avg

            position["last_update"] = now

        else:
            paper_account["positions"][key] = {
                "key": key,
                "index": index,
                "expiry": expiry,
                "strike": strike,
                "option_type": option_type,
                "quantity": quantity,
                "avg_price": price,
                "opened_at": now,
                "last_update": now,
            }

        paper_account["balance"] -= order_value

        paper_account["trades"].append({
            "timestamp": now,
            "action": "BUY",
            "index": index,
            "expiry": expiry,
            "strike": strike,
            "option_type": option_type,
            "quantity": quantity,
            "price": price,
            "value": order_value,
            "pnl": 0.0,
        })

    return jsonify({
        "status": "success",
        "message": (
            f"Paper BUY executed: "
            f"{option_type} {strike:g} "
            f"x {quantity} @ {price:.2f}"
        ),
        "account": _get_account_view(
            get_snapshots
        ),
    })


def _execute_sell(
    get_snapshots,
    get_current_index,
    get_current_expiry,
    option_type,
    strike,
    quantity,
):
    snapshot = _get_latest_snapshot(get_snapshots)

    if not snapshot:
        return jsonify({
            "status": "error",
            "message": (
                "No option-chain snapshot available"
            ),
        }), 400

    option = _find_option(
        snapshot,
        strike,
        option_type,
    )

    if not option:
        return jsonify({
            "status": "error",
            "message": (
                f"{option_type} {strike:g} "
                "is not available in the current snapshot"
            ),
        }), 400

    price = float(option["ltp"])

    if price <= 0:
        return jsonify({
            "status": "error",
            "message": (
                f"Invalid LTP for "
                f"{option_type} {strike:g}"
            ),
        }), 400

    index = snapshot.get(
        "index",
        get_current_index(),
    )

    expiry = snapshot.get(
        "expiry",
        get_current_expiry(),
    )

    key = _position_key(
        index,
        expiry,
        strike,
        option_type,
    )

    now = datetime.now().strftime(
        "%d-%b-%Y %I:%M:%S %p"
    )

    with paper_lock:
        position = paper_account["positions"].get(key)

        if not position:
            return jsonify({
                "status": "error",
                "message": (
                    "No open paper position "
                    "for this option"
                ),
            }), 400

        open_quantity = int(
            position["quantity"]
        )

        if quantity > open_quantity:
            return jsonify({
                "status": "error",
                "message": (
                    f"Only {open_quantity} "
                    "contracts are open"
                ),
            }), 400

        avg_price = float(
            position["avg_price"]
        )

        sell_value = price * quantity

        realized_pnl = (
            price - avg_price
        ) * quantity

        paper_account["balance"] += sell_value

        paper_account["realized_pnl"] += (
            realized_pnl
        )

        remaining = (
            open_quantity - quantity
        )

        if remaining == 0:
            del paper_account["positions"][key]
        else:
            position["quantity"] = remaining

            position["last_update"] = now

        paper_account["trades"].append({
            "timestamp": now,
            "action": "SELL",
            "index": index,
            "expiry": expiry,
            "strike": strike,
            "option_type": option_type,
            "quantity": quantity,
            "price": price,
            "value": sell_value,
            "pnl": realized_pnl,
        })

    return jsonify({
        "status": "success",
        "message": (
            f"Paper SELL executed: "
            f"{option_type} {strike:g} "
            f"x {quantity} @ {price:.2f}"
        ),
        "account": _get_account_view(
            get_snapshots
        ),
    })


def register_paper_trading(
    app,
    get_snapshots,
    get_current_index,
    get_current_expiry,
):

    @app.route("/paper-trading")
    def paper_trading_page():
        return render_template(
            "paper_trading.html"
        )

    @app.route("/api/paper-trading/account")
    def paper_trading_account():
        return jsonify({
            "status": "success",
            "account": _get_account_view(
                get_snapshots
            ),
            "index": get_current_index(),
            "expiry": get_current_expiry(),
        })

    @app.route("/api/paper-trading/market")
    def paper_trading_market():
        snapshot = _get_latest_snapshot(
            get_snapshots
        )

        if not snapshot:
            return jsonify({
                "status": "error",
                "message": (
                    "No option-chain snapshot available"
                ),
            }), 400

        rows = []

        for row in snapshot.get("rows", []):
            rows.append({
                "strike": _number(
                    row.get("strike")
                ),
                "ce_ltp": _number(
                    row.get("ce_ltp")
                ),
                "ce_change": _number(
                    row.get("ce_change")
                ),
                "ce_oi": _number(
                    row.get("ce_oi")
                ),
                "ce_oi_change": _number(
                    row.get("ce_oi_change")
                ),
                "ce_volume": _number(
                    row.get("ce_volume")
                ),
                "pe_ltp": _number(
                    row.get("pe_ltp")
                ),
                "pe_change": _number(
                    row.get("pe_change")
                ),
                "pe_oi": _number(
                    row.get("pe_oi")
                ),
                "pe_oi_change": _number(
                    row.get("pe_oi_change")
                ),
                "pe_volume": _number(
                    row.get("pe_volume")
                ),
            })

        return jsonify({
            "status": "success",
            "index": snapshot.get(
                "index",
                get_current_index(),
            ),
            "expiry": snapshot.get(
                "expiry",
                get_current_expiry(),
            ),
            "timestamp": snapshot.get(
                "timestamp"
            ),
            "spot": _number(
                snapshot.get("spot")
            ),
            "atm": _number(
                snapshot.get("atm")
            ),
            "rows": rows,
        })

    @app.route(
        "/api/paper-trading/reset",
        methods=["POST"],
    )
    def paper_trading_reset():
        with paper_lock:
            paper_account["balance"] = (
                paper_account["initial_balance"]
            )

            paper_account["realized_pnl"] = 0.0

            paper_account["trades"] = []

            paper_account["positions"] = {}

        return jsonify({
            "status": "success",
            "message": (
                "Paper trading account reset"
            ),
            "account": _get_account_view(
                get_snapshots
            ),
        })

    @app.route(
        "/api/paper-trading/buy",
        methods=["POST"],
    )
    def paper_trading_buy():
        data = request.get_json(
            silent=True
        ) or {}

        (
            option_type,
            strike,
            quantity,
            error,
        ) = _validate_order_request(data)

        if error:
            return jsonify({
                "status": "error",
                "message": error,
            }), 400

        return _execute_buy(
            get_snapshots,
            get_current_index,
            get_current_expiry,
            option_type,
            strike,
            quantity,
        )

    @app.route(
        "/api/paper-trading/sell",
        methods=["POST"],
    )
    def paper_trading_sell():
        data = request.get_json(
            silent=True
        ) or {}

        (
            option_type,
            strike,
            quantity,
            error,
        ) = _validate_order_request(data)

        if error:
            return jsonify({
                "status": "error",
                "message": error,
            }), 400

        return _execute_sell(
            get_snapshots,
            get_current_index,
            get_current_expiry,
            option_type,
            strike,
            quantity,
        )

    @app.route(
        "/api/paper-trading/order",
        methods=["POST"],
    )
    def paper_trading_order():
        data = request.get_json(
            silent=True
        ) or {}

        action = str(
            data.get("action", "")
        ).strip().upper()

        if action == "BUY":
            return paper_trading_buy()

        if action == "SELL":
            return paper_trading_sell()

        return jsonify({
            "status": "error",
            "message": (
                "Action must be BUY or SELL"
            ),
        }), 400