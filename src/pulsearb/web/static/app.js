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
const liveBanner = document.getElementById("live-banner");
const pnlLabel = document.getElementById("kpi-pnl-label");
const amountInput = document.getElementById("invest-amount");
const presetsEl = document.getElementById("presets");
const assetChips = document.getElementById("asset-chips");
const venueChips = document.getElementById("venue-chips");
const kindChips = document.getElementById("kind-chips");
const modePick = document.getElementById("mode-pick");
const modeAuto = document.getElementById("mode-auto");
const amountHint = document.getElementById("amount-hint");
const modeHint = document.getElementById("mode-hint");
const priceAny = document.getElementById("price-any");
const priceUnder = document.getElementById("price-under");
const priceOver = document.getElementById("price-over");
const priceLimitInput = document.getElementById("price-limit");
const pricePresetsEl = document.getElementById("price-presets");
const priceHint = document.getElementById("price-hint");
const toastEl = document.getElementById("toast");
const guardBanner = document.getElementById("guard-banner");
const liveReadyEl = document.getElementById("live-ready");
const liveReadyList = document.getElementById("live-ready-list");
const liveReadyStatus = document.getElementById("live-ready-status");
const liveReadyRefresh = document.getElementById("live-ready-refresh");
const fillsMeta = document.getElementById("fills-meta");
const themeDarkBtn = document.getElementById("theme-dark");
const themeLightBtn = document.getElementById("theme-light");
const soundOnBtn = document.getElementById("sound-on");
const soundOffBtn = document.getElementById("sound-off");
const THEME_KEY = "cybersym-theme";
const DESK_KEY = "cybersym-desk";
const SOUND_KEY = "cybersym-sound";

let snapshot = { quotes: [], opportunities: [], fills: [], stats: {}, desk: {} };
let lastMids = new Map();
let renderTimer = null;
let deskReady = false;
let soundOn = true;
let audioCtx = null;
let seenTradeKeys = null;
let seenFillKeys = null;
let lastAlertAt = 0;
let desk = {
  notional: 5,
  auto_invest: false,
  all_assets: false,
  assets: ["BTC", "ETH", "SOL", "XRP"],
  venues: ["coinbase", "kraken", "gemini", "bitstamp"],
  kinds: ["cross_venue", "triangular"],
  cap: 250,
  min_notional: 1,
  presets: [1, 2, 3, 4, 5, 10, 25, 50, 100, 250],
  asset_choices: ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "LINK", "AVAX", "DOT", "UNI", "AAVE"],
  venue_choices: [
    { id: "coinbase", label: "Coinbase" },
    { id: "kraken", label: "Kraken" },
    { id: "gemini", label: "Gemini" },
    { id: "bitstamp", label: "Bitstamp" },
  ],
  kind_choices: [
    { id: "cross_venue", label: "Price gaps" },
    { id: "triangular", label: "Same-exchange triangles" },
  ],
  live: false,
  auto_allowed: true,
  budget: null,
  budget_left: null,
  taps_left: null,
  price_mode: "any",
  price_limit: 5,
  price_presets: [1, 2, 5, 10, 50, 100, 1000],
};

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

function applyTheme(theme) {
  const next = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  document.documentElement.style.colorScheme = next;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", next === "light" ? "#f4f8fc" : "#05070c");
  const bar = document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]');
  if (bar) bar.setAttribute("content", next === "light" ? "default" : "black-translucent");
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch (err) {
    /* private mode */
  }
  if (themeDarkBtn && themeLightBtn) {
    themeDarkBtn.classList.toggle("on", next === "dark");
    themeLightBtn.classList.toggle("on", next === "light");
    themeDarkBtn.setAttribute("aria-pressed", String(next === "dark"));
    themeLightBtn.setAttribute("aria-pressed", String(next === "light"));
  }
}

function readSavedDesk() {
  try {
    const raw = localStorage.getItem(DESK_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    if (!saved || typeof saved !== "object") return null;
    return saved;
  } catch (err) {
    return null;
  }
}

function persistDeskLocal() {
  try {
    localStorage.setItem(
      DESK_KEY,
      JSON.stringify({
        notional: desk.notional,
        auto_invest: desk.auto_invest,
        all_assets: desk.all_assets,
        assets: desk.assets,
        venues: desk.venues,
        kinds: desk.kinds,
        price_mode: desk.price_mode || "any",
        price_limit: desk.price_limit ?? 5,
      })
    );
  } catch (err) {
    /* private mode */
  }
}

applyTheme(
  (() => {
    try {
      return localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
    } catch (err) {
      return "dark";
    }
  })()
);
if (themeDarkBtn) themeDarkBtn.addEventListener("click", () => applyTheme("dark"));
if (themeLightBtn) themeLightBtn.addEventListener("click", () => applyTheme("light"));

function soundEnabled() {
  try {
    return localStorage.getItem(SOUND_KEY) !== "off";
  } catch (err) {
    return true;
  }
}

function applySound(on, { preview = false } = {}) {
  soundOn = Boolean(on);
  try {
    localStorage.setItem(SOUND_KEY, soundOn ? "on" : "off");
  } catch (err) {
    /* private mode */
  }
  if (soundOnBtn && soundOffBtn) {
    soundOnBtn.classList.toggle("on", soundOn);
    soundOffBtn.classList.toggle("on", !soundOn);
    soundOnBtn.setAttribute("aria-pressed", String(soundOn));
    soundOffBtn.setAttribute("aria-pressed", String(!soundOn));
  }
  if (preview) {
    if (soundOn) {
      playChime(true, "done");
      showToast("Trade sound is on for new setups and completed fills.");
    } else {
      showToast("Trade sound is off. You will still see on-screen alerts.");
    }
  }
}

function unlockAudio() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!audioCtx) audioCtx = new Ctx();
    if (audioCtx.state === "suspended") audioCtx.resume();
  } catch (err) {
    /* autoplay blocked until a click */
  }
}

function playChime(force, kind = "offer") {
  if (!soundOn && !force) return;
  unlockAudio();
  if (!audioCtx) return;
  try {
    const t = audioCtx.currentTime;
    const notes =
      kind === "done"
        ? [523, 784, 1046]
        : kind === "blocked"
          ? [220]
          : [880, 1175];
    notes.forEach((freq, index) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      const start = t + index * 0.09;
      osc.type = kind === "blocked" ? "triangle" : "sine";
      osc.frequency.setValueAtTime(freq, start);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(kind === "done" ? 0.08 : 0.07, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + (kind === "done" ? 0.22 : 0.2));
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(start);
      osc.stop(start + 0.28);
    });
  } catch (err) {
    /* ignore */
  }
}

function tradeKey(row) {
  const legs = (row.legs || []).map((leg) => `${leg.action}:${leg.venue}:${leg.symbol}`).join(">");
  return `${row.kind || ""}|${legs || row.summary || row.id || ""}`;
}

function matchingTrades(data) {
  return (data.opportunities || []).filter(
    (row) => row.chosen !== false && (row.investable || row.pending)
  );
}

function noticeNewTrades(data) {
  const rows = matchingTrades(data);
  const keys = new Set(rows.map(tradeKey));
  if (seenTradeKeys === null) {
    seenTradeKeys = keys;
    return;
  }
  const fresh = rows.filter((row) => !seenTradeKeys.has(tradeKey(row)));
  seenTradeKeys = keys;
  if (!fresh.length) return;
  const now = Date.now();
  if (now - lastAlertAt < 3500) return;
  lastAlertAt = now;
  const first = fresh[0];
  const label = friendlyOpp(first);
  showToast(
    fresh.length === 1 ? `New trade: ${label}` : `${fresh.length} new trades for you. ${label}`
  );
  playChime(false, "offer");
}

function fillKey(row) {
  return [row.ts, row.venue, row.symbol, row.side, row.status, row.opportunity_id, row.qty].join("|");
}

function noticeNewFills(data) {
  const rows = data.fills || [];
  const keys = new Set(rows.map(fillKey));
  if (seenFillKeys === null) {
    seenFillKeys = keys;
    return;
  }
  const fresh = rows.filter((row) => !seenFillKeys.has(fillKey(row)));
  seenFillKeys = keys;
  if (!fresh.length) return;
  const done = fresh.filter((row) => row.status === "filled");
  const blocked = fresh.filter((row) => row.status === "blocked" || row.status === "error");
  if (done.length) {
    const row = done[done.length - 1];
    showToast(`Trade complete: ${row.side} ${row.symbol} on ${row.venue}`);
    playChime(false, "done");
    return;
  }
  if (blocked.length) {
    const row = blocked[blocked.length - 1];
    showToast(`Trade not filled: ${row.side} ${row.symbol} ${row.note || row.status}`.trim());
    playChime(false, "blocked");
  }
}

applySound(soundEnabled());
if (soundOnBtn) soundOnBtn.addEventListener("click", () => applySound(true, { preview: true }));
if (soundOffBtn) soundOffBtn.addEventListener("click", () => applySound(false, { preview: true }));
document.addEventListener("pointerdown", unlockAudio, { once: true });

function showToast(text) {
  if (!toastEl) return;
  toastEl.textContent = text;
  toastEl.hidden = false;
  toastEl.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    toastEl.classList.remove("show");
    toastEl.hidden = true;
  }, 3200);
}

function chip(label, on, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `chip${on ? " on" : ""}`;
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function paintDesk() {
  if (!amountInput) return;
  if (document.activeElement !== amountInput) {
    amountInput.value = String(desk.notional);
    amountInput.max = String(desk.cap);
    amountInput.min = String(desk.min_notional || 1);
    amountInput.step = Number(desk.notional) < 5 ? "1" : "1";
  }
  presetsEl.replaceChildren(
    ...desk.presets.map((amt) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `preset${Number(desk.notional) === Number(amt) ? " on" : ""}`;
      btn.textContent = `$${amt}`;
      btn.addEventListener("click", () => saveDesk({ notional: amt }));
      return btn;
    })
  );
  const autoAllowed = desk.auto_allowed !== false;
  modePick.classList.toggle("on", !desk.auto_invest);
  modeAuto.classList.toggle("on", desk.auto_invest);
  modeAuto.disabled = !autoAllowed;
  modeAuto.title = autoAllowed ? "" : "Auto stays off while live Coinbase orders are armed.";
  amountHint.textContent = desk.live
    ? `This tap: $${fmt(desk.notional, 0)}. Session budget $${fmt(desk.budget || desk.cap, 0)} · $${fmt(desk.budget_left ?? desk.cap, 2)} left (${desk.taps_left ?? "?"} more taps). Coins under $1 still buy a fraction.`
    : "Each tap is this size. $1–$5 is typical. Paper until you go live. Coins under $1 still buy a fraction.";
  if (modeHint) {
    modeHint.textContent = autoAllowed
      ? "Picking is safer. Auto uses your amount on matching trades."
      : "Live mode: Auto stays off. Tap Invest on each Coinbase-only triangle.";
  }

  const priceMode = desk.price_mode || "any";
  const priceLimit = Number(desk.price_limit) || 5;
  if (priceAny) priceAny.classList.toggle("on", priceMode === "any");
  if (priceUnder) priceUnder.classList.toggle("on", priceMode === "under");
  if (priceOver) priceOver.classList.toggle("on", priceMode === "over");
  if (priceLimitInput && document.activeElement !== priceLimitInput) {
    priceLimitInput.value = String(priceLimit);
  }
  if (pricePresetsEl) {
    const presets = desk.price_presets || [1, 2, 5, 10, 50, 100, 1000];
    pricePresetsEl.replaceChildren(
      ...presets.map((amt) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `preset${Number(priceLimit) === Number(amt) ? " on" : ""}`;
        btn.textContent = `$${amt}`;
        btn.addEventListener("click", () => {
          const patch = { price_limit: amt };
          if ((desk.price_mode || "any") === "any") patch.price_mode = "under";
          saveDesk(patch);
        });
        return btn;
      })
    );
  }
  if (priceHint) {
    if (priceMode === "under") {
      priceHint.textContent = `Showing coins at $${fmt(priceLimit, 0)} or less. Over $${fmt(priceLimit, 0)} is hidden. Uses the coin’s USD price, not ETH-BTC ratios.`;
    } else if (priceMode === "over") {
      priceHint.textContent = `Showing coins at $${fmt(priceLimit, 0)} or more. Under $${fmt(priceLimit, 0)} is hidden. Uses the coin’s USD price, not ETH-BTC ratios.`;
    } else {
      priceHint.textContent =
        "Leave on Any to see every pair. Under $5 hides coins priced above $5. Over does the reverse. Uses the coin’s USD price, not ETH-BTC ratios.";
    }
  }

  const allOn = Boolean(desk.all_assets);
  assetChips.replaceChildren(
    chip("All coins", allOn, () => saveDesk({ all_assets: !allOn })),
    ...desk.asset_choices.map((asset) =>
      chip(asset, !allOn && desk.assets.includes(asset), () => {
        const next = desk.assets.includes(asset)
          ? desk.assets.filter((item) => item !== asset)
          : [...desk.assets, asset];
        saveDesk({ all_assets: false, assets: next });
      })
    )
  );
  venueChips.replaceChildren(
    ...desk.venue_choices.map((row) =>
      chip(row.label, desk.venues.includes(row.id), () => {
        const next = desk.venues.includes(row.id)
          ? desk.venues.filter((item) => item !== row.id)
          : [...desk.venues, row.id];
        saveDesk({ venues: next });
      })
    )
  );
  kindChips.replaceChildren(
    ...desk.kind_choices.map((row) =>
      chip(row.label, desk.kinds.includes(row.id), () => {
        const next = desk.kinds.includes(row.id)
          ? desk.kinds.filter((item) => item !== row.id)
          : [...desk.kinds, row.id];
        saveDesk({ kinds: next });
      })
    )
  );
}

async function saveDesk(patch) {
  const payload = { ...desk, ...patch };
  try {
    const res = await fetch("/api/desk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    desk = await res.json();
    persistDeskLocal();
    paintDesk();
    render();
  } catch (err) {
    showToast("Could not save your choices. " + err);
  }
}

function pairParts(symbol) {
  const text = String(symbol || "")
    .toUpperCase()
    .replace("/", "-");
  if (text.includes("-")) {
    const [base, quote] = text.split("-");
    return [base, quote || ""];
  }
  return [text, ""];
}

const USD_QUOTES = new Set(["USD", "USDT", "USDC", "FDUSD", "BUSD", "TUSD"]);

function coinUsdPrice(coin, venue) {
  const wanted = String(coin || "").toUpperCase();
  if (!wanted) return null;
  const markets = snapshot.quotes || [];
  const rank = (row) => {
    const [, quote] = pairParts(row.canonical || row.native_symbol);
    if (row.venue === venue && quote === "USD") return 0;
    if (row.venue === venue && USD_QUOTES.has(quote)) return 1;
    if (quote === "USD") return 2;
    if (USD_QUOTES.has(quote)) return 3;
    return 9;
  };
  let best = null;
  let bestRank = 9;
  for (const row of markets) {
    const [base, quote] = pairParts(row.canonical || row.native_symbol);
    if (base !== wanted || !USD_QUOTES.has(quote)) continue;
    if (!Number.isFinite(row.mid) || row.mid <= 0) continue;
    const next = rank(row);
    if (next < bestRank) {
      best = row.mid;
      bestRank = next;
      if (next === 0) break;
    }
  }
  return best;
}

function quotePassesPriceFilter(row) {
  const mode = desk.price_mode || "any";
  if (mode === "any") return true;
  const limit = Number(desk.price_limit) || 5;
  const [base] = pairParts(row.canonical || row.native_symbol);
  const price = coinUsdPrice(base, row.venue);
  if (price == null) return false;
  if (mode === "under") return price <= limit;
  if (mode === "over") return price >= limit;
  return true;
}

function priceFilterLabel() {
  const mode = desk.price_mode || "any";
  const limit = Number(desk.price_limit) || 5;
  if (mode === "under") return `under $${fmt(limit, 0)}`;
  if (mode === "over") return `over $${fmt(limit, 0)}`;
  return "";
}

function friendlyOpp(row) {
  const legs = row.legs || [];
  const buy = legs.find((leg) => leg.action === "buy");
  const sell = legs.find((leg) => leg.action === "sell");
  if (row.kind === "triangular") {
    const venue = (buy && buy.venue) || (legs[0] && legs[0].venue) || "";
    return `Same-exchange triangle on ${venue}`;
  }
  if (row.kind === "alert") return row.summary;
  if (buy && sell) return `Buy ${buy.symbol} on ${buy.venue}, sell on ${sell.venue}`;
  return row.summary;
}

function render() {
  const q = (filter.value || "").trim().toLowerCase();
  const quotes = (snapshot.quotes || []).filter((row) => {
    if (!quotePassesPriceFilter(row)) return false;
    if (!q) return true;
    return `${row.venue} ${row.native_symbol} ${row.canonical}`.toLowerCase().includes(q);
  });
  if (!quotes.length) {
    const empty = document.createElement("div");
    empty.className = "grid-empty";
    const range = priceFilterLabel();
    empty.textContent = range
      ? `No pairs ${range} right now. Try Any price, or change the dollar cutoff.`
      : q
        ? "No pairs match that search."
        : "Waiting for market quotes…";
    grid.replaceChildren(empty);
  } else {
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
  }

  const mine = (snapshot.opportunities || []).filter((row) => row.chosen !== false);
  if (!mine.length) {
    const empty = document.createElement("li");
    empty.className = "empty";
    const range = priceFilterLabel();
    empty.textContent = range
      ? `No matching trades ${range} right now. Try Any price, or pick more coins.`
      : "No matching trades right now. Pick more coins, or wait for the next scan.";
    opps.replaceChildren(empty);
  } else {
    opps.replaceChildren(
      ...mine.map((row) => {
        const li = document.createElement("li");
        li.className = "opp-card";
        const kicker = document.createElement("div");
        kicker.className = "edge";
        kicker.textContent = `${row.kind_label || row.kind} · ${fmt(row.net_edge_bps, 1)} bps net`;
        const body = document.createElement("div");
        body.textContent = friendlyOpp(row);
        const meta = document.createElement("div");
        meta.className = "opp-meta";
        meta.innerHTML = `<span>Est. P&amp;L $${fmt(row.expected_pnl, 2)}</span><span>$${fmt(row.notional, 0)} size</span>`;
        li.append(kicker, body, meta);
        if (row.investable) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "invest-btn";
          btn.textContent = `Invest $${fmt(desk.notional, 0)}`;
          btn.addEventListener("click", () => invest(row.id, btn));
          li.append(btn);
        } else if (row.pending && desk.auto_invest) {
          const note = document.createElement("div");
          note.className = "hint";
          note.textContent = "Auto will take this if it is still open.";
          li.append(note);
        } else if (!row.executable) {
          const note = document.createElement("div");
          note.className = "hint";
          note.textContent = "Watch only — delayed data, not an order.";
          li.append(note);
        }
        return li;
      })
    );
  }

  const fillRows = snapshot.fills || [];
  const completed = fillRows.filter((row) => row.status === "filled");
  if (fillsMeta) {
    if (!completed.length) {
      fillsMeta.textContent = "";
    } else {
      const last = completed[completed.length - 1];
      fillsMeta.textContent = `${completed.length} complete · last ${last.side} ${last.symbol}`;
    }
  }
  if (!fillRows.length) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "No fills yet. Pick a trade when one appears.";
    fills.replaceChildren(empty);
  } else {
    fills.replaceChildren(
      ...fillRows.map((row) => {
        const li = document.createElement("li");
        li.className = row.status === "blocked" || row.status === "error" ? "blocked" : "";
        li.textContent = `${row.status} ${row.side} ${row.symbol} ${row.note || ""}`.trim();
        return li;
      })
    );
  }

  const s = snapshot.stats || {};
  document.getElementById("kpi-live").textContent = s.markets_live ?? 0;
  document.getElementById("kpi-scan").textContent = `${fmt(s.last_scan_ms, 1)} ms`;
  document.getElementById("kpi-opps").textContent = s.opportunities ?? 0;
  const pnl = Number(s.paper_pnl || 0);
  const pnlEl = document.getElementById("kpi-pnl");
  pnlEl.textContent = fmt(pnl, 2);
  pnlEl.className = pnl >= 0 ? "up" : "down";
  const live = String(s.execution || "").startsWith("live");
  if (pnlLabel) pnlLabel.textContent = live ? "Live P&L" : "Paper P&L";
  execBadge.textContent = s.execution || execBadge.textContent;
  execBadge.classList.toggle("exec-live", live);
  if (liveBanner) {
    liveBanner.classList.toggle("show", live);
    liveBanner.hidden = !live;
    if (live) {
      const bals = s.balances || {};
      const top = Object.entries(bals)
        .slice(0, 6)
        .map(([k, v]) => `${k} ${fmt(v, 4)}`)
        .join(" · ");
      liveBanner.textContent = [
        s.live_note || "LIVE trading is on. Real money.",
        desk.notional ? `This tap $${fmt(desk.notional, 0)}.` : "",
        desk.budget != null ? `Budget $${fmt(desk.budget_left ?? 0, 2)} of $${fmt(desk.budget, 0)} left.` : "",
        top ? `Balances: ${top}` : "",
      ]
        .filter(Boolean)
        .join(" ");
    }
  }
  document.getElementById("kpi-tri").textContent = s.triangles ?? 0;
  document.getElementById("kpi-up").textContent = `${fmt(s.uptime_s, 0)}s`;
  const feeds = s.feed_status || {};
  feedBadge.textContent = Object.entries(feeds).map(([k, v]) => `${k}:${v}`).join(" · ") || "waiting";
  killBtn.classList.toggle("on", Boolean(s.killed));
  killBtn.textContent = s.killed ? "Resume" : "Kill switch";
  const reportRows = s.report_rows ?? 0;
  exportBtn.textContent = reportRows ? `Export report (${reportRows})` : "Export report";
  if (reportPath) {
    reportPath.textContent = s.report_path ? `Profit report file: ${s.report_path}` : "";
  }
}

async function invest(id, btn) {
  btn.disabled = true;
  btn.textContent = "Investing…";
  try {
    const res = await fetch("/api/invest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Could not invest");
    showToast(`Invested $${fmt(desk.notional, 0)}. Check Your fills.`);
  } catch (err) {
    showToast(String(err.message || err));
    btn.disabled = false;
    btn.textContent = `Invest $${fmt(desk.notional, 0)}`;
  }
}

filter.addEventListener("input", render);

killBtn.addEventListener("click", async () => {
  const killed = Boolean(snapshot.stats && snapshot.stats.killed);
  await fetch(killed ? "/api/resume" : "/api/kill", { method: "POST" });
});

modePick.addEventListener("click", () => saveDesk({ auto_invest: false }));
modeAuto.addEventListener("click", () => {
  if (desk.auto_allowed === false) {
    showToast("Auto stays off while live Coinbase orders are armed.");
    return;
  }
  saveDesk({ auto_invest: true });
});
amountInput.addEventListener("change", () => saveDesk({ notional: Number(amountInput.value) }));
if (priceAny) priceAny.addEventListener("click", () => saveDesk({ price_mode: "any" }));
if (priceUnder) priceUnder.addEventListener("click", () => saveDesk({ price_mode: "under" }));
if (priceOver) priceOver.addEventListener("click", () => saveDesk({ price_mode: "over" }));
if (priceLimitInput) {
  priceLimitInput.addEventListener("change", () => saveDesk({ price_limit: Number(priceLimitInput.value) }));
}

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
      "Browser export failed. Open the CSV already on disk in Excel:\n\n" + path + "\n\n" + err
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
    try {
      snapshot = JSON.parse(ev.data);
    } catch (err) {
      return;
    }
    if (snapshot.desk) {
      desk = { ...desk, ...snapshot.desk };
      if (!deskReady) {
        deskReady = true;
        const saved = readSavedDesk();
        if (saved) {
          saveDesk(saved);
        } else {
          paintDesk();
        }
      }
    }
    noticeNewTrades(snapshot);
    noticeNewFills(snapshot);
    scheduleRender();
  };
  ws.onclose = () => setTimeout(connect, 1200);
}
connect();
paintDesk();
paintSecurity();
paintLiveReady();
if (liveReadyRefresh) liveReadyRefresh.addEventListener("click", () => paintLiveReady());

async function paintSecurity() {
  if (!guardBanner) return;
  try {
    const res = await fetch("/api/security");
    if (!res.ok) return;
    const data = await res.json();
    const bits = [
      data.network === "lan" ? "On your Wi-Fi · PIN required" : "This computer only",
      data.execution === "live" ? `LIVE · cap $${fmt(data.live_cap, 0)}` : "Paper trading",
      data.keys_file ? "Coinbase key file on this PC" : "No Coinbase key file",
      data.killed ? "Kill switch on" : "",
      data.note,
    ];
    guardBanner.textContent = bits.filter(Boolean).join(" · ");
  } catch (err) {
    /* ignore */
  }
}

async function paintLiveReady() {
  if (!liveReadyEl || !liveReadyList) return;
  if (liveReadyRefresh) liveReadyRefresh.disabled = true;
  if (liveReadyStatus) liveReadyStatus.textContent = "Checking Coinbase keys and cash…";
  try {
    const res = await fetch("/api/live-ready");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "HTTP " + res.status);
    liveReadyEl.classList.toggle("ready", Boolean(data.ready));
    liveReadyEl.classList.toggle("not-ready", !data.ready);
    if (liveReadyStatus) liveReadyStatus.textContent = data.note || "";
    liveReadyList.replaceChildren(
      ...(data.checks || []).map((row) => {
        const li = document.createElement("li");
        const mark = document.createElement("span");
        const status = row.status || (row.ok ? "ok" : "fail");
        mark.className = `mark ${status}`;
        mark.textContent = status === "ok" ? "OK" : status === "wait" ? "WAIT" : "FAIL";
        const body = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = row.label;
        const detail = document.createElement("div");
        detail.className = "hint";
        detail.textContent = row.detail;
        body.append(title, detail);
        li.append(mark, body);
        return li;
      })
    );
  } catch (err) {
    liveReadyEl.classList.remove("ready");
    liveReadyEl.classList.add("not-ready");
    if (liveReadyStatus) liveReadyStatus.textContent = "Could not run the live ready check. " + err;
  } finally {
    if (liveReadyRefresh) liveReadyRefresh.disabled = false;
  }
}
