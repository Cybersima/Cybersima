const $ = (id) => document.getElementById(id);
const money = (n) => (n < 0 ? "-" : "") + "$" + Math.abs(Number(n || 0)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

let lastDetails = null;
let lastStarter = null;
let wsLive = false;

function setLive(mode) {
  const el = $("live-dot");
  if (!el) return;
  el.className = "live-dot " + mode;
  el.textContent = mode === "live" ? "LIVE" : "SYNC";
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => {
    wsLive = true;
    setLive("live");
  };
  ws.onmessage = (ev) => render(JSON.parse(ev.data));
  ws.onclose = () => {
    wsLive = false;
    setLive("poll");
    setTimeout(connect, 1200);
  };
}

async function pullSnapshot() {
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    if (response.ok) render(await response.json());
  } catch (_err) {
    /* engine may still be starting */
  }
}

function renderDetails(details) {
  if (!details) {
    $("modal-title").textContent = "No opportunity yet";
    $("modal-body").innerHTML = "<p>When SecureTrade finds a candidate, this card explains it in plain language — expected dollars, fees, security, and why Guardian allowed or blocked it. You will never need to read source code here.</p>";
    return;
  }
  $("modal-kicker").textContent = details.headline || "Why this trade?";
  $("modal-title").textContent = details.title || "Opportunity";
  const why = (details.why || []).map((line) => `<li>${line}</li>`).join("");
  const blocked = (details.why_blocked || []).map((line) => `<li class="loss">${line}</li>`).join("");
  const legs = (details.legs || []).map((line) => `<li>${line}</li>`).join("");
  $("modal-body").innerHTML = `
    <dl>
      <div><dt>Ticket</dt><dd>${money(details.ticket_usd)}</dd></div>
      <div><dt>Expected net edge</dt><dd>${Number(details.expected_net_edge_pct || 0).toFixed(2)}%</dd></div>
      <div><dt>Expected profit</dt><dd>${money(details.expected_profit_usd)}</dd></div>
      <div><dt>Fees (est.)</dt><dd>${Number(details.fees_pct || 0).toFixed(2)}%</dd></div>
      <div><dt>Slippage (est.)</dt><dd>${Number(details.slippage_pct || 0).toFixed(2)}%</dd></div>
      <div><dt>Max anticipated loss</dt><dd>${money(details.max_anticipated_loss_usd)}</dd></div>
      <div><dt>Trust / security</dt><dd>${details.trust_score || 0}/100 · ${details.security_score || 0}/100</dd></div>
      <div><dt>Execution confidence</dt><dd>${Number(details.execution_confidence_pct || 0).toFixed(0)}%</dd></div>
      <div><dt>Guardian</dt><dd>${details.guardian || "—"}</dd></div>
    </dl>
    <p class="why-label">What the system would do</p>
    <ul>${legs}</ul>
    <p class="why-label">Why?</p>
    <ul class="why">${why}</ul>
    ${blocked ? `<p class="why-label">Blocked because</p><ul>${blocked}</ul>` : ""}
    <p class="honest">${details.honest_note || ""}</p>
  `;
}

function renderLadder(starter) {
  lastStarter = starter;
  const current = starter?.rung;
  $("ladder").innerHTML = (starter?.ladder || []).map((rung) => `
    <button type="button" data-rung="${rung.id}" class="${rung.id === current ? "on" : ""}">
      <b>${rung.title}</b>
      <span>${rung.summary}</span>
    </button>
  `).join("");
  const active = (starter?.ladder || []).find((r) => r.id === current);
  if (active) $("starter-state").textContent = active.title;
}

function humanGates(gates) {
  const labels = {
    paper_is_default: "Paper trading is the default",
    exchange_connectivity: "Exchange connectivity",
    security_configuration: "Security configuration",
    risk_limits: "Risk limits set",
    safety_checks: "Withdrawal-disabled keys / safety checks",
    live_confirm: "Live confirmation phrase",
    api_keys: "API keys stored",
    binance_enabled: "Binance enabled (optional, non-US)",
  };
  return Object.entries(gates || {}).map(([key, ok]) => {
    const mark = ok ? "✓" : "○";
    return `<li>${mark} ${labels[key] || key}</li>`;
  }).join("");
}

function toneClass(row) {
  if (row.tone) return row.tone;
  const outcome = (row.outcome || row["Close Reason"] || "").toUpperCase();
  if (outcome === "REVERSED") return "reversal";
  if (outcome === "MISSED" || outcome === "EXPIRED" || outcome === "CANCELLED" || outcome === "CANCEL" || outcome === "BLOCKED") return "missed";
  const pnl = Number(row.actual_pnl ?? row["Realized Profit"] ?? 0);
  if (outcome === "CAPTURED" && pnl < 0) return "loss";
  if (outcome === "CAPTURED" || pnl > 0) return "profit";
  if (pnl < 0) return "loss";
  return (row.outcome || "").toLowerCase();
}

function renderProfitReport(report) {
  const table = $("profit-report");
  if (!table) return;
  const headers = report?.headers || [];
  const rows = report?.rows || [];
  table.querySelector("thead").innerHTML = "<tr>" + headers.map((h) => `<th>${h}</th>`).join("") + "</tr>";
  if (!rows.length) {
    table.querySelector("tbody").innerHTML = `<tr><td colspan="${Math.max(headers.length, 1)}">No closed trades yet. Captures, reversals, misses, and cancelled commits appear here.</td></tr>`;
    return;
  }
  table.querySelector("tbody").innerHTML = rows.map((row) => {
    const tone = row.tone || toneClass(row);
    return "<tr>" + headers.map((header) => {
      const cls = header === "Market" ? ` class="market ${tone}"` : "";
      const value = row[header] ?? "";
      return `<td${cls}>${value}</td>`;
    }).join("") + "</tr>";
  }).join("");
}

function render(snap) {
  const s = snap.stats || {};
  $("clock").textContent = new Date().toLocaleTimeString();
  $("sys-state").textContent = "● " + (s.system || "PROTECTED");
  $("tr-state").textContent = "● " + (s.trading || "ACTIVE");
  $("tr-state").className = s.killed ? "bad" : "ok";
  $("sec-score").textContent = (s.security_score || 98) + " / 100";
  $("mkt-count").textContent = s.markets_live || 0;
  $("acct").textContent = money(s.account_value);
  const today = Number(s.today_pnl || 0);
  $("today").textContent = (today >= 0 ? "+" : "") + money(today).replace("$-", "-$");
  $("today").className = today >= 0 ? "ok" : "bad";
  const month = Number(s.month_pnl || 0);
  $("month").textContent = (month >= 0 ? "+" : "") + money(month).replace("$-", "-$");
  $("dd").textContent = Number(s.max_drawdown || 0).toFixed(1) + "%";
  $("auto-state").textContent = s.auto_trading ? "ON" : "OFF";
  $("mode-state").textContent = (s.operating_mode || "learn").toUpperCase();
  $("dll").textContent = money(s.daily_loss_limit || 5);
  $("kill").textContent = s.killed ? "Resume" : "Emergency Stop";
  document.querySelectorAll(".modes button").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.mode === (s.operating_mode || "learn"));
  });

  if (snap.starter) renderLadder(snap.starter);

  const best = snap.best;
  lastDetails = snap.best_details || null;
  if (best) {
    $("best-pair").textContent = best.pair || "—";
    $("best-edge").textContent = (Number(best.expected_net_edge_bps || best.net_edge_bps || 0) / 100).toFixed(2) + "%";
    $("best-usd").textContent = money(best.expected_profit_usd);
    $("best-ticket").textContent = money(best.notional);
    $("best-sec").textContent = (best.security_score || best.trust_score || 0) + "/100";
    $("best-conf").textContent = Math.round((best.execution_confidence || 0) * 100) + "%";
    $("best-why").innerHTML = (best.why || []).map((line) => `<li>${line}</li>`).join("");
  }

  const filter = (($("filter") || {}).value || "").toLowerCase();
  const labels = { profit: "Profit", loss: "Loss", missed: "Missed opportunity", reversal: "Reversal" };
  $("grid").innerHTML = (snap.quotes || [])
    .filter((q) => `${q.venue} ${q.native_symbol} ${q.canonical}`.toLowerCase().includes(filter))
    .slice(0, 84)
    .map((q) => {
      const tone = q.tone || "";
      const label = labels[tone] ? `<div class="tone">${labels[tone]}</div>` : "";
      return `<div class="tick ${tone}"><b>${q.venue} · ${q.native_symbol}</b>${Number(q.mid).toPrecision(7)}<div>${Number(q.spread_bps).toFixed(1)} bps</div>${label}</div>`;
    })
    .join("");

  $("outcomes").innerHTML = (snap.paper_lab || []).map((p) => {
    const cls = toneClass(p);
    return `<li class="${cls}"><b>${p.outcome}</b> ${p.pair} ${money(p.actual_pnl)}</li>`;
  }).join("");

  $("blocks").innerHTML = (snap.alerts || []).map((a) => `<li class="loss"><b>${a.title || a.type}</b><div>${(a.reasons || []).join(" · ")}</div></li>`).join("");
  $("pending").innerHTML = (snap.pending || []).map((o) => `<li>${o.pair || o.id} <button data-approve="${o.id}">Approve</button></li>`).join("");
  $("journal").innerHTML = (snap.journal || []).map((e) => `<li><b>${e.decision}</b> ${e.action} · ${e.opportunity_id}</li>`).join("");
  $("live-gates").innerHTML = humanGates(snap.live_prerequisites);
  renderProfitReport(snap.profit_report);
}

document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("on"));
    btn.classList.add("on");
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("on"));
    document.getElementById("view-" + btn.dataset.view).classList.add("on");
  };
});

document.querySelectorAll(".modes button").forEach((btn) => {
  btn.onclick = async () => {
    await fetch("/api/mode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: btn.dataset.mode }) });
  };
});

$("kill").onclick = async () => {
  const killed = $("kill").textContent.includes("Resume");
  await fetch(killed ? "/api/resume" : "/api/kill", { method: "POST" });
};

$("best-details").onclick = () => {
  $("modal").classList.remove("hidden");
  renderDetails(lastDetails);
};
$("close-modal").onclick = () => $("modal").classList.add("hidden");
$("modal").addEventListener("click", (ev) => {
  if (ev.target.id === "modal") $("modal").classList.add("hidden");
});

document.addEventListener("click", async (ev) => {
  const id = ev.target.dataset?.approve;
  if (id) await fetch("/api/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ opportunity_id: id }) });
  const rung = ev.target.closest("[data-rung]")?.dataset?.rung;
  if (rung) await fetch("/api/starter", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rung }) });
});

$("finish-wizard").onclick = async () => {
  await fetch("/api/wizard/complete", { method: "POST" });
  $("finish-wizard").textContent = "Setup complete";
};

fetch("/api/academy").then((r) => r.json()).then((data) => {
  $("lessons").innerHTML = (data.lessons || []).map((l) => `<article><h3>${l.title}</h3><p>${l.body}</p></article>`).join("");
});
fetch("/api/wizard").then((r) => r.json()).then((data) => {
  $("wizard").innerHTML = (data.steps || []).map((s) => `<article><h3>${s.title}</h3><p>${s.body}</p></article>`).join("");
});
fetch("/api/journal").then((r) => r.json()).then((data) => {
  $("chain").textContent = data.chain_ok ? "chain verified" : "chain broken";
});
fetch("/api/starter").then((r) => r.json()).then(renderLadder);

pullSnapshot();
setInterval(() => {
  if (!wsLive) pullSnapshot();
}, 2000);
connect();
