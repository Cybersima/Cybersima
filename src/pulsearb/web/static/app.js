const grid = document.getElementById("grid");
const opps = document.getElementById("opps");
const fills = document.getElementById("fills");
const filter = document.getElementById("filter");
const killBtn = document.getElementById("kill");
const exportBtn = document.getElementById("export-report");
const clock = document.getElementById("clock");
const feedBadge = document.getElementById("feed-badge");
const execBadge = document.getElementById("exec-badge");
const reportPath = document.getElementById("report-path");

let snapshot = { quotes: [], opportunities: [], fills: [], stats: {} };
let lastMids = new Map();
let renderTimer = null;

function fmt(n, d = 2) {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  const x = Number(n);
  if (Math.abs(x) >= 1000) return x.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Math.abs(x) < 0.001) return x.toExponential(2);
  return x.toFixed(d);
}

function tickClock() {
  clock.textContent = new Date().toLocaleTimeString();
}
setInterval(tickClock, 250);
tickClock();

function render() {
  const q = (filter.value || "").trim().toLowerCase();
  const quotes = snapshot.quotes.filter((row) => {
    if (!q) return true;
    return `${row.venue} ${row.native_symbol} ${row.canonical}`.toLowerCase().includes(q);
  });
  grid.replaceChildren(
    ...quotes.map((row) => {
      const prev = lastMids.get(`${row.venue}:${row.native_symbol}`);
      const dir = prev === undefined ? "" : row.mid > prev ? "up" : row.mid < prev ? "down" : "";
      lastMids.set(`${row.venue}:${row.native_symbol}`, row.mid);
      const el = document.createElement("div");
      el.className = `cell ${dir}`;
      el.innerHTML = `
        <div class="sym">${row.venue} · ${row.native_symbol}</div>
        <div class="px ${dir}">${fmt(row.mid, 4)}</div>
        <div class="meta"><span>${fmt(row.bid, 4)} / ${fmt(row.ask, 4)}</span><span>${fmt(row.spread_bps, 1)} bps</span></div>
      `;
      return el;
    })
  );

  opps.replaceChildren(
    ...snapshot.opportunities.map((row) => {
      const li = document.createElement("li");
      li.innerHTML = `<div class="edge">${row.kind} · ${fmt(row.net_edge_bps, 1)} bps net</div>${row.summary}`;
      return li;
    })
  );

  fills.replaceChildren(
    ...snapshot.fills.map((row) => {
      const li = document.createElement("li");
      li.className = row.status === "blocked" || row.status === "error" ? "blocked" : "";
      li.textContent = `${row.status} ${row.side} ${row.symbol} ${row.note || ""}`.trim();
      return li;
    })
  );

  const s = snapshot.stats || {};
  document.getElementById("kpi-live").textContent = s.markets_live ?? 0;
  document.getElementById("kpi-scan").textContent = `${fmt(s.last_scan_ms, 1)} ms`;
  document.getElementById("kpi-opps").textContent = s.opportunities ?? 0;
  const pnl = Number(s.paper_pnl || 0);
  const pnlEl = document.getElementById("kpi-pnl");
  pnlEl.textContent = fmt(pnl, 2);
  pnlEl.className = pnl >= 0 ? "up" : "down";
  document.getElementById("kpi-tri").textContent = s.triangles ?? 0;
  document.getElementById("kpi-up").textContent = `${fmt(s.uptime_s, 0)}s`;
  execBadge.textContent = s.execution || execBadge.textContent;
  const feeds = s.feed_status || {};
  feedBadge.textContent = Object.entries(feeds).map(([k, v]) => `${k}:${v}`).join(" · ") || "waiting";
  killBtn.classList.toggle("on", Boolean(s.killed));
  killBtn.textContent = s.killed ? "Resume" : "Kill switch";
  const reportRows = s.report_rows ?? 0;
  exportBtn.textContent = reportRows ? `Export report (${reportRows})` : "Export report";
  if (reportPath) {
    reportPath.textContent = s.report_path
      ? `Profit report file: ${s.report_path}`
      : "";
  }
}

filter.addEventListener("input", render);

killBtn.addEventListener("click", async () => {
  const killed = Boolean(snapshot.stats && snapshot.stats.killed);
  await fetch(killed ? "/api/resume" : "/api/kill", { method: "POST" });
});

exportBtn.addEventListener("click", async (ev) => {
  ev.preventDefault();
  const previous = exportBtn.textContent;
  exportBtn.textContent = "Saving…";
  try {
    const res = await fetch("/api/report.csv", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const blob = await res.blob();
    if (blob.size < 8) throw new Error("report is empty");
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "CyberSym-SecureTrade-profit-report.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    exportBtn.textContent = "Saved CSV";
  } catch (err) {
    const path = (snapshot.stats && snapshot.stats.report_path) || "data\\CyberSym-SecureTrade-profit-report.csv";
    window.alert(
      "Browser export failed. Open the CSV already on disk in Excel:\n\n" +
        path +
        "\n\n" +
        err
    );
    exportBtn.textContent = previous;
    return;
  }
  setTimeout(render, 1500);
});

function scheduleRender() {
  if (renderTimer) return;
  renderTimer = setTimeout(() => {
    renderTimer = null;
    render();
  }, 500);
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    snapshot = JSON.parse(ev.data);
    scheduleRender();
  };
  ws.onclose = () => setTimeout(connect, 1200);
}
connect();
