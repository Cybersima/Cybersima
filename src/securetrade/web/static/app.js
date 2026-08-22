const $ = (id) => document.getElementById(id);
const money = (n) => (n < 0 ? "-" : "") + "$" + Math.abs(Number(n || 0)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (ev) => render(JSON.parse(ev.data));
  ws.onclose = () => setTimeout(connect, 1200);
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
  $("dll").textContent = money(s.daily_loss_limit || 150);
  $("kill").textContent = s.killed ? "Resume" : "Emergency Stop";

  const best = snap.best;
  if (best) {
    $("best-pair").textContent = best.pair || "—";
    $("best-edge").textContent = Number(best.expected_net_edge_bps || best.net_edge_bps || 0).toFixed(2) / 100 + "%".replace("0.", "0.");
    $("best-edge").textContent = (Number(best.expected_net_edge_bps || best.net_edge_bps || 0) / 100).toFixed(2) + "%";
    $("best-sec").textContent = (best.security_score || best.trust_score || 0) + "/100";
    $("best-conf").textContent = Math.round((best.execution_confidence || 0) * 100) + "%";
    $("best-why").innerHTML = (best.why || []).map((line) => `<li>${line}</li>`).join("");
    $("best-details").dataset.payload = JSON.stringify(best, null, 2);
  }

  const filter = ($("filter").value || "").toLowerCase();
  $("grid").innerHTML = (snap.quotes || [])
    .filter((q) => `${q.venue} ${q.native_symbol} ${q.canonical}`.toLowerCase().includes(filter))
    .slice(0, 84)
    .map((q) => `<div class="tick"><b>${q.venue} · ${q.native_symbol}</b>${Number(q.mid).toPrecision(7)}<div>${Number(q.spread_bps).toFixed(1)} bps</div></div>`)
    .join("");

  $("outcomes").innerHTML = (snap.paper_lab || []).map((p) => {
    const cls = (p.outcome || "").toLowerCase();
    return `<li class="${cls}"><b>${p.outcome}</b> ${p.pair} ${money(p.actual_pnl)}</li>`;
  }).join("");

  $("blocks").innerHTML = (snap.alerts || []).map((a) => `<li class="loss"><b>${a.title || a.type}</b><div>${(a.reasons || []).join(" · ")}</div></li>`).join("");
  $("pending").innerHTML = (snap.pending || []).map((o) => `<li>${o.pair || o.id} <button data-approve="${o.id}">Approve</button></li>`).join("");
  $("journal").innerHTML = (snap.journal || []).map((e) => `<li><b>${e.decision}</b> ${e.action} · ${e.opportunity_id}</li>`).join("");
  $("live-gates").textContent = JSON.stringify(snap.live_prerequisites || {}, null, 2);
  renderForex(snap.forex || {});
}

function sparkline(values) {
  if (!values || values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 88;
  const h = 28;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - min) / span) * (h - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const up = values[values.length - 1] >= values[0];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${up ? "#3dd68c" : "#ff6b6b"}" stroke-width="1.6" points="${pts.join(" ")}"/></svg>`;
}

function renderForex(fx) {
  if (!$("fx-board")) return;
  const stats = fx.stats || {};
  $("fx-feed").textContent = `every ${Number(fx.poll_seconds || 3)}s`;
  $("fx-pairs").textContent = stats.pairs || 0;
  $("fx-open").textContent = stats.open || 0;
  $("fx-win").textContent = stats.win_rate != null ? Number(stats.win_rate).toFixed(1) + "%" : "—";
  const needle = ($("fx-filter").value || "").toLowerCase();
  $("fx-board").innerHTML = (fx.pairs || [])
    .filter((p) => `${p.pair} ${p.canonical} ${p.signal}`.toLowerCase().includes(needle))
    .map((p) => {
      const tfs = (p.timeframes || []).map((tf) => `<span class="fx-tf ${tf.bias}">${tf.timeframe} ${tf.bias === "up" ? "↑" : tf.bias === "down" ? "↓" : "·"}</span>`).join("");
      const cls = (p.signal || "HOLD").toLowerCase();
      const chg = Number(p.change_bps || 0);
      return `<div class="fx-row"><div class="fx-row-top"><b class="fx-pair">${p.pair}</b><span class="fx-last">${Number(p.last).toPrecision(7)}</span>${sparkline(p.spark)}</div><div class="fx-tfs">${tfs}</div><div class="fx-meta"><span class="badge ${cls}">${p.signal}</span><span>${chg >= 0 ? "+" : ""}${chg.toFixed(1)} bps · confluence ${p.confluence || 0}/8</span></div></div>`;
    })
    .join("");
  $("fx-positions").innerHTML = (fx.positions || []).map((p) => {
    const pnl = Number(p.unrealized_pnl || 0);
    return `<li class="${pnl >= 0 ? "captured" : "reversed"}"><b>${(p.side || "").toUpperCase()} ${String(p.pair || "").replace("-", "/")}</b> ${p.timeframe} · entry ${Number(p.entry || 0).toPrecision(6)} · last ${Number(p.last_price || 0).toPrecision(6)} · ${money(pnl)}<div>stop ${Number(p.stop || 0).toPrecision(6)} · target ${Number(p.target || 0).toPrecision(6)} · ${p.pattern || ""}</div></li>`;
  }).join("") || "<li>No open forex trades</li>";
  $("fx-signals").innerHTML = (fx.signals || []).map((s) => `<li><b class="${s.side === "buy" ? "captured" : "reversed"}">${(s.side || "").toUpperCase()} ${s.pair}</b> ${s.timeframe} · ${s.pattern} · ${Number(s.edge_bps || 0).toFixed(1)} bps</li>`).join("") || "<li>Waiting for confluence</li>";
  $("fx-exits").innerHTML = (fx.exits || []).map((e) => `<li class="${(e.outcome || "").toLowerCase()}"><b>${e.outcome}</b> ${e.pair} ${e.reason} · ${money(e.pnl)}</li>`).join("");
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
  $("modal-body").textContent = $("best-details").dataset.payload || "";
};
$("close-modal").onclick = () => $("modal").classList.add("hidden");

$("filter").addEventListener("input", () => {});
$("fx-filter").addEventListener("input", () => {});

document.addEventListener("click", async (ev) => {
  const id = ev.target.dataset?.approve;
  if (id) await fetch("/api/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ opportunity_id: id }) });
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

connect();
