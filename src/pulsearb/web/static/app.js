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
const blockBanner = document.getElementById("block-banner");
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
const execPaper = document.getElementById("exec-paper");
const execLive = document.getElementById("exec-live");
const liveConfirm = document.getElementById("live-confirm");
const liveConfirmGo = document.getElementById("live-confirm-go");
const liveConfirmCancel = document.getElementById("live-confirm-cancel");
const ledeEl = document.getElementById("lede");
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
let lastKilled = false;
let soundOn = true;
let audioCtx = null;
let seenTradeKeys = null;
let seenFillKeys = null;
let lastAlertAt = 0;
let liveReadyState = { ready: false, armed: false };
let desk = {
  notional: 5,
  auto_invest: false,
  all_assets: false,
  assets: ["BTC", "ETH", "SOL", "XRP"],
  venues: ["coinbase", "kraken", "gemini", "oanda", "robinhood"],
  kinds: ["cross_venue", "dislocation", "triangular"],
  cap: 250,
  min_notional: 0.1,
  presets: [0.1, 0.25, 0.5, 1, 2, 3, 4, 5, 10, 25, 50, 100],
  asset_choices: ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "LINK", "AVAX", "DOT", "UNI", "AAVE", "EUR", "GBP"],
  venue_choices: [
    { id: "coinbase", label: "Coinbase" },
    { id: "kraken", label: "Kraken" },
    { id: "gemini", label: "Gemini" },
    { id: "oanda", label: "OANDA" },
    { id: "robinhood", label: "Robinhood" },
  ],
  kind_choices: [
    { id: "cross_venue", label: "Price gaps" },
    { id: "dislocation", label: "Coinbase dislocations" },
    { id: "triangular", label: "Same-exchange triangles" },
  ],
  live: false,
  live_venue: "coinbase",
  live_venue_choices: [
    { id: "coinbase", label: "Coinbase" },
    { id: "kraken", label: "Kraken" },
    { id: "gemini", label: "Gemini" },
    { id: "oanda", label: "OANDA" },
    { id: "robinhood", label: "Robinhood" },
  ],
  live_venues_ready: [],
  schedule_enabled: false,
  schedule_start: "22:00",
  schedule_stop: "06:00",
  schedule_active: true,
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

function fmtTap(n) {
  const x = Number(n);
  if (!Number.isFinite(x)) return "—";
  return x < 1 ? x.toFixed(2) : String(Math.round(x * 100) / 100 === Math.round(x) ? Math.round(x) : x.toFixed(2));
}

function clockTime(ts) {
  const value = Number(ts);
  if (!Number.isFinite(value) || value <= 0) return "";
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString();
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
        live_venue: desk.live_venue,
        schedule_enabled: desk.schedule_enabled,
        schedule_start: desk.schedule_start,
        schedule_stop: desk.schedule_stop,
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

function investLabel() {
  return desk.live ? `Buy & sell $${fmtTap(desk.notional)}` : `Invest $${fmtTap(desk.notional)}`;
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

function tradeCard(trade) {
  const li = document.createElement("li");
  li.className = `trade-card ${trade.status === "blocked" || trade.status === "open" ? "blocked" : ""}`;
  const head = document.createElement("div");
  head.className = "trade-head";
  const mode = document.createElement("span");
  mode.className = `trade-mode${trade.execution === "live" ? " live" : ""}`;
  mode.textContent = trade.execution === "live" ? "LIVE" : "PAPER";
  const status = document.createElement("span");
  status.className = `trade-status ${trade.status || ""}`;
  status.textContent = trade.status || "";
  const when = document.createElement("span");
  when.className = "leg-meta";
  const opened = clockTime(trade.opened_at);
  const closed = clockTime(trade.closed_at);
  when.textContent = opened && closed && closed !== opened ? `Opened ${opened} · closed ${closed}` : opened ? `Opened ${opened}` : "";
  head.append(mode, status, when);
  const legs = document.createElement("ol");
  legs.className = "trade-legs";
  (trade.legs || []).forEach((leg, index) => {
    const row = document.createElement("li");
    const qty = leg.qty ? fmt(leg.qty, 6) : "0";
    const px = leg.price ? fmt(leg.price, 2) : "—";
    const usd = leg.notional ? `$${fmt(leg.notional, 2)}` : "";
    const label = leg.flatten ? "sold leftover to USD" : leg.note || "";
    row.innerHTML = "";
    const line = document.createElement("div");
    line.textContent = `${index + 1}. ${String(leg.side || "").toUpperCase()} ${leg.symbol} · ${qty} @ ${px} ${usd}`.trim();
    row.append(line);
    if (label) {
      const meta = document.createElement("div");
      meta.className = "leg-meta";
      meta.textContent = label;
      row.append(meta);
    }
    legs.append(row);
  });
  const close = document.createElement("div");
  close.className = "close-label";
  const cashBits = [];
  if (Number(trade.spent_usd) > 0) cashBits.push(`spent $${fmt(trade.spent_usd, 2)}`);
  if (Number(trade.received_usd) > 0) cashBits.push(`back $${fmt(trade.received_usd, 2)}`);
  close.textContent = [trade.close_label, cashBits.join(" · ")].filter(Boolean).join(" · ");
  li.append(head, legs, close);
  return li;
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

function paintExecToggle() {
  const live = Boolean(desk.live);
  if (execPaper) execPaper.classList.toggle("on", !live);
  if (execLive) execLive.classList.toggle("on", live);
  if (ledeEl) {
    ledeEl.textContent = live
      ? `Live on ${liveVenueLabel()}: USD round-trips. Each tap buys with USD and aims to finish back in USD.`
      : "Paper first. Switch to Live for real Coinbase or Kraken taps. Cross-exchange gaps stay paper.";
  }
}

function hideLiveConfirm() {
  if (liveConfirm) liveConfirm.hidden = true;
}

async function setExecution(mode) {
  hideLiveConfirm();
  try {
    const payload = { mode };
    if (mode === "live") payload.confirm = "I_UNDERSTAND_THE_RISK";
    const res = await fetch("/api/execution", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Could not switch mode");
    if (data.desk) desk = { ...desk, ...data.desk };
    paintDesk();
    paintExecToggle();
    paintLiveReady();
    paintSecurity();
    render();
    showToast(data.note || (mode === "live" ? `Live ${liveVenueLabel()} is on.` : "Back on paper."));
  } catch (err) {
    showToast(String(err.message || err));
    paintExecToggle();
  }
}

function chip(label, on, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `chip${on ? " on" : ""}`;
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function liveVenueLabel() {
  const id = desk.live_venue || "coinbase";
  const row = (desk.live_venue_choices || []).find((item) => item.id === id);
  return row ? row.label : id;
}

function paintDesk() {
  if (!amountInput) return;
  if (document.activeElement !== amountInput) {
    amountInput.value = String(desk.notional);
    amountInput.max = String(desk.cap);
    amountInput.min = String(desk.min_notional || 0.1);
    amountInput.step = Number(desk.min_notional) < 1 || Number(desk.notional) < 1 ? "0.01" : "1";
  }
  presetsEl.replaceChildren(
    ...desk.presets.map((amt) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `preset${Number(desk.notional) === Number(amt) ? " on" : ""}`;
      btn.textContent = `$${fmtTap(amt)}`;
      btn.addEventListener("click", () => saveDesk({ notional: amt }));
      return btn;
    })
  );
  const autoAllowed = desk.auto_allowed !== false;
  modePick.classList.toggle("on", !desk.auto_invest);
  modeAuto.classList.toggle("on", desk.auto_invest);
  modeAuto.disabled = !autoAllowed;
  modeAuto.title = autoAllowed
    ? ""
    : "While live, turn on Only between (a start and stop time) before Auto can run.";
  amountHint.textContent = desk.live
    ? `This tap: $${fmtTap(desk.notional)} on ${liveVenueLabel()}. Session budget $${fmt(desk.budget || desk.cap, 0)} · $${fmt(desk.budget_left ?? desk.cap, 2)} left (${desk.taps_left ?? "?"} more taps). Coins under $1 still buy a fraction.`
    : "Each tap is this size. $1–$5 is typical (paper can go to $0.10). Paper until you go live. Coins under $1 still buy a fraction.";
  if (modeHint) {
    modeHint.textContent = autoAllowed
      ? (desk.live
          ? "Picking is safer. Auto uses your amount on matching Coinbase or Kraken USD-start rows."
          : "Picking is safer. Auto only takes Coinbase or Kraken same-exchange rows that buy with USD. Cross-venue stays click-to-paper.")
      : "Live: Auto stays off unless you set an Auto window (for example 10:00 PM to 6:00 AM). Cross-venue gaps stay paper.";
  }
  const schedOff = document.getElementById("sched-off");
  const schedOn = document.getElementById("sched-on");
  const schedStart = document.getElementById("sched-start");
  const schedStop = document.getElementById("sched-stop");
  const schedHint = document.getElementById("sched-hint");
  const windowOn = Boolean(desk.schedule_enabled);
  if (schedOff) schedOff.classList.toggle("on", !windowOn);
  if (schedOn) schedOn.classList.toggle("on", windowOn);
  if (schedStart && document.activeElement !== schedStart) schedStart.value = desk.schedule_start || "22:00";
  if (schedStop && document.activeElement !== schedStop) schedStop.value = desk.schedule_stop || "06:00";
  if (schedHint) {
    if (windowOn) {
      const open = desk.schedule_active !== false;
      schedHint.textContent = open
        ? `Auto window is on (${desk.schedule_start}–${desk.schedule_stop}, this computer’s clock). Auto can fire until ${desk.schedule_stop}.`
        : `Auto is waiting until ${desk.schedule_start} (this computer’s clock). It will stop at ${desk.schedule_stop}. Overnight windows wrap midnight.`;
    } else if (desk.live) {
      schedHint.textContent =
        "While live, Auto only runs if you turn on Only between. Example: 10:00 PM to 6:00 AM. Times use this computer’s clock.";
    } else {
      schedHint.textContent =
        "Times use this computer’s clock. Example: 10:00 PM to 6:00 AM overnight. Optional on paper; required for live Auto.";
    }
  }
  const liveVenueChips = document.getElementById("live-venue-chips");
  if (liveVenueChips) {
    const choices = desk.live_venue_choices || [
      { id: "coinbase", label: "Coinbase" },
      { id: "kraken", label: "Kraken" },
    ];
    const ready = desk.live_venues_ready || [];
    liveVenueChips.replaceChildren(
      ...choices.map((row) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = row.label;
        btn.classList.toggle("on", (desk.live_venue || "coinbase") === row.id);
        const hasKeys = !ready.length || ready.includes(row.id);
        btn.title = hasKeys ? "" : `Save keys\\${row.id}.json first.`;
        btn.addEventListener("click", () => {
          saveDesk({ live_venue: row.id });
          paintLiveReady();
        });
        return btn;
      })
    );
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
  paintExecToggle();
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

function emptyOppsMessage() {
  const kinds = desk.kinds || [];
  const onlyTri = kinds.length === 1 && kinds[0] === "triangular";
  const onlyDis = kinds.length === 1 && kinds[0] === "dislocation";
  const range = priceFilterLabel();
  const feeds = (snapshot.stats && snapshot.stats.feed_status) || {};
  const demo = Boolean(feeds.simulator);
  if (range && onlyTri) {
    return `No triangles ${range}. These routes use BTC/ETH, which that filter hides. Set Show pairs to Any price.`;
  }
  if (range) {
    return `No matching trades ${range} right now. Try Any price, or pick more coins.`;
  }
  if (onlyTri) {
    return demo
      ? "Waiting for a same-exchange triangle. Demo injects one about every 18 seconds. If Show pairs is Under $5, set it to Any. Auto cannot fire until a row appears."
      : "Same-exchange triangles are rare on live prices — three Coinbase fees eat most edges. Turn on Coinbase dislocations (USD vs USDC) as well. Auto cannot fire until a row appears.";
  }
  if (onlyDis) {
    return demo
      ? "Waiting for a Coinbase USD vs USDC dislocation. Demo injects one about every 18 seconds."
      : "Watching USD vs USDC books. A takeable live tap needs the gap to clear two venue fees. Raising the tap to $10 does not create that gap.";
  }
  return "No matching trades right now. Pick more coins, or wait for the next scan.";
}

function friendlyOpp(row) {
  const legs = row.legs || [];
  const buy = legs.find((leg) => leg.action === "buy");
  const sell = legs.find((leg) => leg.action === "sell");
  if (row.kind === "dislocation") {
    return row.summary || "Coinbase USD vs USDC dislocation — buy, sell, finish toward USD";
  }
  if (row.kind === "triangular") {
    const venue = (buy && buy.venue) || (legs[0] && legs[0].venue) || "";
    if (row.summary) return row.summary;
    return `Same-exchange buy & sell on ${venue} — finishes back in USD`;
  }
  if (row.kind === "alert") return row.summary;
  if (buy && sell) {
    if (buy.venue !== sell.venue) {
      return `Buy ${buy.symbol} on ${buy.venue}, sell on ${sell.venue} (paper only — live cannot hold a coin to move it)`;
    }
    return `Buy ${buy.symbol} on ${buy.venue}, sell on ${sell.venue}`;
  }
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
        <div class="sym">${row.venue} · ${row.native_symbol}${row.asset_class === "fx" ? " · FX" : ""}</div>
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
    empty.textContent = emptyOppsMessage();
    opps.replaceChildren(empty);
  } else {
    opps.replaceChildren(
      ...mine.map((row) => {
        const li = document.createElement("li");
        li.className = "opp-card";
        const kicker = document.createElement("div");
        kicker.className = "edge";
        kicker.textContent = `${row.kind_label || row.kind} · ${fmt(row.net_edge_bps, 1)} bps net · ${
          desk.live && row.live_ok ? "LIVE" : row.paper_only ? "PAPER ONLY" : "PAPER"
        }`;
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
          btn.textContent = investLabel();
          btn.addEventListener("click", () => invest(row.id, btn));
          li.append(btn);
          if (desk.live) {
            const note = document.createElement("div");
            note.className = "hint";
            note.textContent = `Live ${liveVenueLabel()}: buys with USD, then sells back toward USD.`;
            li.append(note);
          } else if (row.paper_only) {
            const note = document.createElement("div");
            note.className = "hint";
            note.textContent =
              "Auto skips this. You can still paper-trade it. Auto only takes Coinbase or Kraken same-exchange rows that buy with USD.";
            li.append(note);
          }
        } else if (row.paper_only) {
          const note = document.createElement("div");
          note.className = "hint";
          note.textContent = desk.live
            ? `Paper only while Live is on — this gap is not a ${liveVenueLabel()} USD round-trip.`
            : "Auto skips this. Click Invest to paper-trade it. Auto only takes Coinbase or Kraken same-exchange rows that buy with USD.";
          li.append(note);
        } else if (row.pending && desk.auto_invest) {
          const note = document.createElement("div");
          note.className = "hint";
          note.textContent = "Auto will take this if it is still open.";
          li.append(note);
        } else if (!row.executable) {
          const note = document.createElement("div");
          note.className = "hint";
          if (row.kind === "triangular") {
            note.textContent =
              "Watch only — after three exchange fees this edge is below the 25 bps triangle take floor.";
          } else if (row.kind === "dislocation") {
            note.textContent =
              "Watch only — after fees this USD/USDC gap is below the 15 bps dislocation take floor.";
          } else if (row.kind === "cross_venue") {
            note.textContent =
              "Watch only — after two-exchange fees this gap is below the 25 bps paper click floor. Live never takes cross-venue.";
          } else {
            note.textContent = "Watch only — delayed data, not an order.";
          }
          li.append(note);
        }
        return li;
      })
    );
  }

  const trades = snapshot.trades || [];
  const fillRows = snapshot.fills || [];
  const completed = fillRows.filter((row) => row.status === "filled");
  if (fillsMeta) {
    if (!trades.length && !completed.length) {
      fillsMeta.textContent = "";
    } else if (trades.length) {
      const last = trades[0];
      fillsMeta.textContent = `${trades.length} trade${trades.length === 1 ? "" : "s"} · last ${last.status}`;
    } else {
      const last = completed[completed.length - 1];
      fillsMeta.textContent = `${completed.length} complete · last ${last.side} ${last.symbol}`;
    }
  }
  if (trades.length) {
    fills.replaceChildren(...trades.map(tradeCard));
  } else if (!fillRows.length) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "No trades yet. When you tap a row, it shows here marked PAPER or LIVE: opened, each leg, and closed back to USD.";
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
  const cashUsd = document.getElementById("cash-usd");
  const cashTap = document.getElementById("cash-tap");
  const cashSession = document.getElementById("cash-session");
  const cashTaps = document.getElementById("cash-taps");
  if (cashUsd) {
    const usd = Number(s.usd_spendable);
    const cash = Number(s.cash_usd);
    if (s.usd_spendable == null && (s.cash_usd == null || s.cash_usd === "")) {
      cashUsd.textContent = "—";
    } else if (Number.isFinite(usd) && Number.isFinite(cash) && cash > usd + 0.009) {
      cashUsd.textContent = `$${fmt(usd, 2)} USD ($${fmt(cash, 2)} incl. USDC/USDT)`;
    } else if (Number.isFinite(usd)) {
      cashUsd.textContent = `$${fmt(usd, 2)} USD`;
    } else {
      cashUsd.textContent = `$${fmt(cash, 2)}`;
    }
  }
  if (blockBanner) {
    const reason = s.idle_reason || (desk && desk.idle_reason) || "";
    blockBanner.textContent = reason;
    blockBanner.hidden = !reason;
    blockBanner.classList.toggle("show", Boolean(reason));
  }
  if (cashTap) cashTap.textContent = `$${fmtTap(desk.notional)}`;
  if (cashSession) {
    if (desk.budget != null) {
      cashSession.textContent = `$${fmt(desk.budget_left ?? 0, 2)} of $${fmt(desk.budget, 0)}`;
    } else if (live) {
      cashSession.textContent = "No cap set";
    } else {
      cashSession.textContent = "Paper";
    }
  }
  if (cashTaps) {
    cashTaps.textContent = desk.taps_left == null ? (live ? "—" : "Paper") : String(desk.taps_left);
  }
  document.getElementById("kpi-tri").textContent = s.triangles ?? 0;
  document.getElementById("kpi-up").textContent = `${fmt(s.uptime_s, 0)}s`;
  const feeds = s.feed_status || {};
  feedBadge.textContent = Object.entries(feeds)
    .filter(([k]) => k !== "yahoo" && k !== "bitstamp")
    .map(([k, v]) => `${k}:${v}`).join(" · ") || "waiting";
  killBtn.classList.toggle("on", Boolean(s.killed));
  killBtn.textContent = s.killed ? "Resume" : "Kill switch";
  const reportRows = s.report_rows ?? 0;
  exportBtn.textContent = reportRows ? `Export my trades (${reportRows})` : "Export my trades";
  if (reportPath) {
    reportPath.textContent = s.report_path ? `Profit report file: ${s.report_path}` : "";
  }
}

async function invest(id, btn) {
  btn.disabled = true;
  btn.textContent = desk.live ? "Buying & selling…" : "Investing…";
  try {
    const res = await fetch("/api/invest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Could not invest");
    showToast(
      desk.live
        ? `Round-trip sent ($${fmtTap(desk.notional)}). Check Your trades — opened, each leg, and close back to USD.`
        : `Invested $${fmtTap(desk.notional)}. Check Your trades.`
    );
  } catch (err) {
    showToast(String(err.message || err));
    btn.disabled = false;
    btn.textContent = investLabel();
  }
}

filter.addEventListener("input", render);

async function clearBoards(which) {
  const opportunities = which === "opps" || which === "both";
  const fills = which === "fills" || which === "both";
  try {
    const res = await fetch("/api/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ opportunities, fills }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Could not clear");
    if (opportunities) {
      snapshot.opportunities = [];
      seenTradeKeys = new Set();
    }
    if (fills) {
      snapshot.fills = [];
      snapshot.trades = [];
      seenFillKeys = new Set();
    }
    render();
    showToast(
      opportunities && fills
        ? "Cleared both lists. New cards are marked PAPER or LIVE."
        : opportunities
          ? "Cleared Trades for you. The next scan will fill it again."
          : "Cleared Your trades. Export first next time if you want to keep the old blotter."
    );
  } catch (err) {
    showToast(String(err.message || err));
  }
}

const clearOppsBtn = document.getElementById("clear-opps");
const clearFillsBtn = document.getElementById("clear-fills");
if (clearOppsBtn) clearOppsBtn.addEventListener("click", () => clearBoards("opps"));
if (clearFillsBtn) clearFillsBtn.addEventListener("click", () => clearBoards("fills"));

killBtn.addEventListener("click", async () => {
  const killed = Boolean(snapshot.stats && snapshot.stats.killed);
  await fetch(killed ? "/api/resume" : "/api/kill", { method: "POST" });
});

modePick.addEventListener("click", () => saveDesk({ auto_invest: false }));
modeAuto.addEventListener("click", () => {
  if (desk.auto_allowed === false) {
    showToast("While live, turn on Only between (start and stop times) before Auto can run.");
    return;
  }
  saveDesk({ auto_invest: true });
});
amountInput.addEventListener("change", () => saveDesk({ notional: Number(amountInput.value) }));
const schedOffBtn = document.getElementById("sched-off");
const schedOnBtn = document.getElementById("sched-on");
const schedStartInput = document.getElementById("sched-start");
const schedStopInput = document.getElementById("sched-stop");
if (schedOffBtn) schedOffBtn.addEventListener("click", () => saveDesk({ schedule_enabled: false, auto_invest: desk.live ? false : desk.auto_invest }));
if (schedOnBtn) schedOnBtn.addEventListener("click", () => saveDesk({ schedule_enabled: true }));
if (schedStartInput) schedStartInput.addEventListener("change", () => saveDesk({ schedule_start: schedStartInput.value }));
if (schedStopInput) schedStopInput.addEventListener("change", () => saveDesk({ schedule_stop: schedStopInput.value }));
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
      const wasLive = Boolean(desk.live);
      desk = { ...desk, ...snapshot.desk };
      if (!deskReady) {
        deskReady = true;
        const saved = readSavedDesk();
        if (saved) {
          const hidden = new Set(["yahoo", "bitstamp"]);
          if (Array.isArray(saved.venues)) {
            saved.venues = saved.venues.filter((item) => !hidden.has(item));
          }
          saveDesk(saved);
        } else {
          paintDesk();
        }
      } else if (Boolean(desk.live) !== wasLive) {
        paintDesk();
        paintLiveReady();
      }
    }
    noticeNewTrades(snapshot);
    noticeNewFills(snapshot);
    const killedNow = Boolean(snapshot.stats && snapshot.stats.killed);
    if (killedNow !== lastKilled) {
      lastKilled = killedNow;
      paintLiveReady();
      paintSecurity();
    }
    scheduleRender();
  };
  ws.onclose = () => setTimeout(connect, 1200);
}
connect();
paintDesk();
paintSecurity();
paintLiveReady();
if (liveReadyRefresh) liveReadyRefresh.addEventListener("click", () => paintLiveReady());
if (execPaper) {
  execPaper.addEventListener("click", () => {
    hideLiveConfirm();
    if (desk.live) setExecution("paper");
  });
}
if (execLive) {
  execLive.addEventListener("click", () => {
    if (desk.live) {
      hideLiveConfirm();
      return;
    }
    if (!liveReadyState.ready) {
      showToast("Live ready check must pass first. Fix the FAIL rows, then Check again.");
      paintLiveReady();
      return;
    }
    if (liveConfirm) liveConfirm.hidden = false;
  });
}
if (liveConfirmGo) liveConfirmGo.addEventListener("click", () => setExecution("live"));
if (liveConfirmCancel) liveConfirmCancel.addEventListener("click", hideLiveConfirm);

async function paintSecurity() {
  if (!guardBanner) return;
  try {
    const res = await fetch("/api/security");
    if (!res.ok) return;
    const data = await res.json();
    const bits = [
      data.network === "lan" ? "On your Wi-Fi · PIN required" : "This computer only",
      data.execution === "live" ? `LIVE · cap $${fmt(data.live_cap, 0)}` : "Paper trading",
      data.keys_file ? "Key file on this PC" : "No Coinbase or Kraken key file",
      data.killed && data.execution === "live"
        ? "Kill switch paused new orders — still LIVE"
        : data.killed
          ? "Kill switch on"
          : "",
      data.note,
    ];
    guardBanner.textContent = bits.filter(Boolean).join(" · ");
    paintPhonePair();
  } catch (err) {
    /* ignore */
  }
}

async function paintLiveReady() {
  if (!liveReadyEl || !liveReadyList) return;
  if (liveReadyRefresh) liveReadyRefresh.disabled = true;
  if (liveReadyStatus) liveReadyStatus.textContent = `Checking ${liveVenueLabel()} keys and cash…`;
  try {
    const res = await fetch("/api/live-ready");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "HTTP " + res.status);
    liveReadyState = { ready: Boolean(data.ready), armed: Boolean(data.armed) };
    liveReadyEl.classList.toggle("ready", Boolean(data.ready) || Boolean(data.armed));
    liveReadyEl.classList.toggle("not-ready", !data.ready && !data.armed);
    if (liveReadyStatus) liveReadyStatus.textContent = data.note || "";
    paintExecToggle();
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

const PANE_KEY = "cybersym-pane";
const PANES = ["trades", "desk", "markets", "more"];

function isStandaloneApp() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

function isPhoneShell() {
  return window.matchMedia("(max-width: 720px)").matches || isStandaloneApp();
}

function setPane(name) {
  const next = PANES.includes(name) ? name : "trades";
  document.body.dataset.pane = next;
  document.querySelectorAll("#phone-dock [data-pane]").forEach((btn) => {
    const on = btn.dataset.pane === next;
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  try {
    localStorage.setItem(PANE_KEY, next);
  } catch (err) {
    /* private mode */
  }
}

function setupPhoneShell() {
  const dock = document.getElementById("phone-dock");
  if (dock) {
    dock.querySelectorAll("[data-pane]").forEach((btn) => {
      btn.addEventListener("click", () => setPane(btn.dataset.pane));
    });
  }
  let saved = "trades";
  try {
    saved = localStorage.getItem(PANE_KEY) || "trades";
  } catch (err) {
    saved = "trades";
  }
  setPane(saved);
  const banner = document.getElementById("phone-install");
  if (banner) banner.hidden = !(isPhoneShell() && !isStandaloneApp());
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
  }
}

async function paintPhonePair() {
  const box = document.getElementById("phone-pair");
  const list = document.getElementById("phone-urls");
  if (!box || !list) return;
  if (isPhoneShell()) {
    box.hidden = true;
    return;
  }
  try {
    const res = await fetch("/api/phone");
    if (!res.ok) return;
    const data = await res.json();
    const urls = data.urls || [];
    if (!data.lan || !urls.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    list.replaceChildren(
      ...urls.map((url) => {
        const li = document.createElement("li");
        const link = document.createElement("a");
        link.href = url;
        link.textContent = url;
        const copy = document.createElement("button");
        copy.type = "button";
        copy.className = "phone-copy";
        copy.textContent = "Copy";
        copy.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(url);
            copy.textContent = "Copied";
            setTimeout(() => {
              copy.textContent = "Copy";
            }, 1200);
          } catch (err) {
            showToast(url);
          }
        });
        li.append(link, copy);
        return li;
      })
    );
  } catch (err) {
    box.hidden = true;
  }
}

setupPhoneShell();
paintPhonePair();

