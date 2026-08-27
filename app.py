import os
import time
import threading
import requests
import pyotp
import csv
import io

from dotenv import load_dotenv
from datetime import datetime
from flask import Flask, render_template, jsonify, request, make_response
from SmartApi.smartConnect import SmartConnect

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)

from oi_treemap import register_oi_treemap
from paper_trading import register_paper_trading


load_dotenv()

app = Flask(__name__)


# ============================================================
# PAPER TRADING
# ============================================================

register_paper_trading(
    app,
    get_snapshots=lambda: SNAPSHOTS,
    get_current_index=lambda: CURRENT_INDEX,
    get_current_expiry=lambda: CURRENT_EXPIRY,
)
# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_CODE = os.getenv("ANGEL_CLIENT_CODE")
MPIN = os.getenv("ANGEL_MPIN")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

SCRIP_URL = (
    "https://margincalculator.angelone.in/"
    "OpenAPI_File/files/OpenAPIScripMaster.json"
)

REFRESH_INTERVAL = 180
STRIKES_EACH_SIDE = 5


# ============================================================
# INDEX CONFIGURATION
# ============================================================

INDEX_CONFIG = {

    "NIFTY": {
        "display_name": "NIFTY",
        "spot_exchange": "NSE",
        "spot_symbol": "NIFTY",
        "spot_token": "26000",
        "strike_interval": 50,
        "exchange_segment": "NFO",
        "instrument_type": "OPTIDX"
    },

    "BANKNIFTY": {
        "display_name": "BANKNIFTY",
        "spot_exchange": "NSE",
        "spot_symbol": "BANKNIFTY",
        "spot_token": "26009",
        "strike_interval": 100,
        "exchange_segment": "NFO",
        "instrument_type": "OPTIDX"
    },

    "GOLD": {
        "display_name": "GOLD",
        "spot_exchange": "MCX",
        "strike_interval": 100,
        "exchange_segment": "MCX",
        "instrument_type": "OPTFUT",
        "commodity": True
    },

    "SILVER": {
        "display_name": "SILVER",
        "spot_exchange": "MCX",
        "strike_interval": 1000,
        "exchange_segment": "MCX",
        "instrument_type": "OPTFUT",
        "commodity": True
    },

    "CRUDEOIL": {
        "display_name": "CRUDEOIL",
        "spot_exchange": "MCX",
        "strike_interval": 100,
        "exchange_segment": "MCX",
        "instrument_type": "OPTFUT",
        "commodity": True
    }

}


# ============================================================
# GLOBAL STATE
# ============================================================

smart = None
connected = False

SCRIPS = []

INDEX_EXPIRIES = {
    "NIFTY": [],
    "BANKNIFTY": [],
    "GOLD": [],
    "SILVER": [],
    "CRUDEOIL": []
}

INDEX_CONTRACTS = {
    "NIFTY": {},
    "BANKNIFTY": {}
}

COMMODITY_EXPIRIES = {
    "GOLD": [],
    "SILVER": [],
    "CRUDEOIL": []
}

COMMODITY_CONTRACTS = {
    "GOLD": {},
    "SILVER": {},
    "CRUDEOIL": {}
}

COMMODITY_SPOT_CONTRACTS = {
    "GOLD": None,
    "SILVER": None,
    "CRUDEOIL": None
}

CURRENT_INDEX = "NIFTY"

CURRENT_EXPIRY = None

SNAPSHOTS = []

SNAPSHOT_STORE = {
    "NIFTY": [],
    "BANKNIFTY": [],
    "GOLD": [],
    "SILVER": [],
    "CRUDEOIL": []
}

DATA_LOCK = threading.Lock()


# ============================================================
# REGISTER OI TREEMAP ROUTE
# ============================================================

register_oi_treemap(
    app,
    SNAPSHOTS,
    DATA_LOCK
)


# ============================================================
# EXPIRY PARSER
# ============================================================

def parse_expiry(expiry):

    if not expiry:
        return None

    expiry = str(expiry).strip().upper()

    formats = (
        "%d%b%Y",
        "%d-%b-%Y",
        "%d%b%y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y"
    )

    for fmt in formats:

        try:

            return datetime.strptime(
                expiry,
                fmt
            ).date()

        except ValueError:

            continue

    return None


def normalize_expiry(expiry):

    expiry_date = parse_expiry(
        expiry
    )

    if not expiry_date:
        return None

    return expiry_date.strftime(
        "%d%b%Y"
    ).upper()


# ============================================================
# LOAD ANGEL ONE SCRIP MASTER
# ============================================================

def load_scrip_master():

    global SCRIPS
    global INDEX_EXPIRIES
    global INDEX_CONTRACTS
    global COMMODITY_EXPIRIES
    global COMMODITY_CONTRACTS
    global COMMODITY_SPOT_CONTRACTS

    response = requests.get(
        SCRIP_URL,
        timeout=60
    )

    response.raise_for_status()

    SCRIPS = response.json()

    print(
        f"Loaded {len(SCRIPS)} instruments"
    )

    today = datetime.now().date()

    # ========================================================
    # RESET STORES
    # ========================================================

    for index_name in INDEX_EXPIRIES:

        INDEX_EXPIRIES[index_name] = []

    for index_name in INDEX_CONTRACTS:

        INDEX_CONTRACTS[index_name] = {}

    for commodity in COMMODITY_EXPIRIES:

        COMMODITY_EXPIRIES[commodity] = []

    for commodity in COMMODITY_CONTRACTS:

        COMMODITY_CONTRACTS[commodity] = {}

    for commodity in COMMODITY_SPOT_CONTRACTS:

        COMMODITY_SPOT_CONTRACTS[commodity] = None


    # ========================================================
    # NIFTY / BANKNIFTY
    # ========================================================

    for index_name in (
        "NIFTY",
        "BANKNIFTY"
    ):

        expiry_dates = {}
        contracts = {}

        for scrip in SCRIPS:

            exch_seg = str(
                scrip.get(
                    "exch_seg",
                    ""
                )
            ).strip().upper()

            if exch_seg != "NFO":
                continue

            instrument_type = str(
                scrip.get(
                    "instrumenttype",
                    ""
                )
            ).strip().upper()

            if instrument_type != "OPTIDX":
                continue

            name = str(
                scrip.get(
                    "name",
                    ""
                )
            ).strip().upper()

            symbol = str(
                scrip.get(
                    "symbol",
                    ""
                )
            ).strip().upper()

            if index_name == "NIFTY":

                valid_index = (
                    name in (
                        "NIFTY",
                        "NIFTY 50"
                    )
                    or symbol.startswith("NIFTY")
                )

            else:

                valid_index = (
                    name == "BANKNIFTY"
                    or symbol.startswith("BANKNIFTY")
                )

            if not valid_index:
                continue

            expiry_date = parse_expiry(
                scrip.get("expiry")
            )

            if not expiry_date:
                continue

            if expiry_date < today:
                continue

            expiry = expiry_date.strftime(
                "%d%b%Y"
            ).upper()

            expiry_dates[
                expiry_date
            ] = expiry

            try:

                strike = (
                    float(
                        scrip["strike"]
                    ) / 100
                )

            except (
                ValueError,
                TypeError,
                KeyError
            ):

                continue

            if not symbol.endswith(
                ("CE", "PE")
            ):
                continue

            option_type = (
                "CE"
                if symbol.endswith("CE")
                else "PE"
            )

            contracts[
                (
                    expiry,
                    strike,
                    option_type
                )
            ] = scrip

        INDEX_EXPIRIES[index_name] = [
            expiry_dates[d]
            for d in sorted(expiry_dates)
        ]

        INDEX_CONTRACTS[index_name] = contracts

        print(
            f"{index_name} EXPIRIES: "
            f"{len(INDEX_EXPIRIES[index_name])}"
        )

        for expiry in INDEX_EXPIRIES[index_name]:

            print(
                f"  {expiry}"
            )


    # ========================================================
    # GOLD / SILVER / CRUDEOIL
    # ========================================================

    for commodity in (
        "GOLD",
        "SILVER",
        "CRUDEOIL"
    ):

        expiry_dates = {}
        contracts = {}

        for scrip in SCRIPS:

            exch_seg = str(
                scrip.get(
                    "exch_seg",
                    ""
                )
            ).strip().upper()

            if exch_seg != "MCX":
                continue

            instrument_type = str(
                scrip.get(
                    "instrumenttype",
                    ""
                )
            ).strip().upper()

            if instrument_type != "OPTFUT":
                continue

            name = str(
                scrip.get(
                    "name",
                    ""
                )
            ).strip().upper()

            symbol = str(
                scrip.get(
                    "symbol",
                    ""
                )
            ).strip().upper()

            if (
                name != commodity
                and not symbol.startswith(commodity)
            ):
                continue

            expiry_date = parse_expiry(
                scrip.get("expiry")
            )

            if not expiry_date:
                continue

            if expiry_date < today:
                continue

            expiry = expiry_date.strftime(
                "%d%b%Y"
            ).upper()

            expiry_dates[
                expiry_date
            ] = expiry

            try:

                strike = (
                    float(
                        scrip["strike"]
                    ) / 100
                )

            except (
                ValueError,
                TypeError,
                KeyError
            ):

                continue

            if not symbol.endswith(
                ("CE", "PE")
            ):
                continue

            option_type = (
                "CE"
                if symbol.endswith("CE")
                else "PE"
            )

            contracts[
                (
                    expiry,
                    strike,
                    option_type
                )
            ] = scrip

        COMMODITY_EXPIRIES[commodity] = [
            expiry_dates[d]
            for d in sorted(expiry_dates)
        ]

        COMMODITY_CONTRACTS[commodity] = contracts

        print(
            f"{commodity} EXPIRIES: "
            f"{len(COMMODITY_EXPIRIES[commodity])}"
        )

        for expiry in COMMODITY_EXPIRIES[commodity]:

            print(
                f"  {expiry}"
            )


    # ========================================================
    # COMMODITY SPOT / NEAREST FUTURE
    # ========================================================

    for commodity in (
        "GOLD",
        "SILVER",
        "CRUDEOIL"
    ):

        futures = []

        for scrip in SCRIPS:

            exch_seg = str(
                scrip.get(
                    "exch_seg",
                    ""
                )
            ).strip().upper()

            if exch_seg != "MCX":
                continue

            instrument_type = str(
                scrip.get(
                    "instrumenttype",
                    ""
                )
            ).strip().upper()

            if instrument_type not in (
                "FUTCOM",
                "FUTENR"
            ):
                continue

            name = str(
                scrip.get(
                    "name",
                    ""
                )
            ).strip().upper()

            symbol = str(
                scrip.get(
                    "symbol",
                    ""
                )
            ).strip().upper()

            if (
                name != commodity
                and not symbol.startswith(commodity)
            ):
                continue

            expiry_date = parse_expiry(
                scrip.get("expiry")
            )

            if not expiry_date:
                continue

            if expiry_date < today:
                continue

            futures.append(
                (
                    expiry_date,
                    scrip
                )
            )

        futures.sort(
            key=lambda item: item[0]
        )

        if futures:

            COMMODITY_SPOT_CONTRACTS[
                commodity
            ] = futures[0][1]

            print(
                f"{commodity} SPOT FUTURE: "
                f"{futures[0][1].get('symbol', '')}"
            )


# ============================================================
# GET EXPIRIES
# ============================================================

def get_expiries(index_name=None):

    if index_name is None:
        index_name = CURRENT_INDEX

    if index_name in (
        "GOLD",
        "SILVER",
        "CRUDEOIL"
    ):

        return list(
            COMMODITY_EXPIRIES.get(
                index_name,
                []
            )
        )

    return list(
        INDEX_EXPIRIES.get(
            index_name,
            []
        )
    )


def get_latest_expiry(index_name=None):

    expiries = get_expiries(
        index_name
    )

    if not expiries:
        return None

    return expiries[0]


# ============================================================
# GET CURRENT INDEX CONFIG
# ============================================================

def get_index_config(index_name=None):

    if index_name is None:
        index_name = CURRENT_INDEX

    config = INDEX_CONFIG.get(
        index_name
    )

    if not config:

        raise Exception(
            f"Unsupported index: {index_name}"
        )

    return config


# ============================================================
# GET INDEX SPOT
# ============================================================

def get_index_spot(index_name=None):

    if not smart:
        return None

    if index_name is None:
        index_name = CURRENT_INDEX

    config = get_index_config(
        index_name
    )

    # ========================================================
    # NIFTY / BANKNIFTY
    # ========================================================

    if not config.get(
        "commodity",
        False
    ):

        response = smart.ltpData(
            config["spot_exchange"],
            config["spot_symbol"],
            config["spot_token"]
        )

        if not response.get("status"):

            raise Exception(
                response.get(
                    "message",
                    f"Unable to fetch "
                    f"{index_name} spot"
                )
            )

        return float(
            response["data"]["ltp"]
        )


    # ========================================================
    # COMMODITY
    # ========================================================

    contract = COMMODITY_SPOT_CONTRACTS.get(
        index_name
    )

    if not contract:

        raise Exception(
            f"No MCX future found for {index_name}"
        )

    response = smart.ltpData(
        "MCX",
        contract.get("symbol"),
        str(contract.get("token"))
    )

    if not response.get("status"):

        raise Exception(
            response.get(
                "message",
                f"Unable to fetch "
                f"{index_name} spot"
            )
        )

    return float(
        response["data"]["ltp"]
    )


# ============================================================
# BACKWARD COMPATIBILITY
# ============================================================

def get_nifty_spot():

    return get_index_spot(
        "NIFTY"
    )


# ============================================================
# ATM STRIKE
# ============================================================

def calculate_atm(
    spot,
    index_name=None
):

    if index_name is None:
        index_name = CURRENT_INDEX

    config = get_index_config(
        index_name
    )

    strike_interval = config[
        "strike_interval"
    ]

    return round(
        spot / strike_interval
    ) * strike_interval


def get_required_strikes(
    spot,
    index_name=None
):

    if index_name is None:
        index_name = CURRENT_INDEX

    config = get_index_config(
        index_name
    )

    strike_interval = config[
        "strike_interval"
    ]

    atm = calculate_atm(
        spot,
        index_name
    )

    return [
        atm + (
            offset * strike_interval
        )
        for offset in range(
            -STRIKES_EACH_SIDE,
            STRIKES_EACH_SIDE + 1
        )
    ]


# ============================================================
# FIND OPTION CONTRACTS
# ============================================================

def get_option_contracts(
    expiry,
    strikes,
    index_name=None
):

    if index_name is None:
        index_name = CURRENT_INDEX

    if index_name in (
        "GOLD",
        "SILVER",
        "CRUDEOIL"
    ):

        contracts_master = COMMODITY_CONTRACTS.get(
            index_name,
            {}
        )

    else:

        contracts_master = INDEX_CONTRACTS.get(
            index_name,
            {}
        )

    strike_set = set(
        strikes
    )

    contracts = {}

    for strike in strike_set:

        ce = contracts_master.get(
            (
                expiry,
                strike,
                "CE"
            )
        )

        pe = contracts_master.get(
            (
                expiry,
                strike,
                "PE"
            )
        )

        if ce:

            contracts[
                (strike, "CE")
            ] = ce

        if pe:

            contracts[
                (strike, "PE")
            ] = pe

    return contracts


# ============================================================
# FETCH OPTION MARKET DATA
# ============================================================

def fetch_option_data(
    expiry,
    strikes,
    index_name=None
):

    if index_name is None:
        index_name = CURRENT_INDEX

    contracts = get_option_contracts(
        expiry,
        strikes,
        index_name
    )

    token_map = {}

    for contract in contracts.values():

        token = contract.get(
            "token"
        )

        if token:

            token_map[
                str(token)
            ] = contract

    if not token_map:

        raise Exception(
            f"No {index_name} option contracts "
            f"found for expiry {expiry}"
        )

    tokens = list(
        token_map.keys()
    )

    fetched = []

    exchange_segment = (
        "MCX"
        if index_name in (
            "GOLD",
            "SILVER",
            "CRUDEOIL"
        )
        else "NFO"
    )

    for start in range(
        0,
        len(tokens),
        50
    ):

        batch = tokens[
            start:start + 50
        ]

        response = smart.getMarketData(
            "FULL",
            {
                exchange_segment: batch
            }
        )

        if not response.get("status"):

            raise Exception(
                response.get(
                    "message",
                    "Unable to fetch "
                    "option market data"
                )
            )

        fetched.extend(
            response.get(
                "data",
                {}
            ).get(
                "fetched",
                []
            )
        )

    market_data = {}

    for quote in fetched:

        token = str(
            quote.get(
                "symbolToken",
                ""
            )
        )

        contract = token_map.get(
            token
        )

        if not contract:
            continue

        strike = (
            float(
                contract["strike"]
            ) / 100
        )

        symbol = str(
            contract.get(
                "symbol",
                ""
            )
        ).upper()

        option_type = (
            "CE"
            if symbol.endswith("CE")
            else "PE"
        )

        market_data[
            (strike, option_type)
        ] = quote

    return market_data


# ============================================================
# BUILD SNAPSHOT
# ============================================================

def build_snapshot():

    global CURRENT_EXPIRY

    if not connected:

        raise Exception(
            "Angel One is disconnected"
        )

    index_name = CURRENT_INDEX

    spot = get_index_spot(
        index_name
    )

    if spot is None:

        raise Exception(
            f"Unable to get "
            f"{index_name} spot"
        )

    atm = calculate_atm(
        spot,
        index_name
    )

    strikes = get_required_strikes(
        spot,
        index_name
    )

    expiry = CURRENT_EXPIRY

    available_expiries = get_expiries(
        index_name
    )

    if expiry not in available_expiries:

        expiry = get_latest_expiry(
            index_name
        )

        CURRENT_EXPIRY = expiry

    if not expiry:

        raise Exception(
            f"No {index_name} expiry available"
        )

    market_data = fetch_option_data(
        expiry,
        strikes,
        index_name
    )

    rows = []

    for strike in strikes:

        ce = market_data.get(
            (strike, "CE"),
            {}
        )

        pe = market_data.get(
            (strike, "PE"),
            {}
        )

        rows.append({

            "strike": strike,

            "ce_ltp": ce.get(
                "ltp",
                ""
            ),

            "ce_change": ce.get(
                "netChange",
                ""
            ),

            "ce_oi": ce.get(
                "opnInterest",
                ""
            ),

            "ce_oi_change": ce.get(
                "oiChange",
                ""
            ),

            "ce_volume": ce.get(
                "tradeVolume",
                ""
            ),

            "pe_ltp": pe.get(
                "ltp",
                ""
            ),

            "pe_change": pe.get(
                "netChange",
                ""
            ),

            "pe_oi": pe.get(
                "opnInterest",
                ""
            ),

            "pe_oi_change": pe.get(
                "oiChange",
                ""
            ),

            "pe_volume": pe.get(
                "tradeVolume",
                ""
            )

        })

    return {

        "index": index_name,

        "timestamp": datetime.now().strftime(
            "%d-%b-%Y %I:%M:%S %p"
        ),

        "spot": spot,

        "atm": atm,

        "expiry": expiry,

        "rows": rows

    }


# ============================================================
# ADD SNAPSHOT
# ============================================================

def create_snapshot():

    snapshot = build_snapshot()

    index_name = snapshot[
        "index"
    ]

    with DATA_LOCK:

        if index_name not in SNAPSHOT_STORE:

            SNAPSHOT_STORE[
                index_name
            ] = []

        SNAPSHOT_STORE[
            index_name
        ].insert(
            0,
            snapshot
        )

        SNAPSHOTS[:] = SNAPSHOT_STORE[
            index_name
        ]

    return snapshot


# ============================================================
# SWITCH INDEX SNAPSHOT STORE
# ============================================================

def switch_snapshot_store(
    index_name
):

    with DATA_LOCK:

        SNAPSHOTS[:] = SNAPSHOT_STORE.get(
            index_name,
            []
        )


# ============================================================
# BACKGROUND REFRESH
# ============================================================

def refresh_worker():

    while True:

        time.sleep(
            REFRESH_INTERVAL
        )

        if not connected:
            continue

        try:

            create_snapshot()

            print(
                f"3-minute "
                f"{CURRENT_INDEX} snapshot added"
            )

        except Exception as exc:

            print(
                f"Automatic refresh failed: {exc}"
            )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def index():

    with DATA_LOCK:

        snapshots = list(
            SNAPSHOTS
        )

    return render_template(
        "index.html",
        snapshots=snapshots,
        indexes=list(
            INDEX_CONFIG.keys()
        ),
        selected_index=CURRENT_INDEX,
        expiries=get_expiries(
            CURRENT_INDEX
        ),
        selected_expiry=CURRENT_EXPIRY,
        connected=connected
    )


# ============================================================
# INDEX API
# ============================================================

@app.route("/api/indexes")
def api_indexes():

    return jsonify({

        "status": "success",

        "indexes": list(
            INDEX_CONFIG.keys()
        ),

        "selected_index": CURRENT_INDEX

    })


# ============================================================
# EXPIRY API
# ============================================================

@app.route("/api/expiries")
def api_expiries():

    return jsonify({

        "status": "success",

        "index": CURRENT_INDEX,

        "expiries": get_expiries(
            CURRENT_INDEX
        ),

        "selected_expiry": CURRENT_EXPIRY

    })


# ============================================================
# STATUS
# ============================================================

@app.route("/status")
def status():

    return jsonify({

        "connected": connected,

        "index": CURRENT_INDEX,

        "expiry": CURRENT_EXPIRY,

        "expiries": get_expiries(
            CURRENT_INDEX
        ),

        "indexes": list(
            INDEX_CONFIG.keys()
        ),

        "snapshots": len(
            SNAPSHOTS
        )

    })


# ============================================================
# CONNECT / DISCONNECT
# ============================================================

@app.route("/connect-toggle")
def connect_toggle():

    global smart
    global connected
    global CURRENT_INDEX
    global CURRENT_EXPIRY

    if connected:

        smart = None

        connected = False

        CURRENT_EXPIRY = None

        return jsonify({

            "status": "disconnected"

        })

    try:

        if not API_KEY:

            raise Exception(
                "ANGEL_API_KEY is not configured"
            )

        if not CLIENT_CODE:

            raise Exception(
                "ANGEL_CLIENT_CODE is not configured"
            )

        if not MPIN:

            raise Exception(
                "ANGEL_MPIN is not configured"
            )

        if not TOTP_SECRET:

            raise Exception(
                "ANGEL_TOTP_SECRET is not configured"
            )

        smart = SmartConnect(
            api_key=API_KEY
        )

        totp = pyotp.TOTP(
            TOTP_SECRET
        ).now()

        session = smart.generateSession(
            CLIENT_CODE,
            MPIN,
            totp
        )

        if not session.get("status"):

            smart = None

            raise Exception(
                session.get(
                    "message",
                    "Angel One login failed"
                )
            )

        connected = True

        CURRENT_INDEX = "NIFTY"

        CURRENT_EXPIRY = get_latest_expiry(
            CURRENT_INDEX
        )

        switch_snapshot_store(
            CURRENT_INDEX
        )

        create_snapshot()

        return jsonify({

            "status": "connected",

            "index": CURRENT_INDEX,

            "expiry": CURRENT_EXPIRY,

            "expiries": get_expiries(
                CURRENT_INDEX
            ),

            "indexes": list(
                INDEX_CONFIG.keys()
            )

        })

    except Exception as exc:

        smart = None

        connected = False

        CURRENT_EXPIRY = None

        return jsonify({

            "status": "error",

            "message": str(exc)

        })


# ============================================================
# CHANGE INDEX
# ============================================================

@app.route("/set-index")
def set_index():

    global CURRENT_INDEX
    global CURRENT_EXPIRY

    if not connected:

        return jsonify({

            "status": "error",

            "message": "Angel One is disconnected"

        }), 400

    index_name = request.args.get(
        "index",
        ""
    ).strip().upper()

    if index_name not in INDEX_CONFIG:

        return jsonify({

            "status": "error",

            "message": "Invalid index",

            "available_indexes": list(
                INDEX_CONFIG.keys()
            )

        }), 400

    try:

        CURRENT_INDEX = index_name

        CURRENT_EXPIRY = get_latest_expiry(
            CURRENT_INDEX
        )

        switch_snapshot_store(
            CURRENT_INDEX
        )

        snapshot = create_snapshot()

        return jsonify({

            "status": "success",

            "index": CURRENT_INDEX,

            "expiry": CURRENT_EXPIRY,

            "expiries": get_expiries(
                CURRENT_INDEX
            ),

            "snapshot": snapshot

        })

    except Exception as exc:

        return jsonify({

            "status": "error",

            "message": str(exc)

        }), 500


# ============================================================
# MANUAL REFRESH
# ============================================================

@app.route("/refresh")
def manual_refresh():

    if not connected:

        return jsonify({

            "status": "error",

            "message": "Angel One is disconnected"

        }), 400

    try:

        snapshot = create_snapshot()

        return jsonify({

            "status": "success",

            "snapshot": snapshot

        })

    except Exception as exc:

        return jsonify({

            "status": "error",

            "message": str(exc)

        }), 500


# ============================================================
# CHANGE EXPIRY
# ============================================================

@app.route("/set-expiry")
def set_expiry():

    global CURRENT_EXPIRY

    if not connected:

        return jsonify({

            "status": "error",

            "message": "Angel One is disconnected"

        }), 400

    expiry = request.args.get(
        "expiry",
        ""
    ).strip().upper()

    if not expiry:

        return jsonify({

            "status": "error",

            "message": "Expiry is required"

        }), 400

    expiry_date = parse_expiry(
        expiry
    )

    if not expiry_date:

        return jsonify({

            "status": "error",

            "message": "Invalid expiry"

        }), 400

    expiry = expiry_date.strftime(
        "%d%b%Y"
    ).upper()

    available_expiries = get_expiries(
        CURRENT_INDEX
    )

    if expiry not in available_expiries:

        return jsonify({

            "status": "error",

            "message": "Invalid expiry",

            "available_expiries":
                available_expiries

        }), 400

    CURRENT_EXPIRY = expiry

    try:

        snapshot = create_snapshot()

        return jsonify({

            "status": "success",

            "index": CURRENT_INDEX,

            "expiry": CURRENT_EXPIRY,

            "snapshot": snapshot

        })

    except Exception as exc:

        return jsonify({

            "status": "error",

            "message": str(exc)

        }), 500


# ============================================================
# API: SNAPSHOTS
# ============================================================

@app.route("/api/snapshots")
def api_snapshots():

    with DATA_LOCK:

        snapshots = list(
            SNAPSHOTS
        )

    return jsonify(
        snapshots
    )


# ============================================================
# API: SPOT
# ============================================================

@app.route("/api/spot")
def api_spot():

    if not connected:

        return jsonify({

            "index": CURRENT_INDEX,

            "spot": None,

            "atm": None

        })

    try:

        spot = get_index_spot(
            CURRENT_INDEX
        )

        return jsonify({

            "index": CURRENT_INDEX,

            "spot": spot,

            "atm": calculate_atm(
                spot,
                CURRENT_INDEX
            )

        })

    except Exception as exc:

        return jsonify({

            "index": CURRENT_INDEX,

            "spot": None,

            "atm": None,

            "error": str(exc)

        }), 500


# ============================================================
# DOWNLOAD CSV
# ============================================================

@app.route("/download-oi")
def download_oi():

    with DATA_LOCK:

        snapshots = list(
            SNAPSHOTS
        )

    if not snapshots:

        return jsonify({

            "status": "error",

            "message":
                f"No {CURRENT_INDEX} "
                f"Option Chain data available"

        }), 400

    output = io.StringIO()

    writer = csv.writer(
        output
    )

    writer.writerow([

        "Index",
        "Timestamp",
        "Expiry",
        "Spot",
        "ATM",
        "Strike",

        "CE LTP",
        "CE Change",
        "CE OI",
        "CE OI Change",
        "CE Volume",

        "PE LTP",
        "PE Change",
        "PE OI",
        "PE OI Change",
        "PE Volume"

    ])

    for snapshot in snapshots:

        for row in snapshot.get(
            "rows",
            []
        ):

            writer.writerow([

                snapshot.get(
                    "index",
                    CURRENT_INDEX
                ),

                snapshot.get(
                    "timestamp",
                    ""
                ),

                snapshot.get(
                    "expiry",
                    ""
                ),

                snapshot.get(
                    "spot",
                    ""
                ),

                snapshot.get(
                    "atm",
                    ""
                ),

                row.get(
                    "strike",
                    ""
                ),

                row.get(
                    "ce_ltp",
                    ""
                ),

                row.get(
                    "ce_change",
                    ""
                ),

                row.get(
                    "ce_oi",
                    ""
                ),

                row.get(
                    "ce_oi_change",
                    ""
                ),

                row.get(
                    "ce_volume",
                    ""
                ),

                row.get(
                    "pe_ltp",
                    ""
                ),

                row.get(
                    "pe_change",
                    ""
                ),

                row.get(
                    "pe_oi",
                    ""
                ),

                row.get(
                    "pe_oi_change",
                    ""
                ),

                row.get(
                    "pe_volume",
                    ""
                )

            ])

    csv_data = output.getvalue()

    output.close()

    response = make_response(
        csv_data
    )

    response.headers[
        "Content-Type"
    ] = "text/csv; charset=utf-8"

    response.headers[
        "Content-Disposition"
    ] = (
        "attachment; "
        f"filename={CURRENT_INDEX.lower()}_"
        "option_chain.csv"
    )

    return response


# ============================================================
# DOWNLOAD PDF
# ============================================================

@app.route("/download-oi-pdf")
def download_oi_pdf():

    with DATA_LOCK:

        snapshots = list(
            SNAPSHOTS
        )

    if not snapshots:

        return jsonify({

            "status": "error",

            "message":
                f"No {CURRENT_INDEX} "
                f"Option Chain data available"

        }), 400

    output = io.BytesIO()

    document = SimpleDocTemplate(

        output,

        pagesize=landscape(A4),

        rightMargin=20,

        leftMargin=20,

        topMargin=20,

        bottomMargin=20

    )

    styles = getSampleStyleSheet()

    elements = []

    elements.append(
        Paragraph(
            f"{CURRENT_INDEX} Option Chain",
            styles["Title"]
        )
    )

    elements.append(
        Spacer(
            1,
            10
        )
    )

    for snapshot in snapshots:

        elements.append(
            Paragraph(
                f"Timestamp: "
                f"{snapshot.get('timestamp', '')}",
                styles["Normal"]
            )
        )

        elements.append(
            Paragraph(
                f"Index: "
                f"{snapshot.get('index', CURRENT_INDEX)}"
                f"&nbsp;&nbsp;&nbsp;"
                f"Expiry: "
                f"{snapshot.get('expiry', '')}"
                f"&nbsp;&nbsp;&nbsp;"
                f"Spot: "
                f"{snapshot.get('spot', '')}"
                f"&nbsp;&nbsp;&nbsp;"
                f"ATM: "
                f"{snapshot.get('atm', '')}",
                styles["Normal"]
            )
        )

        elements.append(
            Spacer(
                1,
                8
            )
        )

        data = [[

            "CE LTP",
            "CE Change",
            "CE OI",
            "CE OI Change",
            "CE Volume",

            "STRIKE",

            "PE LTP",
            "PE Change",
            "PE OI",
            "PE OI Change",
            "PE Volume"

        ]]

        for row in snapshot.get(
            "rows",
            []
        ):

            data.append([

                row.get(
                    "ce_ltp",
                    ""
                ),

                row.get(
                    "ce_change",
                    ""
                ),

                row.get(
                    "ce_oi",
                    ""
                ),

                row.get(
                    "ce_oi_change",
                    ""
                ),

                row.get(
                    "ce_volume",
                    ""
                ),

                row.get(
                    "strike",
                    ""
                ),

                row.get(
                    "pe_ltp",
                    ""
                ),

                row.get(
                    "pe_change",
                    ""
                ),

                row.get(
                    "pe_oi",
                    ""
                ),

                row.get(
                    "pe_oi_change",
                    ""
                ),

                row.get(
                    "pe_volume",
                    ""
                )

            ])

        table = Table(
            data,
            repeatRows=1
        )

        table.setStyle(
            TableStyle([

                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.lightgrey
                ),

                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.black
                ),

                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold"
                ),

                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER"
                ),

                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey
                ),

                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    7
                ),

                (
                    "BACKGROUND",
                    (5, 1),
                    (5, -1),
                    colors.lightyellow
                ),

                (
                    "FONTNAME",
                    (5, 1),
                    (5, -1),
                    "Helvetica-Bold"
                )

            ])
        )

        elements.append(
            table
        )

        elements.append(
            Spacer(
                1,
                20
            )
        )

    document.build(
        elements
    )

    pdf_data = output.getvalue()

    output.close()

    response = make_response(
        pdf_data
    )

    response.headers[
        "Content-Type"
    ] = "application/pdf"

    response.headers[
        "Content-Disposition"
    ] = (
        "attachment; "
        f"filename={CURRENT_INDEX.lower()}_"
        "option_chain.pdf"
    )

    return response


# ============================================================
# REGISTER OI CHANGE ROUTE
# ============================================================

from oi_change import register_oi_change

register_oi_change(
    app,
    SNAPSHOTS,
    DATA_LOCK
)


# ============================================================
# STARTUP
# ============================================================

def initialize():

    try:

        load_scrip_master()

    except Exception as exc:

        print(
            f"Scrip master loading failed: {exc}"
        )


initialize()


threading.Thread(
    target=refresh_worker,
    daemon=True
).start()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False
    )