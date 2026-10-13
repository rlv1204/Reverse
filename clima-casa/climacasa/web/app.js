"use strict";

const TOKEN = document.querySelector('meta[name="clima-token"]').content;
const $ = (id) => document.getElementById(id);
const POLL_MS = 5000;
const HEARTBEAT_MS = 30000;
const TEMP_DEBOUNCE_MS = 700;

let devices = [];
let selectedId = loadSelected();
let busy = 0;
let pendingTarget = null;
let tempTimer = null;
let lgStatus = { lgConfigured: false, lgCountry: "BR", lgError: null };

// ------------------------------------------------------------ comunicação

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "X-Clima-Token": TOKEN, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch { /* resposta vazia */ }
  if (!res.ok) throw new Error(data.error || `Erro ${res.status}`);
  return data;
}

async function load() {
  if (busy) return;
  try {
    const data = await api("GET", "/api/devices");
    if (busy) return; // um comando começou enquanto carregávamos
    devices = data.devices;
    lgStatus = data;
    render();
  } catch (err) {
    setConn(`Programa sem resposta: ${err.message}`, true);
  }
}

function heartbeat() {
  api("POST", "/api/heartbeat", {}).catch(() => {});
}

function loadSelected() {
  try { return localStorage.getItem("clima.selected") || ""; } catch { return ""; }
}
function saveSelected(id) {
  try { localStorage.setItem("clima.selected", id); } catch { /* sem armazenamento */ }
}

// ------------------------------------------------------------ comandos

function current() {
  return devices.find((d) => d.id === selectedId) || null;
}

async function send(body, optimistic) {
  const dev = current();
  if (!dev) return;
  const before = JSON.parse(JSON.stringify(dev));
  Object.assign(dev, optimistic || {});
  renderDevice(dev);
  busy++;
  $("control").classList.add("busy");
  try {
    const data = await api("POST", `/api/devices/${encodeURIComponent(dev.id)}/control`, body);
    if (data.device) {
      const i = devices.findIndex((d) => d.id === data.device.id);
      if (i >= 0) devices[i] = data.device;
    }
  } catch (err) {
    const i = devices.findIndex((d) => d.id === before.id);
    if (i >= 0) devices[i] = before;
    toast(err.message, true);
  } finally {
    busy--;
    if (!busy) $("control").classList.remove("busy");
    render();
  }
}

function setTarget(value) {
  const dev = current();
  if (!dev) return;
  const min = dev.tempMin ?? 16, max = dev.tempMax ?? 30, step = dev.tempStep || 1;
  value = Math.min(max, Math.max(min, Math.round(value / step) * step));
  pendingTarget = value;
  showTarget(dev, value);
  clearTimeout(tempTimer);
  tempTimer = setTimeout(() => {
    const v = pendingTarget;
    pendingTarget = null;
    send({ target: v }, { target: v });
  }, TEMP_DEBOUNCE_MS);
}

// ------------------------------------------------------------ desenho da tela

function render() {
  const hasDevices = devices.length > 0;
  $("empty").hidden = hasDevices;
  $("control").hidden = !hasDevices;
  if (hasDevices && !current()) selectedId = devices[0].id;
  renderTabs();
  const dev = current();
  if (dev) renderDevice(dev);
  else if (lgStatus.lgError) setConn(lgStatus.lgError, true);
  else setConn("Nenhum aparelho conectado", false);
}

function renderTabs() {
  const tabs = $("tabs");
  tabs.replaceChildren(...devices.map((d) => {
    const b = document.createElement("button");
    b.className = "tab";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(d.id === selectedId));
    const dot = document.createElement("i");
    dot.className = "dot" + (d.error ? " err" : d.power ? " on" : "");
    b.append(dot, document.createTextNode(d.name));
    b.addEventListener("click", () => {
      selectedId = d.id;
      saveSelected(d.id);
      pendingTarget = null;
      clearTimeout(tempTimer);
      render();
    });
    return b;
  }));
  tabs.hidden = devices.length < 2;
}

function icon(name) {
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  const use = document.createElementNS(svgNS, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

function fmt(n) {
  if (n === null || n === undefined) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(".", ",");
}

function showTarget(dev, value) {
  $("target").textContent = fmt(value);
  $("led").textContent = value == null ? "" : `${fmt(value)}°`;
  const slider = $("slider");
  slider.min = dev.tempMin ?? 16;
  slider.max = dev.tempMax ?? 30;
  slider.step = dev.tempStep || 1;
  if (value != null) slider.value = value;
  const pct = ((slider.value - slider.min) / (slider.max - slider.min || 1)) * 100;
  slider.style.setProperty("--pct", `${pct}%`);
}

function renderDevice(dev) {
  const loading = !dev.loaded;
  const unavailable = !dev.online;
  $("name").textContent = dev.name;
  $("chip-temp").hidden = dev.current == null;
  $("chip-temp").querySelector("b").textContent = `${fmt(dev.current)}°`;
  $("chip-hum").hidden = dev.humidity == null;
  $("chip-hum").querySelector("b").textContent = `${fmt(dev.humidity)}%`;

  const power = $("power");
  power.classList.toggle("on", !!dev.power);
  power.disabled = unavailable;
  power.title = dev.power ? "Desligar" : "Ligar";

  const unit = $("unit");
  unit.className = `unit ${dev.power ? "on" : "off"} ${dev.mode || ""}`;
  $("control").classList.toggle("off", !dev.power);

  showTarget(dev, pendingTarget ?? dev.target);
  const ticks = $("ticks");
  const steps = Math.round(((dev.tempMax ?? 30) - (dev.tempMin ?? 16)) / (dev.tempStep >= 1 ? dev.tempStep : 1));
  if (ticks.childElementCount !== steps + 1) {
    ticks.replaceChildren(...Array.from({ length: steps + 1 }, () => document.createElement("i")));
  }
  $("s-min").textContent = `${fmt(dev.tempMin)}°`;
  $("s-max").textContent = `${fmt(dev.tempMax)}°`;
  $("s-mid").textContent = `${fmt(Math.round(((dev.tempMin ?? 16) + (dev.tempMax ?? 30)) / 2))}°`;

  // modos
  $("modes").replaceChildren(...dev.modes.map((m) => {
    const b = document.createElement("button");
    b.className = `mode ${m.value}`;
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(m.value === dev.mode));
    b.disabled = unavailable;
    b.append(icon(m.icon), document.createTextNode(m.label));
    b.addEventListener("click", () => {
      if (m.value !== dev.mode) send({ mode: m.value }, { mode: m.value });
    });
    return b;
  }));

  fillPicker("fan", dev.fans, dev.fan, unavailable);
  fillPicker("swing", dev.swings, dev.swing, unavailable);

  $("features").replaceChildren(...dev.features.map((f) => {
    const b = document.createElement("button");
    b.className = "feature";
    b.setAttribute("aria-pressed", String(!!f.on));
    b.disabled = unavailable;
    b.title = f.label;
    const label = document.createElement("span");
    label.textContent = f.label;
    b.append(icon(f.icon), label);
    b.addEventListener("click", () => {
      const features = dev.features.map((x) => (x.key === f.key ? { ...x, on: !f.on } : x));
      send({ feature: f.key, on: !f.on }, { features });
    });
    return b;
  }));

  for (const id of ["minus", "plus", "slider"]) $(id).disabled = unavailable;

  const alert = $("alert");
  alert.hidden = !dev.error;
  alert.textContent = dev.error || "";

  if (loading) setConn("Conectando ao aparelho…", false);
  else if (dev.error) setConn(`${dev.source}: sem conexão`, true);
  else setConn(dev.brand === "gree" ? `Conectado pela rede local${dev.address ? " · " + dev.address : ""}` : "Conectado ao LG ThinQ", false);
}

function fillPicker(id, options, value, unavailable) {
  const select = $(id);
  const picker = $(`${id}-picker`);
  picker.hidden = options.length === 0;
  picker.classList.toggle("disabled", unavailable);
  select.disabled = unavailable;
  const key = JSON.stringify(options);
  if (select.dataset.key !== key) {
    select.replaceChildren(...options.map((o) => new Option(o.label, o.value)));
    select.dataset.key = key;
  }
  select.value = value ?? "";
  const match = options.find((o) => o.value === value);
  $(`${id}-label`).textContent = match ? match.label : "—";
}

function setConn(text, isError) {
  $("conn-text").textContent = text;
  $("conn").classList.toggle("err", isError);
}

let toastTimer;
function toast(text, isError) {
  const t = $("toast");
  t.textContent = text;
  t.classList.toggle("bad", !!isError);
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, isError ? 7000 : 3500);
}

// ------------------------------------------------------------ eventos da tela principal

$("power").addEventListener("click", () => {
  const dev = current();
  if (dev) send({ power: !dev.power }, { power: !dev.power });
});
$("minus").addEventListener("click", () => {
  const dev = current();
  if (dev) setTarget((pendingTarget ?? dev.target ?? 24) - (dev.tempStep || 1));
});
$("plus").addEventListener("click", () => {
  const dev = current();
  if (dev) setTarget((pendingTarget ?? dev.target ?? 24) + (dev.tempStep || 1));
});
$("slider").addEventListener("input", (e) => setTarget(Number(e.target.value)));
$("fan").addEventListener("change", (e) => send({ fan: e.target.value }, { fan: e.target.value }));
$("swing").addEventListener("change", (e) => send({ swing: e.target.value }, { swing: e.target.value }));

document.addEventListener("keydown", (e) => {
  if ($("settings").open || e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
  if (e.key === "ArrowUp" || e.key === "+") $("plus").click();
  if (e.key === "ArrowDown" || e.key === "-") $("minus").click();
});

// ------------------------------------------------------------ configurações

const dialog = $("settings");
document.querySelectorAll("[data-open-settings]").forEach((b) => b.addEventListener("click", openSettings));

function openSettings() {
  $("lg-country").value = lgStatus.lgCountry || "BR";
  $("lg-token").value = "";
  $("lg-remove").hidden = !lgStatus.lgConfigured;
  const status = $("lg-status");
  if (lgStatus.lgError) {
    status.textContent = lgStatus.lgError;
    status.className = "hint bad";
  } else if (lgStatus.lgConfigured) {
    const n = devices.filter((d) => d.brand === "lg").length;
    status.textContent = `Conta LG conectada (${n} ar-condicionado${n === 1 ? "" : "s"}).`;
    status.className = "hint ok";
  } else {
    status.textContent = "Conta LG ainda não conectada.";
    status.className = "hint";
  }
  renderNames();
  dialog.showModal();
}

function renderNames() {
  const box = $("names");
  if (!devices.length) {
    box.textContent = "Nenhum aparelho encontrado ainda.";
    box.className = "hint";
    return;
  }
  box.className = "";
  box.replaceChildren(...devices.map((d) => {
    const row = document.createElement("div");
    row.className = "name-row";
    const brand = document.createElement("small");
    brand.textContent = d.brand === "lg" ? "LG" : "Gree";
    const input = document.createElement("input");
    input.value = d.name;
    input.maxLength = 40;
    input.setAttribute("aria-label", `Nome do aparelho ${d.name}`);
    input.addEventListener("change", async () => {
      try {
        await api("POST", `/api/devices/${encodeURIComponent(d.id)}/rename`, { name: input.value });
        toast("Nome salvo");
        load();
      } catch (err) { toast(err.message, true); }
    });
    row.append(brand, input);
    if (d.brand === "gree") {
      const del = document.createElement("button");
      del.type = "button";
      del.className = "icon";
      del.title = "Remover este aparelho da lista";
      del.append(icon("x"));
      del.addEventListener("click", async () => {
        if (!confirm(`Remover "${d.name}" da lista? Ele volta se você procurar os aparelhos de novo.`)) return;
        await api("POST", "/api/gree/remove", { mac: d.id.slice(5) }).catch((err) => toast(err.message, true));
        await load();
        renderNames();
      });
      row.append(del);
    } else {
      row.append(Object.assign(document.createElement("span"), { className: "spacer" }));
    }
    return row;
  }));
}

async function withButton(button, fn) {
  const text = button.textContent;
  button.disabled = true;
  button.textContent = "Aguarde…";
  try { await fn(); } finally { button.disabled = false; button.textContent = text; }
}

async function scan(ip) {
  const out = $("scan-result");
  out.className = "hint";
  out.textContent = "Procurando na rede… (leva alguns segundos)";
  try {
    const r = await api("POST", "/api/gree/discover", ip ? { ip } : {});
    const parts = [];
    if (r.found === 0) {
      out.className = "hint bad";
      out.textContent = "Nenhum aparelho Gree respondeu. Confira se o computador está no mesmo Wi-Fi e se o Firewall do Windows liberou o programa (veja o LEIA-ME).";
      return;
    }
    parts.push(`${r.found} aparelho(s) encontrado(s)`);
    if (r.new.length) parts.push(`novos: ${r.new.map((d) => d.name).join(", ")}`);
    if (r.failed.length) parts.push(`não pareados: ${r.failed.map((d) => d.ip).join(", ")}`);
    out.className = r.failed.length ? "hint bad" : "hint ok";
    out.textContent = parts.join(" — ");
    await load();
    renderNames();
  } catch (err) {
    out.className = "hint bad";
    out.textContent = err.message;
  }
}

$("scan").addEventListener("click", (e) => withButton(e.currentTarget, () => scan()));
$("add-ip").addEventListener("click", (e) => {
  const ip = $("manual-ip").value.trim();
  if (!ip) { toast("Digite o IP do aparelho", true); return; }
  withButton(e.currentTarget, () => scan(ip));
});

$("lg-save").addEventListener("click", (e) => withButton(e.currentTarget, async () => {
  const token = $("lg-token").value.trim();
  const status = $("lg-status");
  if (!token) { toast("Cole o token da LG antes de salvar", true); return; }
  try {
    const r = await api("POST", "/api/lg/token", { token, country: $("lg-country").value });
    status.textContent = `Conectado! ${r.devices} ar-condicionado(s) LG encontrado(s).`;
    status.className = "hint ok";
    $("lg-token").value = "";
    $("lg-remove").hidden = false;
    await load();
    renderNames();
  } catch (err) {
    status.textContent = err.message;
    status.className = "hint bad";
  }
}));

$("lg-remove").addEventListener("click", async () => {
  if (!confirm("Desconectar a conta LG deste programa?")) return;
  await api("POST", "/api/lg/token", { token: "" }).catch((err) => toast(err.message, true));
  lgStatus.lgConfigured = false;
  await load();
  openSettings();
});

$("quit").addEventListener("click", async () => {
  if (!confirm("Encerrar o Clima Casa?")) return;
  await api("POST", "/api/quit", {}).catch(() => {});
  dialog.close();
  document.body.replaceChildren(Object.assign(document.createElement("p"), {
    className: "empty", textContent: "Programa encerrado. Pode fechar esta janela.",
  }));
  window.close();
});

// ------------------------------------------------------------ início

load();
heartbeat();
setInterval(load, POLL_MS);
setInterval(heartbeat, HEARTBEAT_MS);
document.addEventListener("visibilitychange", () => { if (!document.hidden) { heartbeat(); load(); } });
