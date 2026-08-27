let connected = false;

/* ============================================================
   INITIAL STATUS
   ============================================================ */

document.addEventListener("DOMContentLoaded", function () {
  checkStatus();
});

/* ============================================================
   CHECK CONNECTION
   ============================================================ */

async function checkStatus() {
  try {
    const response = await fetch("/status");

    const data = await response.json();

    connected = data.connected;

    updateConnectionUI();

    if (connected) {
      loadSnapshots();
    }
  } catch (error) {
    console.error("Status error:", error);
  }
}

/* ============================================================
   CONNECT / DISCONNECT
   ============================================================ */

async function toggleConnection() {
  const button = document.getElementById("connectButton");

  button.disabled = true;

  button.textContent = connected ? "Disconnecting..." : "Connecting...";

  try {
    const response = await fetch("/connect-toggle");

    const data = await response.json();

    if (data.status === "connected") {
      connected = true;

      showMessage("Connected successfully");

      await loadSnapshots();
    } else if (data.status === "disconnected") {
      connected = false;

      showMessage("Disconnected");
    } else {
      alert(data.message || data.msg || "Connection failed");
    }
  } catch (error) {
    alert("Connection error: " + error);
  }

  updateConnectionUI();

  button.disabled = false;
}

/* ============================================================
   UPDATE CONNECTION UI
   ============================================================ */

function updateConnectionUI() {
  const status = document.getElementById("connectionStatus");

  const button = document.getElementById("connectButton");

  const refresh = document.getElementById("refreshButton");

  if (connected) {
    status.textContent = "CONNECTED";

    status.className = "status connected";

    button.textContent = "Disconnect";

    refresh.disabled = false;
  } else {
    status.textContent = "DISCONNECTED";

    status.className = "status disconnected";

    button.textContent = "Connect";

    refresh.disabled = true;
  }
}

/* ============================================================
   MANUAL REFRESH
   ============================================================ */

async function manualRefresh() {
  if (!connected) {
    return;
  }

  const button = document.getElementById("refreshButton");

  button.disabled = true;

  button.textContent = "Refreshing...";

  try {
    const response = await fetch("/refresh");

    const data = await response.json();

    if (data.status === "success") {
      await loadSnapshots();

      showMessage("New snapshot added");
    } else {
      showMessage(data.message || "Refresh failed");
    }
  } catch (error) {
    showMessage("Refresh failed");

    console.error(error);
  }

  button.disabled = false;

  if (connected) {
    button.textContent = "Refresh";
  }
}

/* ============================================================
   CHANGE EXPIRY
   ============================================================ */

async function changeExpiry() {
  if (!connected) {
    return;
  }

  const expiry = document.getElementById("expiry").value;

  if (!expiry) {
    return;
  }

  showMessage("Loading selected expiry...");

  try {
    const response = await fetch(
      "/set-expiry?expiry=" + encodeURIComponent(expiry),
    );

    const data = await response.json();

    if (data.status === "success") {
      await loadSnapshots();

      showMessage("Expiry changed");
    } else {
      showMessage(data.message || "Expiry change failed");
    }
  } catch (error) {
    showMessage("Expiry change failed");

    console.error(error);
  }
}

/* ============================================================
   LOAD SNAPSHOTS
   ============================================================ */

async function loadSnapshots() {
  try {
    const response = await fetch("/api/snapshots");

    const snapshots = await response.json();

    renderSnapshots(snapshots);

    updateDashboard(snapshots);

    updateOISummary();
  } catch (error) {
    console.error("Snapshot error:", error);
  }
}

/* ============================================================
   UPDATE TOP DASHBOARD
   ============================================================ */

function updateDashboard(snapshots) {
  if (!snapshots || snapshots.length === 0) {
    return;
  }

  const latest = snapshots[0];

  document.getElementById("spot").textContent = formatNumber(latest.spot, 2);

  document.getElementById("atm").textContent = formatNumber(latest.atm, 0);

  document.getElementById("lastUpdate").textContent = latest.timestamp;

  document.getElementById("expiry").value = latest.expiry;
}

/* ============================================================
   UPDATE LATEST OI AND VOLUME SUMMARY
   ============================================================ */

function updateOISummary() {
  const snapshots = document.querySelectorAll(".snapshot");

  if (snapshots.length === 0) {
    return;
  }

  const snapshot = snapshots[0];

  const rows = snapshot.querySelectorAll("tbody tr:not(.combined-row)");

  let highestCE = null;
  let lowestCE = null;

  let highestPE = null;
  let lowestPE = null;

  let highestCEVolume = null;
  let lowestCEVolume = null;

  let highestPEVolume = null;
  let lowestPEVolume = null;

  rows.forEach(function (row) {
    const cells = row.querySelectorAll("td");

    if (cells.length < 9) {
      return;
    }

    const strike = getNumber(cells[4].textContent);

    const ceOI = getNumber(cells[2].textContent);

    const ceVolume = getNumber(cells[3].textContent);

    const peOI = getNumber(cells[7].textContent);

    const peVolume = getNumber(cells[8].textContent);

    if (!Number.isNaN(strike) && !Number.isNaN(ceOI)) {
      if (highestCE === null || ceOI > highestCE.oi) {
        highestCE = {
          strike: strike,
          oi: ceOI,
        };
      }

      if (lowestCE === null || ceOI < lowestCE.oi) {
        lowestCE = {
          strike: strike,
          oi: ceOI,
        };
      }
    }

    if (!Number.isNaN(strike) && !Number.isNaN(peOI)) {
      if (highestPE === null || peOI > highestPE.oi) {
        highestPE = {
          strike: strike,
          oi: peOI,
        };
      }

      if (lowestPE === null || peOI < lowestPE.oi) {
        lowestPE = {
          strike: strike,
          oi: peOI,
        };
      }
    }

    if (!Number.isNaN(strike) && !Number.isNaN(ceVolume)) {
      if (highestCEVolume === null || ceVolume > highestCEVolume.volume) {
        highestCEVolume = {
          strike: strike,
          volume: ceVolume,
        };
      }

      if (lowestCEVolume === null || ceVolume < lowestCEVolume.volume) {
        lowestCEVolume = {
          strike: strike,
          volume: ceVolume,
        };
      }
    }

    if (!Number.isNaN(strike) && !Number.isNaN(peVolume)) {
      if (highestPEVolume === null || peVolume > highestPEVolume.volume) {
        highestPEVolume = {
          strike: strike,
          volume: peVolume,
        };
      }

      if (lowestPEVolume === null || peVolume < lowestPEVolume.volume) {
        lowestPEVolume = {
          strike: strike,
          volume: peVolume,
        };
      }
    }
  });

  if (highestCE !== null) {
    document.getElementById("ceHighest").textContent =
      highestCE.oi.toLocaleString("en-IN") +
      " @ " +
      highestCE.strike.toLocaleString("en-IN");
  }

  if (lowestCE !== null) {
    document.getElementById("ceLowest").textContent =
      lowestCE.oi.toLocaleString("en-IN") +
      " @ " +
      lowestCE.strike.toLocaleString("en-IN");
  }

  if (highestPE !== null) {
    document.getElementById("peHighest").textContent =
      highestPE.oi.toLocaleString("en-IN") +
      " @ " +
      highestPE.strike.toLocaleString("en-IN");
  }

  if (lowestPE !== null) {
    document.getElementById("peLowest").textContent =
      lowestPE.oi.toLocaleString("en-IN") +
      " @ " +
      lowestPE.strike.toLocaleString("en-IN");
  }

  if (highestCEVolume !== null) {
    document.getElementById("ceHighestVolume").textContent =
      highestCEVolume.volume.toLocaleString("en-IN") +
      " @ " +
      highestCEVolume.strike.toLocaleString("en-IN");
  }

  if (lowestCEVolume !== null) {
    document.getElementById("ceLowestVolume").textContent =
      lowestCEVolume.volume.toLocaleString("en-IN") +
      " @ " +
      lowestCEVolume.strike.toLocaleString("en-IN");
  }

  if (highestPEVolume !== null) {
    document.getElementById("peHighestVolume").textContent =
      highestPEVolume.volume.toLocaleString("en-IN") +
      " @ " +
      highestPEVolume.strike.toLocaleString("en-IN");
  }

  if (lowestPEVolume !== null) {
    document.getElementById("peLowestVolume").textContent =
      lowestPEVolume.volume.toLocaleString("en-IN") +
      " @ " +
      lowestPEVolume.strike.toLocaleString("en-IN");
  }
}

/* ============================================================
   NUMBER PARSER
   ============================================================ */

function getNumber(value) {
  if (value === null || value === undefined || value === "") {
    return NaN;
  }

  return Number(String(value).replace(/,/g, "").trim());
}

/* ============================================================
   RENDER SNAPSHOTS
   ============================================================ */

function renderSnapshots(snapshots) {
  const container = document.getElementById("snapshots");

  container.innerHTML = "";

  snapshots.forEach(function (snapshot) {
    const section = document.createElement("section");

    section.className = "snapshot";

    section.innerHTML = buildSnapshotHTML(snapshot);

    container.appendChild(section);
  });
}

/* ============================================================
   SNAPSHOT HTML
   ============================================================ */

function buildSnapshotHTML(snapshot) {
  let rows = "";

  let combinedCEOI = 0;
  let combinedCEVolume = 0;
  let combinedPEOI = 0;
  let combinedPEVolume = 0;

  snapshot.rows.forEach(function (row) {
    const atmClass =
      Number(row.strike) === Number(snapshot.atm) ? "atm-row" : "";

    combinedCEOI += Number(row.ce_oi) || 0;
    combinedCEVolume += Number(row.ce_volume) || 0;
    combinedPEOI += Number(row.pe_oi) || 0;
    combinedPEVolume += Number(row.pe_volume) || 0;

    rows += `
                <tr class="${atmClass}">

                    <td>
                        ${value(row.ce_ltp)}
                    </td>

                    <td class="${changeClass(row.ce_change)}">
                        ${value(row.ce_change)}
                    </td>

                    <td>
                        ${value(row.ce_oi)}
                    </td>

                    <td>
                        ${value(row.ce_volume)}
                    </td>

                    <td class="strike">
                        ${formatNumber(row.strike, 0)}
                    </td>

                    <td>
                        ${value(row.pe_ltp)}
                    </td>

                    <td class="${changeClass(row.pe_change)}">
                        ${value(row.pe_change)}
                    </td>

                    <td>
                        ${value(row.pe_oi)}
                    </td>

                    <td>
                        ${value(row.pe_volume)}
                    </td>

                </tr>
            `;
  });

  return `

        <div class="snapshot-header">

            <div>

                <strong>
                    ${snapshot.timestamp}
                </strong>

                <span>
                    Expiry: ${snapshot.expiry}
                </span>

            </div>


            <div>

                Spot:
                <strong>
                    ${formatNumber(snapshot.spot, 2)}
                </strong>

                &nbsp;&nbsp;

                ATM:
                <strong>
                    ${formatNumber(snapshot.atm, 0)}
                </strong>

            </div>

        </div>


        <div class="table-wrapper">

            <table>

                <thead>

                    <tr>

                        <th
                            colspan="4"
                            class="ce-header"
                        >
                            CALL OPTION (CE)
                        </th>


                        <th
                            rowspan="2"
                            class="strike-header"
                        >
                            STRIKE
                        </th>


                        <th
                            colspan="4"
                            class="pe-header"
                        >
                            PUT OPTION (PE)
                        </th>

                    </tr>


                    <tr>

                        <th>LTP</th>

                        <th>CHANGE</th>

                        <th>OI</th>

                        <th>VOLUME</th>


                        <th>LTP</th>

                        <th>CHANGE</th>

                        <th>OI</th>

                        <th>VOLUME</th>

                    </tr>

                </thead>


                <tbody>

                    ${rows}

                    <tr class="combined-row">

                        <td colspan="2">
                            COMBINED TOTAL
                        </td>

                        <td>
                            ${formatNumber(combinedCEOI, 0)}
                        </td>

                        <td>
                            ${formatNumber(combinedCEVolume, 0)}
                        </td>

                        <td class="strike">
                        </td>

                        <td colspan="2">
                        </td>

                        <td>
                            ${formatNumber(combinedPEOI, 0)}
                        </td>

                        <td>
                            ${formatNumber(combinedPEVolume, 0)}
                        </td>

                    </tr>

                </tbody>

            </table>

        </div>
    `;
}

/* ============================================================
   VALUE FORMAT
   ============================================================ */

function value(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return value;
}

/* ============================================================
   CHANGE CLASS
   ============================================================ */

function changeClass(value) {
  const number = Number(value);

  if (Number.isNaN(number)) {
    return "";
  }

  if (number > 0) {
    return "positive";
  }

  if (number < 0) {
    return "negative";
  }

  return "";
}

/* ============================================================
   NUMBER FORMAT
   ============================================================ */

function formatNumber(number, decimals) {
  if (number === null || number === undefined || number === "") {
    return "--";
  }

  const parsed = Number(number);

  if (Number.isNaN(parsed)) {
    return number;
  }

  return parsed.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,

    maximumFractionDigits: decimals,
  });
}

/* ============================================================
   MESSAGE
   ============================================================ */

function showMessage(message) {
  document.getElementById("refreshMessage").textContent = message;
}

/* ============================================================
   AUTOMATIC 3-MINUTE DASHBOARD UPDATE
   ============================================================ */

setInterval(async function () {
  if (!connected) {
    return;
  }

  await loadSnapshots();

  showMessage("Dashboard updated automatically");
}, 180000);
