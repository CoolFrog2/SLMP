"use strict";

const $ = (id) => document.getElementById(id);

// --- Kapcsolat mezők megőrzése localStorage-ben -------------------------
const CONN_KEYS = ["ip", "port", "timeout", "token"];
function loadConn() {
  CONN_KEYS.forEach((k) => {
    const v = localStorage.getItem("slmp_" + k);
    if (v !== null && $(k)) $(k).value = v;
  });
}
function saveConn() {
  CONN_KEYS.forEach((k) => localStorage.setItem("slmp_" + k, $(k).value));
}
CONN_KEYS.forEach((k) => $(k) && $(k).addEventListener("change", saveConn));

// --- Napló ---------------------------------------------------------------
function log(msg, kind = "info") {
  const el = document.createElement("div");
  el.className = "log-line";
  const t = new Date().toLocaleTimeString("hu-HU");
  el.innerHTML = `<span class="log-time">${t}</span> <span class="log-${kind}">${escapeHtml(msg)}</span>`;
  const box = $("log");
  box.prepend(el);
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// --- Kapcsolat adatok beolvasása ----------------------------------------
function connParams() {
  return {
    ip: $("ip").value.trim(),
    port: parseInt($("port").value, 10),
    timeout: parseFloat($("timeout").value) || 3,
  };
}

// --- API hívás -----------------------------------------------------------
async function apiPost(path, body) {
  const headers = { "Content-Type": "application/json" };
  const token = $("token").value.trim();
  if (token) headers["X-API-Token"] = token;
  const res = await fetch(path, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  let data;
  try {
    data = await res.json();
  } catch (e) {
    throw new Error(`HTTP ${res.status}: érvénytelen válasz`);
  }
  if (!data.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// --- Kapcsolat teszt -----------------------------------------------------
$("btn-test").addEventListener("click", async () => {
  const status = $("conn-status");
  status.className = "status status-unknown";
  status.textContent = "tesztelés…";
  try {
    const d = await apiPost("/api/test", connParams());
    status.className = "status status-ok";
    status.textContent = "él";
    log(d.message, "ok");
  } catch (e) {
    status.className = "status status-fail";
    status.textContent = "nincs kapcsolat";
    log("Teszt hiba: " + e.message, "err");
  }
});

// --- Olvasás -------------------------------------------------------------
$("btn-read").addEventListener("click", async () => {
  const device = $("read-device").value.trim();
  const count = parseInt($("read-count").value, 10);
  const mode = $("read-mode").value;
  if (!device) { log("Adj meg eszközt az olvasáshoz!", "err"); return; }

  const params = { ...connParams(), device, count, mode };
  const btn = $("btn-read");
  btn.disabled = true;
  try {
    const d = await apiPost("/api/read", params);
    renderRead(d);
    log(`Olvasás OK: ${device} ×${count} (${mode})`, "ok");
  } catch (e) {
    $("read-result").innerHTML = `<p class="msg-err">${escapeHtml(e.message)}</p>`;
    log("Olvasás hiba: " + e.message, "err");
  } finally {
    btn.disabled = false;
  }
});

function renderRead(d) {
  let rows = "";
  if (d.mode === "bit") {
    rows = d.values.map((v) => `
      <tr>
        <td>${v.address}</td>
        <td class="${v.value ? "bit-on" : "bit-off"}">${v.value ? "1 (ON)" : "0 (OFF)"}</td>
      </tr>`).join("");
    $("read-result").innerHTML = `
      <table><thead><tr><th>Cím</th><th>Bit</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  } else {
    rows = d.values.map((v) => `
      <tr>
        <td>${v.address}</td>
        <td>${v.value}</td>
        <td>${v.hex}</td>
        <td>${v.signed}</td>
      </tr>`).join("");
    $("read-result").innerHTML = `
      <table><thead><tr><th>Cím</th><th>Dec (u16)</th><th>Hex</th><th>Signed</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  }
}

// --- Írás ----------------------------------------------------------------
$("btn-write").addEventListener("click", async () => {
  const device = $("write-device").value.trim();
  const mode = $("write-mode").value;
  const values = $("write-values").value.trim();
  if (!device) { log("Adj meg eszközt az íráshoz!", "err"); return; }
  if (!values) { log("Adj meg írandó értékeket!", "err"); return; }

  const params = { ...connParams(), device, mode, values };
  const btn = $("btn-write");
  btn.disabled = true;
  try {
    const d = await apiPost("/api/write", params);
    $("write-result").innerHTML = `<p class="msg-ok">${escapeHtml(d.message)}</p>`;
    log("Írás OK: " + d.message, "ok");
  } catch (e) {
    $("write-result").innerHTML = `<p class="msg-err">${escapeHtml(e.message)}</p>`;
    log("Írás hiba: " + e.message, "err");
  } finally {
    btn.disabled = false;
  }
});

// --- Mód váltáskor a tipp frissítése -------------------------------------
function updateHint() {
  const mode = $("write-mode").value;
  $("write-hint").textContent = mode === "bit"
    ? "Bit: 0/1 értékek vesszővel (pl. 1,0,1,1)."
    : "Word: decimális vagy 0x hex (0–65535), vesszővel (pl. 100, 0x1A, 255).";
}
$("write-mode").addEventListener("change", updateHint);

// --- Indítás -------------------------------------------------------------
loadConn();
updateHint();
log("Frontend betöltve. Állítsd be az IP-t és portot, majd tesztelj.", "info");
