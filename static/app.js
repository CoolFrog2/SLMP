"use strict";

const $ = (id) => document.getElementById(id);

/* ===================== Téma ===================== */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("slmp_theme", theme);
}
$("theme-toggle").addEventListener("click", () => {
  const cur = document.documentElement.getAttribute("data-theme");
  applyTheme(cur === "dark" ? "light" : "dark");
});

/* ===================== Kapcsolat mezők megőrzése ===================== */
const CONN_KEYS = ["ip", "port", "timeout", "token"];
function loadPrefs() {
  CONN_KEYS.forEach((k) => {
    const v = localStorage.getItem("slmp_" + k);
    if (v !== null && $(k)) $(k).value = v;
  });
  applyTheme(localStorage.getItem("slmp_theme") || "dark");
}
function savePrefs() {
  CONN_KEYS.forEach((k) => $(k) && localStorage.setItem("slmp_" + k, $(k).value));
}
CONN_KEYS.forEach((k) => $(k) && $(k).addEventListener("change", savePrefs));

/* ===================== Segmentált kapcsoló ===================== */
function initSegment(id, onChange) {
  const seg = $(id);
  seg.querySelectorAll(".seg").forEach((btn) => {
    btn.addEventListener("click", () => {
      seg.querySelectorAll(".seg").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      if (onChange) onChange(btn.dataset.value);
    });
  });
}
function segValue(id) {
  return $(id).querySelector(".seg.active").dataset.value;
}

/* ===================== Toast ===================== */
function toast(message, kind = "info", ttl = 3200) {
  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
  const icon = { ok: "✓", err: "!", info: "i" }[kind] || "i";
  const ic = document.createElement("span");
  ic.className = "toast-icon";
  ic.textContent = icon;
  const msg = document.createElement("span");
  msg.className = "toast-msg";
  msg.textContent = message;
  el.append(ic, msg);
  $("toasts").appendChild(el);
  setTimeout(() => {
    el.classList.add("out");
    setTimeout(() => el.remove(), 250);
  }, ttl);
}

/* ===================== Napló ===================== */
function log(msg, kind = "info") {
  const line = document.createElement("div");
  line.className = "log-line";
  const t = document.createElement("span");
  t.className = "log-time";
  t.textContent = new Date().toLocaleTimeString("hu-HU");
  const m = document.createElement("span");
  m.className = "log-" + kind;
  m.textContent = msg;
  line.append(t, m);
  $("log").prepend(line);
}
$("btn-clear-log").addEventListener("click", () => ($("log").innerHTML = ""));

/* ===================== Gomb betöltés-állapot ===================== */
function busy(btn, on) {
  btn.classList.toggle("loading", on);
  btn.disabled = on;
}

/* ===================== Kapcsolat / API ===================== */
function connParams() {
  return {
    ip: $("ip").value.trim(),
    port: parseInt($("port").value, 10),
    timeout: parseFloat($("timeout").value) || 3,
  };
}

async function apiPost(path, body) {
  const headers = { "Content-Type": "application/json" };
  const token = $("token").value.trim();
  if (token) headers["X-API-Token"] = token;
  const res = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
  let data;
  try {
    data = await res.json();
  } catch (e) {
    throw new Error(`HTTP ${res.status}: érvénytelen válasz`);
  }
  if (!data.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function setConnState(state, text) {
  const pill = $("conn-pill");
  pill.dataset.state = state;
  $("conn-text").textContent = text;
}

/* ===================== Kapcsolat teszt ===================== */
$("btn-test").addEventListener("click", async () => {
  const btn = $("btn-test");
  setConnState("testing", "tesztelés…");
  busy(btn, true);
  try {
    const d = await apiPost("/api/test", connParams());
    setConnState("ok", "kapcsolat él");
    toast(d.message, "ok");
    log(d.message, "ok");
  } catch (e) {
    setConnState("fail", "nincs kapcsolat");
    toast(e.message, "err");
    log("Teszt hiba: " + e.message, "err");
  } finally {
    busy(btn, false);
  }
});

/* ===================== Olvasás ===================== */
async function doRead({ silent = false } = {}) {
  const device = $("read-device").value.trim();
  const count = parseInt($("read-count").value, 10);
  const mode = segValue("read-mode");
  if (!device) {
    if (!silent) toast("Adj meg eszközt az olvasáshoz!", "err");
    return false;
  }
  const params = { ...connParams(), device, count, mode };
  const btn = $("btn-read");
  if (!silent) busy(btn, true);
  try {
    const d = await apiPost("/api/read", params);
    renderRead(d);
    setConnState("ok", "kapcsolat él");
    if (!silent) log(`Olvasás OK: ${device} ×${count} (${mode})`, "ok");
    return true;
  } catch (e) {
    $("read-result").innerHTML = "";
    $("read-result").append(buildMsg(e.message, "err"));
    if (!silent) {
      toast("Olvasás hiba: " + e.message, "err");
      log("Olvasás hiba: " + e.message, "err");
    }
    stopAuto();
    return false;
  } finally {
    if (!silent) busy(btn, false);
  }
}
$("btn-read").addEventListener("click", () => doRead());

function renderRead(d) {
  const box = $("read-result");
  box.innerHTML = "";
  const table = document.createElement("table");
  table.className = "data-table";

  const head = document.createElement("thead");
  const hr = document.createElement("tr");
  const cols = d.mode === "bit"
    ? ["Cím", "Állapot"]
    : ["Cím", "Dec (u16)", "Hex", "Signed"];
  cols.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c;
    hr.appendChild(th);
  });
  head.appendChild(hr);
  table.appendChild(head);

  const body = document.createElement("tbody");
  d.values.forEach((v) => {
    const tr = document.createElement("tr");
    const addr = document.createElement("td");
    addr.className = "cell-addr";
    addr.textContent = v.address;
    tr.appendChild(addr);

    if (d.mode === "bit") {
      const td = document.createElement("td");
      const led = document.createElement("span");
      led.className = "led " + (v.value ? "on" : "off");
      const dot = document.createElement("span");
      dot.className = "led-dot";
      const txt = document.createElement("span");
      txt.textContent = v.value ? "1 · ON" : "0 · OFF";
      led.append(dot, txt);
      td.appendChild(led);
      tr.appendChild(td);
    } else {
      const dec = document.createElement("td");
      dec.className = "cell-mono";
      dec.textContent = v.value;
      const hex = document.createElement("td");
      hex.className = "cell-mono cell-muted";
      hex.textContent = v.hex;
      const sig = document.createElement("td");
      sig.className = "cell-mono cell-muted";
      sig.textContent = v.signed;
      tr.append(dec, hex, sig);
    }
    body.appendChild(tr);
  });
  table.appendChild(body);
  box.appendChild(table);
}

function buildMsg(text, kind) {
  const div = document.createElement("div");
  div.className = "msg msg-" + kind;
  const ic = document.createElement("span");
  ic.textContent = kind === "ok" ? "✓" : "⚠";
  const t = document.createElement("span");
  t.textContent = text;
  div.append(ic, t);
  return div;
}

/* ===================== Auto-frissítés ===================== */
let autoTimer = null;
function startAuto() {
  stopAuto();
  const ival = Math.max(200, parseInt($("auto-interval").value, 10) || 1000);
  autoTimer = setInterval(() => doRead({ silent: true }), ival);
  log(`Auto-frissítés bekapcsolva (${ival} ms)`, "info");
}
function stopAuto() {
  if (autoTimer) {
    clearInterval(autoTimer);
    autoTimer = null;
    if ($("auto-refresh").checked) $("auto-refresh").checked = false;
  }
}
$("auto-refresh").addEventListener("change", (e) => {
  if (e.target.checked) {
    doRead().then((ok) => ok ? startAuto() : (e.target.checked = false));
  } else {
    stopAuto();
  }
});
$("auto-interval").addEventListener("change", () => { if (autoTimer) startAuto(); });

/* ===================== Írás ===================== */
$("btn-write").addEventListener("click", async () => {
  const device = $("write-device").value.trim();
  const mode = segValue("write-mode");
  const values = $("write-values").value.trim();
  if (!device) { toast("Adj meg eszközt az íráshoz!", "err"); return; }
  if (!values) { toast("Adj meg írandó értékeket!", "err"); return; }

  const params = { ...connParams(), device, mode, values };
  const btn = $("btn-write");
  busy(btn, true);
  try {
    const d = await apiPost("/api/write", params);
    $("write-result").innerHTML = "";
    $("write-result").append(buildMsg(d.message, "ok"));
    setConnState("ok", "kapcsolat él");
    toast(d.message, "ok");
    log("Írás OK: " + d.message, "ok");
  } catch (e) {
    $("write-result").innerHTML = "";
    $("write-result").append(buildMsg(e.message, "err"));
    toast("Írás hiba: " + e.message, "err");
    log("Írás hiba: " + e.message, "err");
  } finally {
    busy(btn, false);
  }
});

/* ===================== Tipp a mód szerint ===================== */
function updateHint() {
  const mode = segValue("write-mode");
  $("write-hint").textContent = mode === "bit"
    ? "Bit: 0/1 értékek vesszővel (pl. 1,0,1,1)."
    : "Word: decimális vagy 0x hex (0–65535), vesszővel (pl. 100, 0x1A, 255).";
}

/* ===================== Enter = művelet ===================== */
["read-device", "read-count"].forEach((id) =>
  $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") doRead(); }));
["write-device", "write-values"].forEach((id) =>
  $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") $("btn-write").click(); }));

/* ===================== Random író ===================== */
let rndPoll = null;
let rndRunning = false;

function rndSetRunning(running) {
  rndRunning = running;
  const btn = $("btn-rnd-toggle");
  const label = btn.querySelector("span");
  const state = $("rnd-state");
  if (running) {
    btn.classList.replace("btn-primary", "btn-danger");
    label.textContent = "Leállítás";
    state.dataset.state = "running";
  } else {
    btn.classList.replace("btn-danger", "btn-primary");
    label.textContent = "Indítás";
    state.dataset.state = "unknown";
    $("rnd-state-text").textContent = "leállítva";
  }
}

function agoText(epochSec) {
  const diff = Date.now() / 1000 - epochSec;
  if (diff < 1.5) return "most";
  if (diff < 60) return `${Math.round(diff)} mp-e`;
  return `${Math.round(diff / 60)} perce`;
}

function rndRenderStatus(s) {
  const lastEl = $("rnd-last");
  const newVal = (s.last_value === null || s.last_value === undefined)
    ? "—" : `${s.last_value} · ${s.last_hex}`;
  if (newVal !== "—" && lastEl.textContent !== newVal) {
    lastEl.classList.remove("flash");
    void lastEl.offsetWidth;        // reflow -> animáció újrajátszása
    lastEl.classList.add("flash");
  }
  lastEl.textContent = newVal;
  $("rnd-writes").textContent = s.writes ?? 0;
  $("rnd-errors").textContent = s.errors ?? 0;
  $("rnd-when").textContent = s.last_write_at ? agoText(s.last_write_at) : "—";
  if (s.running) $("rnd-state-text").textContent = `fut · ${s.device} / ${s.interval_ms} ms`;
}

function rndStartPolling() {
  rndStopPolling();
  rndPoll = setInterval(rndPollStatus, 1000);
}
function rndStopPolling() {
  if (rndPoll) { clearInterval(rndPoll); rndPoll = null; }
}

async function rndPollStatus() {
  try {
    const d = await apiPost("/api/random/status", {});
    rndRenderStatus(d.status);
    if (!d.status.running && rndRunning) {     // a szerver állította le (pl. auto-stop)
      rndStopPolling();
      rndSetRunning(false);
      const reason = d.status.last_error || "ismeretlen ok";
      toast("Random író leállt: " + reason, "err");
      log("Random író leállt: " + reason, "err");
    }
  } catch (e) {
    rndStopPolling();
    rndSetRunning(false);
    toast("Random státusz hiba: " + e.message, "err");
  }
}

$("btn-rnd-toggle").addEventListener("click", async () => {
  const btn = $("btn-rnd-toggle");

  if (rndRunning) {
    busy(btn, true);
    try {
      const d = await apiPost("/api/random/stop", {});
      rndStopPolling();
      rndSetRunning(false);
      rndRenderStatus(d.status);
      toast("Random írás leállítva.", "ok");
      log("Random írás leállítva.", "ok");
    } catch (e) {
      toast("Leállítás hiba: " + e.message, "err");
    } finally {
      busy(btn, false);
    }
    return;
  }

  const device = $("rnd-device").value.trim();
  if (!device) { toast("Adj meg egy D regisztert!", "err"); return; }
  const params = {
    ...connParams(),
    device,
    interval: parseInt($("rnd-interval").value, 10) || 1000,
    min: parseInt($("rnd-min").value, 10) || 0,
    max: isNaN(parseInt($("rnd-max").value, 10)) ? 65535 : parseInt($("rnd-max").value, 10),
  };
  busy(btn, true);
  try {
    const d = await apiPost("/api/random/start", params);
    rndSetRunning(true);
    rndRenderStatus(d.status);
    rndStartPolling();
    setConnState("ok", "kapcsolat él");
    toast(d.message, "ok");
    log(d.message, "ok");
  } catch (e) {
    toast("Random indítás hiba: " + e.message, "err");
    log("Random indítás hiba: " + e.message, "err");
  } finally {
    busy(btn, false);
  }
});

// Oldalbetöltéskor: ha a szerveren már fut a random író, tükrözzük az állapotot.
async function rndInit() {
  try {
    const d = await apiPost("/api/random/status", {});
    if (d.status.running) {
      if (d.status.device) $("rnd-device").value = d.status.device;
      if (d.status.interval_ms) $("rnd-interval").value = d.status.interval_ms;
      if (d.status.min !== null && d.status.min !== undefined) $("rnd-min").value = d.status.min;
      if (d.status.max !== null && d.status.max !== undefined) $("rnd-max").value = d.status.max;
      rndSetRunning(true);
      rndRenderStatus(d.status);
      rndStartPolling();
    }
  } catch (e) { /* csendben — pl. ha token kell és még nincs megadva */ }
}

/* ===================== Indítás ===================== */
initSegment("read-mode");
initSegment("write-mode", updateHint);
loadPrefs();
updateHint();
rndInit();
log("Frontend betöltve. Állítsd be az IP-t és portot, majd tesztelj.", "info");
