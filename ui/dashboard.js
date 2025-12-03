async function fetchJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Request failed: ${path}`);
  return res.json();
}

async function renderStatus() {
  const el = document.getElementById('status');
  try {
    const health = await fetchJson('/health');
    el.textContent = `Status: ${health.status} | Redis: ${health.redis_ok ? 'ok' : 'down'}`;
  } catch (err) {
    el.textContent = `Status unavailable: ${err}`;
  }
}

async function renderSignals() {
  const container = document.getElementById('signals');
  container.innerHTML = '<h2>Signals</h2>';
  try {
    const data = await fetchJson('/signals');
    const list = document.createElement('ul');
    data.signals.forEach((s) => {
      const li = document.createElement('li');
      li.textContent = `${s.route.symbol}: buy ${s.route.buy_exchange} -> sell ${s.route.sell_exchange} (${s.expected_profit_bps.toFixed(2)} bps)`;
      list.appendChild(li);
    });
    container.appendChild(list);
  } catch (err) {
    container.append(`Failed to load signals: ${err}`);
  }
}

renderStatus();
renderSignals();
setInterval(renderStatus, 10000);
setInterval(renderSignals, 15000);
