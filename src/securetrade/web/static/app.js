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
