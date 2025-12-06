(function () {
  const POLL_INTERVAL_MS = 3000;

  const els = {
    statusPill: document.getElementById("global-status-pill"),
    statusDot: document.getElementById("global-status-dot"),
    statusText: document.getElementById("global-status-text"),
    lastUpdate: document.getElementById("last-update-label"),

    sysStatusValue: document.getElementById("sys-status-value"),
    sysSymbolsValue: document.getElementById("sys-symbols-value"),
    sysExchangesValue: document.getElementById("sys-exchanges-value"),
    sysRedisValue: document.getElementById("sys-redis-value"),
    sysLlmValue: document.getElementById("sys-llm-value"),
    sysTgValue: document.getElementById("sys-tg-value"),

    exchangesBody: document.getElementById("exchanges-table-body"),
    marketBody: document.getElementById("market-table-body"),
    signalsList: document.getElementById("signals-list"),
    signalsCount: document.getElementById("signals-count-badge"),
  };

  let isRefreshing = false;

  async function fetchJson(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    return res.json();
  }

  function updateStatus(status) {
    const pill = els.statusPill;
    pill.classList.remove("degraded", "down");

    let label = "UNKNOWN";
    if (!status) {
      pill.classList.add("down");
    } else if (status.status === "ok") {
      label = "OK";
    } else if (status.status === "degraded") {
      label = "DEGRADED";
      pill.classList.add("degraded");
    } else {
      label = String(status.status || "DOWN").toUpperCase();
      pill.classList.add("down");
    }

    els.statusText.textContent = label;
    els.sysStatusValue.textContent = label;

    els.sysRedisValue.textContent = status?.redis ?? "—";
    els.sysLlmValue.textContent = status?.llm ?? "—";
    els.sysTgValue.textContent = status?.telegram ?? "—";
    els.sysSymbolsValue.textContent = status?.symbols ?? 0;

    const exchanges = status?.exchanges || {};
    els.sysExchangesValue.textContent = Object.keys(exchanges).length;

    if (status?.last_update_ts) {
      els.lastUpdate.textContent = `Last update: ${status.last_update_ts}`;
    } else {
      els.lastUpdate.textContent = "Last update: —";
    }

    const tbody = els.exchangesBody;
    tbody.innerHTML = "";
    for (const [name, info] of Object.entries(exchanges)) {
      const tr = document.createElement("tr");

      const tdName = document.createElement("td");
      tdName.textContent = name;

      const tdStatus = document.createElement("td");
      tdStatus.textContent = info.status || info;
      if (info.status === "excellent" || info === "excellent") {
        tdStatus.style.color = "var(--ok)";
      } else if (info.status === "unstable") {
        tdStatus.style.color = "var(--warn)";
      } else if (info.status === "down") {
        tdStatus.style.color = "var(--danger)";
      }

      const tdDelay = document.createElement("td");
      tdDelay.textContent =
        typeof info.delay_ms === "number" ? info.delay_ms.toFixed(1) : "—";

      const tdErr = document.createElement("td");
      tdErr.textContent =
        typeof info.error_rate === "number"
          ? `${(info.error_rate * 100).toFixed(2)}%`
          : "—";

      const tdUpdated = document.createElement("td");
      tdUpdated.textContent = info.updated_at || "—";

      tr.appendChild(tdName);
      tr.appendChild(tdStatus);
      tr.appendChild(tdDelay);
      tr.appendChild(tdErr);
      tr.appendChild(tdUpdated);
      tbody.appendChild(tr);
    }
  }

  function updateMarket(market) {
    const tbody = els.marketBody;
    tbody.innerHTML = "";

    if (!Array.isArray(market)) {
      return;
    }

    for (const item of market) {
      const tr = document.createElement("tr");

      const tdSym = document.createElement("td");
      tdSym.textContent = item.symbol;

      const tdMid = document.createElement("td");
      tdMid.textContent =
        typeof item.last_mid === "number"
          ? item.last_mid.toFixed(4)
          : String(item.last_mid ?? "—");

      const tdVol = document.createElement("td");
      tdVol.textContent =
        typeof item.volatility_1h === "number"
          ? (item.volatility_1h * 100).toFixed(2) + "%"
          : "—";

      const tdUpd = document.createElement("td");
      tdUpd.textContent = item.updated_at || "—";

      tr.appendChild(tdSym);
      tr.appendChild(tdMid);
      tr.appendChild(tdVol);
      tr.appendChild(tdUpd);
      tbody.appendChild(tr);
    }
  }

  function updateSignals(signals) {
    const list = els.signalsList;
    list.innerHTML = "";

    if (!Array.isArray(signals) || !signals.length) {
      els.signalsCount.textContent = "0";
      const empty = document.createElement("div");
      empty.textContent = "No signals yet.";
      empty.style.fontSize = "12px";
      empty.style.color = "var(--text-muted)";
      list.appendChild(empty);
      return;
    }

    const limited = signals.slice(0, 20);
    els.signalsCount.textContent = String(limited.length);

    for (const s of limited) {
      const card = document.createElement("div");
      card.className = "signal-card";

      const header = document.createElement("div");
      header.className = "signal-header";

      const sym = document.createElement("div");
      sym.className = "signal-symbol";
      sym.textContent = s.symbol;

      const route = document.createElement("div");
      route.className = "signal-route";
      route.textContent = `${s.buy_exchange} → ${s.sell_exchange}`;

      header.appendChild(sym);
      header.appendChild(route);

      const metrics = document.createElement("div");
      metrics.className = "signal-metrics";

      const spread = document.createElement("div");
      spread.className = "signal-tag";
      spread.textContent = `Spread: ${s.spread?.toFixed?.(4) ?? s.spread}`;

      const vol = document.createElement("div");
      vol.className = "signal-tag";
      vol.textContent = `Vol: $${s.volume_usd?.toFixed?.(2) ?? s.volume_usd}`;

      const net = document.createElement("div");
      net.className = "signal-tag";
      const netVal =
        typeof s.net_profit === "number"
          ? s.net_profit.toFixed(4)
          : String(s.net_profit ?? "—");
      net.textContent = `Net: ${netVal}`;
      if (typeof s.net_profit === "number") {
        if (s.net_profit > 0) {
          net.classList.add("signal-profit-positive");
        } else if (s.net_profit < 0) {
          net.classList.add("signal-profit-negative");
        }
      }

      metrics.appendChild(spread);
      metrics.appendChild(vol);
      metrics.appendChild(net);

      const meta = document.createElement("div");
      meta.className = "signal-meta";
      meta.textContent = s.created_at || "—";

      card.appendChild(header);
      card.appendChild(metrics);
      card.appendChild(meta);

      list.appendChild(card);
    }
  }

  async function refreshAll() {
    if (isRefreshing) return;
    isRefreshing = true;

    try {
      const [status, market, signals] = await Promise.allSettled([
        fetchJson("/api/status"),
        fetchJson("/api/market"),
        fetchJson("/api/signals"),
      ]);

      if (status.status === "fulfilled") {
        updateStatus(status.value);
      } else {
        updateStatus(null);
      }

      if (market.status === "fulfilled") {
        updateMarket(market.value);
      } else {
        updateMarket([]);
      }

      if (signals.status === "fulfilled") {
        updateSignals(signals.value);
      } else {
        updateSignals([]);
      }
    } catch (e) {
      console.error("Dashboard refresh error:", e);
      updateStatus(null);
      updateMarket([]);
      updateSignals([]);
    } finally {
      isRefreshing = false;
    }
  }

  window.addEventListener("load", () => {
    refreshAll();
    setInterval(refreshAll, POLL_INTERVAL_MS);
  });
})();
