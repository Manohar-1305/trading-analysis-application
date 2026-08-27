let marketData = null;
let currentIndex = "NIFTY";

const AVAILABLE_INDEXES = ["NIFTY", "BANKNIFTY", "GOLD", "SILVER", "CRUDEOIL"];

const LOT_SIZES = {
  NIFTY: 65,
  BANKNIFTY: 30,
  GOLD: 100,
  SILVER: 30,
  CRUDEOIL: 100,
};

function number(value) {
  const parsed = Number(
    String(value ?? "")
      .replace(/,/g, "")
      .trim(),
  );

  return Number.isFinite(parsed) ? parsed : 0;
}

function getLotSize(index) {
  return LOT_SIZES[String(index || currentIndex).toUpperCase()] || 1;
}

function formatNumber(value, decimals = 2) {
  return number(value).toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatInteger(value) {
  return number(value).toLocaleString("en-IN", {
    maximumFractionDigits: 0,
  });
}

function formatPnl(value) {
  const amount = number(value);

  if (amount > 0) {
    return (
      '<span class="positive-pnl">' + "+" + formatNumber(amount) + "</span>"
    );
  }

  if (amount < 0) {
    return '<span class="negative-pnl">' + formatNumber(amount) + "</span>";
  }

  return '<span class="neutral-pnl">0.00</span>';
}

function setStatus(message) {
  document.getElementById("statusMessage").textContent = message;
}

function populateIndexes(selectedIndex) {
  const select = document.getElementById("indexFilter");

  select.innerHTML = "";

  AVAILABLE_INDEXES.forEach(function (index) {
    const option = document.createElement("option");

    option.value = index;
    option.textContent = index;

    if (index === selectedIndex) {
      option.selected = true;
    }

    select.appendChild(option);
  });
}

function populateExpiries(expiries, selectedExpiry) {
  const select = document.getElementById("expiry");

  select.innerHTML = "";

  if (!expiries || expiries.length === 0) {
    const option = document.createElement("option");

    option.value = "";
    option.textContent = "No expiry available";

    select.appendChild(option);

    return;
  }

  expiries.forEach(function (expiry) {
    const option = document.createElement("option");

    option.value = expiry;
    option.textContent = expiry;

    if (expiry === selectedExpiry) {
      option.selected = true;
    }

    select.appendChild(option);
  });
}

function updatePageTitle(index) {
  document.title = index + " Paper Trading";

  document.getElementById("pageHeading").textContent = index + " Paper Trading";
}

async function changeIndex() {
  const select = document.getElementById("indexFilter");
  const index = select.value;

  if (!index) {
    return;
  }

  if (!AVAILABLE_INDEXES.includes(index)) {
    return;
  }

  localStorage.setItem("selectedIndex", index);

  document.body.classList.add("index-loading");

  try {
    const response = await fetch(
      "/set-index?index=" + encodeURIComponent(index),
    );

    const data = await response.json();

    if (data.status !== "success") {
      setStatus(data.message || "Unable to change index");
      return;
    }

    currentIndex = data.index;

    localStorage.setItem("selectedIndex", data.index);

    updatePageTitle(data.index);

    populateIndexes(data.index);

    populateExpiries(data.expiries, data.expiry);

    window.location.reload();
  } catch (error) {
    console.error(error);

    setStatus("Unable to change index");
  } finally {
    document.body.classList.remove("index-loading");
  }
}

async function changeExpiry() {
  const expiry = document.getElementById("expiry").value;

  if (!expiry) {
    return;
  }

  try {
    setStatus("Changing expiry...");

    const response = await fetch(
      "/set-expiry?expiry=" + encodeURIComponent(expiry),
    );

    const data = await response.json();

    if (data.status !== "success") {
      setStatus(data.message || "Unable to change expiry");
      return;
    }

    await loadMarket();
    await loadAccount();

    setStatus("Paper trading market updated");
  } catch (error) {
    console.error(error);

    setStatus("Unable to change expiry");
  }
}

async function loadMarket() {
  try {
    const response = await fetch("/api/paper-trading/market?_=" + Date.now(), {
      cache: "no-store",
    });

    const data = await response.json();

    if (data.status !== "success") {
      setStatus(data.message || "Unable to load market data");
      return;
    }

    marketData = data;

    currentIndex = data.index || currentIndex;

    populateIndexes(currentIndex);

    const lotSize = Number(data.lot_size || getLotSize(currentIndex));

    document.getElementById("marketInfo").textContent =
      data.index +
      " | Expiry: " +
      data.expiry +
      " | Spot: " +
      formatNumber(data.spot) +
      " | ATM: " +
      formatNumber(data.atm, 0) +
      " | Lot Size: " +
      formatInteger(lotSize) +
      " | " +
      data.timestamp;

    renderMarket(data.rows, lotSize);

    setStatus("Paper trading only. No real Angel One order is placed.");

    await loadAccount();
  } catch (error) {
    console.error(error);

    setStatus("Unable to load paper-trading market data");
  }
}

function createQuantityInput() {
  const input = document.createElement("input");

  input.type = "number";
  input.min = "1";
  input.step = "1";
  input.value = "1";
  input.className = "quantity-input";

  return input;
}

function renderMarket(rows, lotSize) {
  const body = document.getElementById("marketBody");

  body.innerHTML = "";

  if (!rows || rows.length === 0) {
    body.innerHTML =
      "<tr>" +
      '<td colspan="11">' +
      "No option-chain data available" +
      "</td>" +
      "</tr>";

    return;
  }

  rows.forEach(function (row) {
    const tr = document.createElement("tr");

    tr.innerHTML =
      '<td class="ce-cell">' +
      formatNumber(row.ce_ltp) +
      "</td>" +
      '<td class="ce-cell">' +
      formatNumber(row.ce_change) +
      "</td>" +
      '<td class="ce-cell">' +
      formatNumber(row.ce_oi, 0) +
      "</td>" +
      '<td class="ce-cell">' +
      formatNumber(row.ce_volume, 0) +
      "</td>";

    const ceAction = document.createElement("td");

    ceAction.className = "ce-cell action-cell";

    const ceActionRow = document.createElement("div");

    ceActionRow.className = "action-row";

    const ceQuantity = createQuantityInput();

    ceQuantity.title = "Lots. 1 lot = " + lotSize + " units";

    const ceBuy = document.createElement("button");

    ceBuy.type = "button";
    ceBuy.className = "paper-button buy-button";
    ceBuy.textContent = "BUY";
    ceBuy.title = "BUY CE";

    ceBuy.onclick = function () {
      placeOrder("BUY", "CE", row.strike, ceQuantity.value);
    };

    const ceSell = document.createElement("button");

    ceSell.type = "button";
    ceSell.className = "paper-button sell-button";
    ceSell.textContent = "SELL";
    ceSell.title = "SELL CE";

    ceSell.onclick = function () {
      placeOrder("SELL", "CE", row.strike, ceQuantity.value);
    };

    ceActionRow.appendChild(ceQuantity);
    ceActionRow.appendChild(ceBuy);
    ceActionRow.appendChild(ceSell);

    ceAction.appendChild(ceActionRow);

    tr.appendChild(ceAction);

    const strikeCell = document.createElement("td");

    strikeCell.className = "strike-cell";
    strikeCell.textContent = formatNumber(row.strike, 0);

    tr.appendChild(strikeCell);

    const peValues = [row.pe_ltp, row.pe_change, row.pe_oi, row.pe_volume];

    peValues.forEach(function (value, index) {
      const td = document.createElement("td");

      td.className = "pe-cell";

      td.textContent = formatNumber(value, index >= 2 ? 0 : 2);

      tr.appendChild(td);
    });

    const peAction = document.createElement("td");

    peAction.className = "pe-cell action-cell";

    const peActionRow = document.createElement("div");

    peActionRow.className = "action-row";

    const peQuantity = createQuantityInput();

    peQuantity.title = "Lots. 1 lot = " + lotSize + " units";

    const peBuy = document.createElement("button");

    peBuy.type = "button";
    peBuy.className = "paper-button buy-button";
    peBuy.textContent = "BUY";
    peBuy.title = "BUY PE";

    peBuy.onclick = function () {
      placeOrder("BUY", "PE", row.strike, peQuantity.value);
    };

    const peSell = document.createElement("button");

    peSell.type = "button";
    peSell.className = "paper-button sell-button";
    peSell.textContent = "SELL";
    peSell.title = "SELL PE";

    peSell.onclick = function () {
      placeOrder("SELL", "PE", row.strike, peQuantity.value);
    };

    peActionRow.appendChild(peQuantity);
    peActionRow.appendChild(peBuy);
    peActionRow.appendChild(peSell);

    peAction.appendChild(peActionRow);

    tr.appendChild(peAction);

    body.appendChild(tr);
  });
}

async function placeOrder(action, optionType, strike, lots) {
  const parsedLots = parseInt(lots, 10);

  if (!Number.isInteger(parsedLots) || parsedLots <= 0) {
    setStatus("Lots must be greater than zero");
    return;
  }

  const lotSize = getLotSize(currentIndex);
  const totalQuantity = parsedLots * lotSize;

  try {
    const response = await fetch("/api/paper-trading/order", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({
        action: action,
        option_type: optionType,
        strike: strike,
        quantity: totalQuantity,
      }),
    });

    const data = await response.json();

    if (data.status !== "success") {
      setStatus(data.message || "Paper order failed");
      return;
    }

    setStatus(
      data.message +
        " | " +
        parsedLots +
        " lot(s) = " +
        formatInteger(totalQuantity) +
        " units",
    );

    await loadAccount();
  } catch (error) {
    console.error(error);

    setStatus("Paper order failed");
  }
}

async function sellPosition(optionType, strike, lots, index) {
  const parsedLots = parseInt(lots, 10);

  if (!Number.isInteger(parsedLots) || parsedLots <= 0) {
    setStatus("Invalid position lot quantity");
    return;
  }

  const lotSize = getLotSize(index || currentIndex);
  const totalQuantity = parsedLots * lotSize;

  if (
    !confirm(
      "Sell " +
        parsedLots +
        " lot(s) of " +
        optionType +
        " @ " +
        formatNumber(strike, 0) +
        "?\n\n" +
        "Total quantity: " +
        formatInteger(totalQuantity),
    )
  ) {
    return;
  }

  await placeOrder("SELL", optionType, strike, parsedLots);
}

function getTradeKey(trade) {
  return (
    String(trade.index || "")
      .trim()
      .toUpperCase() +
    "|" +
    String(trade.expiry || "")
      .trim()
      .toUpperCase() +
    "|" +
    formatNumber(trade.strike, 2) +
    "|" +
    String(trade.option_type || "")
      .trim()
      .toUpperCase()
  );
}

function calculateTradeResults(trades) {
  const orderedTrades = Array.isArray(trades) ? trades.slice().reverse() : [];

  const state = {};
  const results = new Map();
  let totalRealizedPnl = 0;

  orderedTrades.forEach(function (trade, index) {
    const key = getTradeKey(trade);

    const lots = number(trade.lots ?? trade.quantity);

    const lotSize = number(trade.lot_size || getLotSize(trade.index));

    const price = number(trade.price);

    if (lots <= 0 || lotSize <= 0) {
      results.set(index, number(trade.pnl));
      return;
    }

    if (!state[key]) {
      state[key] = {
        lots: 0,
        avgPrice: 0,
        lotSize: lotSize,
      };
    }

    const position = state[key];

    position.lotSize = lotSize;

    if (String(trade.action).toUpperCase() === "BUY") {
      const oldLots = position.lots;
      const newLots = oldLots + lots;

      if (newLots > 0) {
        position.avgPrice =
          (position.avgPrice * oldLots + price * lots) / newLots;
      }

      position.lots = newLots;

      results.set(index, 0);
    } else if (String(trade.action).toUpperCase() === "SELL") {
      const sellLots = Math.min(lots, position.lots);

      const totalQuantity = sellLots * lotSize;

      const realizedPnl = (price - position.avgPrice) * totalQuantity;

      results.set(index, realizedPnl);

      totalRealizedPnl += realizedPnl;

      position.lots -= sellLots;

      if (position.lots <= 0) {
        position.lots = 0;
        position.avgPrice = 0;
      }
    } else {
      results.set(index, number(trade.pnl));
    }
  });

  return {
    results: results,
    realizedPnl: totalRealizedPnl,
  };
}

function calculateDisplayedBalance(account, realizedPnl) {
  const initialBalance = number(account.initial_balance);

  const positions = Array.isArray(account.positions) ? account.positions : [];

  let investedAmount = 0;

  positions.forEach(function (position) {
    const lots = number(position.lots ?? position.quantity);

    const lotSize = number(position.lot_size || getLotSize(position.index));

    const avgBuy = number(position.avg_price);

    const totalQuantity = lots * lotSize;

    investedAmount += avgBuy * totalQuantity;
  });

  return initialBalance - investedAmount + realizedPnl;
}

function calculateDisplayedUnrealizedPnl(account) {
  const positions = Array.isArray(account.positions) ? account.positions : [];

  let unrealizedPnl = 0;

  positions.forEach(function (position) {
    const lots = number(position.lots ?? position.quantity);

    const lotSize = number(position.lot_size || getLotSize(position.index));

    const totalQuantity = lots * lotSize;

    const avgBuy = number(position.avg_price);

    const currentLtp = number(position.current_price);

    unrealizedPnl += (currentLtp - avgBuy) * totalQuantity;
  });

  return unrealizedPnl;
}

function calculateDisplayedTotalPnl(account, realizedPnl, unrealizedPnl) {
  return realizedPnl + unrealizedPnl;
}

async function loadAccount() {
  try {
    const response = await fetch("/api/paper-trading/account?_=" + Date.now(), {
      cache: "no-store",
    });

    const data = await response.json();

    if (data.status !== "success") {
      return;
    }

    const account = data.account;

    const tradeCalculation = calculateTradeResults(account.trades);

    const displayedRealizedPnl = tradeCalculation.realizedPnl;

    const displayedBalance = calculateDisplayedBalance(
      account,
      displayedRealizedPnl,
    );

    const displayedUnrealizedPnl = calculateDisplayedUnrealizedPnl(account);

    const displayedTotalPnl = calculateDisplayedTotalPnl(
      account,
      displayedRealizedPnl,
      displayedUnrealizedPnl,
    );

    document.getElementById("balance").textContent =
      formatNumber(displayedBalance);

    document.getElementById("realizedPnl").innerHTML =
      formatPnl(displayedRealizedPnl);

    document.getElementById("unrealizedPnl").innerHTML = formatPnl(
      displayedUnrealizedPnl,
    );

    document.getElementById("totalPnl").innerHTML =
      formatPnl(displayedTotalPnl);

    renderPositions(account.positions);

    renderTrades(account.trades, tradeCalculation.results);
  } catch (error) {
    console.error(error);
  }
}

function renderPositions(positions) {
  const body = document.getElementById("positionsBody");

  body.innerHTML = "";

  if (!positions || positions.length === 0) {
    body.innerHTML =
      "<tr>" +
      '<td colspan="14">' +
      "No open paper positions" +
      "</td>" +
      "</tr>";

    return;
  }

  positions.forEach(function (position) {
    const tr = document.createElement("tr");

    const lots = number(
      position.lots ?? position.quantity / getLotSize(position.index),
    );

    const lotSize = number(position.lot_size || getLotSize(position.index));

    const totalQuantity = number(position.quantity) || lots * lotSize;

    const avgBuy = number(position.avg_price);

    const currentLtp = number(position.current_price);

    const invested = avgBuy * totalQuantity;

    const marketValue = currentLtp * totalQuantity;

    const unrealizedPnl = (currentLtp - avgBuy) * totalQuantity;

    const pnlPercent = invested ? (unrealizedPnl / invested) * 100 : 0;

    tr.innerHTML =
      "<td>" +
      position.index +
      "</td>" +
      "<td>" +
      position.expiry +
      "</td>" +
      "<td>" +
      formatNumber(position.strike, 0) +
      "</td>" +
      "<td>" +
      position.option_type +
      "</td>" +
      "<td>" +
      formatInteger(lots) +
      "</td>" +
      "<td>" +
      formatInteger(lotSize) +
      "</td>" +
      "<td>" +
      formatInteger(totalQuantity) +
      "</td>" +
      "<td>" +
      formatNumber(avgBuy) +
      "</td>" +
      "<td>" +
      formatNumber(currentLtp) +
      "</td>" +
      "<td>" +
      formatNumber(invested) +
      "</td>" +
      "<td>" +
      formatNumber(marketValue) +
      "</td>" +
      "<td>" +
      formatPnl(unrealizedPnl) +
      "</td>" +
      "<td>" +
      formatNumber(pnlPercent) +
      "%</td>";

    const actionCell = document.createElement("td");

    actionCell.className = "position-action-cell";

    const sellButton = document.createElement("button");

    sellButton.type = "button";

    sellButton.className = "paper-button sell-button position-sell-button";

    sellButton.textContent = "SELL " + position.option_type;

    sellButton.onclick = function () {
      sellPosition(position.option_type, position.strike, lots, position.index);
    };

    actionCell.appendChild(sellButton);

    tr.appendChild(actionCell);

    body.appendChild(tr);
  });
}

function renderTrades(trades, calculatedResults) {
  const body = document.getElementById("tradesBody");

  body.innerHTML = "";

  if (!trades || trades.length === 0) {
    body.innerHTML =
      "<tr>" + '<td colspan="12">' + "No paper trades yet" + "</td>" + "</tr>";

    return;
  }

  const orderedTrades = trades.slice().reverse();

  orderedTrades.forEach(function (trade, reverseIndex) {
    const originalIndex = trades.length - 1 - reverseIndex;

    const calculatedPnl =
      calculatedResults && calculatedResults.has(originalIndex)
        ? calculatedResults.get(originalIndex)
        : number(trade.pnl);

    const tr = document.createElement("tr");

    const lotSize = number(trade.lot_size || getLotSize(trade.index));

    const totalQuantity = number(trade.quantity);

    const lots =
      number(trade.lots) || (lotSize > 0 ? totalQuantity / lotSize : 0);

    const price = number(trade.price);

    const value = price * totalQuantity;

    tr.innerHTML =
      "<td>" +
      trade.timestamp +
      "</td>" +
      "<td>" +
      trade.action +
      "</td>" +
      "<td>" +
      trade.index +
      "</td>" +
      "<td>" +
      trade.expiry +
      "</td>" +
      "<td>" +
      formatNumber(trade.strike, 0) +
      "</td>" +
      "<td>" +
      trade.option_type +
      "</td>" +
      "<td>" +
      formatInteger(lots) +
      "</td>" +
      "<td>" +
      formatInteger(lotSize) +
      "</td>" +
      "<td>" +
      formatInteger(totalQuantity) +
      "</td>" +
      "<td>" +
      formatNumber(price) +
      "</td>" +
      "<td>" +
      formatNumber(value) +
      "</td>" +
      "<td>" +
      formatPnl(calculatedPnl) +
      "</td>";

    body.appendChild(tr);
  });
}

async function resetPaperAccount() {
  if (!confirm("Reset the paper account and delete all paper trades?")) {
    return;
  }

  try {
    const response = await fetch("/api/paper-trading/reset", {
      method: "POST",
    });

    const data = await response.json();

    if (data.status !== "success") {
      setStatus(data.message || "Reset failed");
      return;
    }

    setStatus("Paper trading account reset");

    await loadAccount();
  } catch (error) {
    console.error(error);

    setStatus("Reset failed");
  }
}

function manualRefresh() {
  setStatus("Refreshing market data...");

  window.location.reload();
}

async function initializePage() {
  populateIndexes("NIFTY");

  const savedIndex = localStorage.getItem("selectedIndex");

  if (savedIndex && AVAILABLE_INDEXES.includes(savedIndex)) {
    currentIndex = savedIndex;
  }

  try {
    const response = await fetch("/status");

    const data = await response.json();

    if (data.index) {
      currentIndex = data.index;
    }

    populateIndexes(currentIndex);

    updatePageTitle(currentIndex);

    if (data.expiries) {
      populateExpiries(data.expiries, data.expiry);
    }

    if (savedIndex && savedIndex !== currentIndex && data.connected) {
      const select = document.getElementById("indexFilter");

      select.value = savedIndex;

      await changeIndex();

      return;
    }

    localStorage.setItem("selectedIndex", currentIndex);

    await loadMarket();
  } catch (error) {
    console.error(error);

    setStatus("Unable to initialize paper trading");
  }
}

document.addEventListener("DOMContentLoaded", function () {
  initializePage();

  setInterval(function () {
    window.location.reload();
  }, 180000);
});
