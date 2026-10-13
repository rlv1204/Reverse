"use strict";

const TOKEN = document.querySelector('meta[name="clima-token"]').content;
const $ = (id) => document.getElementById(id);
const SVG_NS = "http://www.w3.org/2000/svg";
const POLL_MS = 5000;
const RETRY_MS = 3000;
const TEMP_DEBOUNCE_MS = 700;
const UPDATE_CHECK_MS = 6 * 3600 * 1000;

// Arco do mostrador: 270°, começando embaixo à esquerda (135°).
const DIAL = { cx: 120, cy: 120, r: 100, start: 135, sweep: 270 };

let devices = [];
let selectedId = stored("clima.selected") || "";
let busy = 0;
let pendingTarget = null;
let tempTimer = null;
let serverOk = true;
let pollTimer = null;
let meta = { lgConfigured: false, lgCountry: "BR", lgError: null, version: "" };
let updateInfo = null;

// ------------------------------------------------------------ utilidades

function stored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function store(key, value) {
  try { localStorage.setItem(key, value); } catch { /* sem armazenamento */ }
}

class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function api(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: { "X-Clima-Token": TOKEN, ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("O programa não está respondendo", 0);
  }
  let data = {};
  try { data = await res.json(); } catch { /* resposta vazia */ }
  if (!res.ok) throw new ApiError(data.error || `Erro ${res.status}`, res.status);
  return data;
}

async function ping() {
  try {
    const res = await fetch("/ping", { cache: "no-store" });
    return res.ok ? await res.json() : null;
  } catch { return null; }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  return node;
}

function icon(name) {
  const svg = svgEl("svg");
  svg.append(svgEl("use", { href: `#i-${name}` }));
  return svg;
}

function fmt(n) {
  if (n === null || n === undefined) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(".", ",");
}

// ------------------------------------------------------------ conexão com o programa

async function load() {
  if (busy) return;
  try {
    const data = await api("GET", "/api/devices");
    if (busy) return; // um comando começou enquanto carregávamos
    devices = data.devices;
    meta = data;
    setServerOk(true);
    render();
  } catch (err) {
    if (err.status === 403) {
      // O programa foi reiniciado (nova senha de sessão): recarregamos a página.
      if (await ping()) location.reload();
      return;
    }
    if (err.status === 0) setServerOk(false);
  }
}

function setServerOk(ok) {
  if (serverOk === ok) return;
  serverOk = ok;
  $("net-badge").hidden = ok;
  if (!ok) setConn("Sem contato com o programa — tentando reconectar…", "wait");
}

function schedulePoll(delay) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    await load();
    schedulePoll(serverOk ? POLL_MS : RETRY_MS);
  }, delay);
}

function wake() {
  // Janela voltou a ficar visível, ganhou foco ou o computador acordou.
  schedulePoll(0);
}

// ------------------------------------------------------------ comandos

function current() {
  return devices.find((d) => d.id === selectedId) || null;
}

async function send(body, optimistic) {
  const dev = current();
  if (!dev) return;
  const before = structuredClone(dev);
  Object.assign(dev, optimistic || {});
  render();
  busy++;
  document.body.classList.add("busy");
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
    if (err.status === 0) setServerOk(false);
  } finally {
    busy--;
    if (!busy) document.body.classList.remove("busy");
    render();
  }
}

function clampTarget(dev, value) {
  const min = dev.tempMin ?? 16, max = dev.tempMax ?? 30, step = dev.tempStep || 1;
  return Math.min(max, Math.max(min, Math.round(value / step) * step));
}

function setTarget(value, immediate) {
  const dev = current();
  if (!dev) return;
  value = clampTarget(dev, value);
  pendingTarget = value;
  renderDial(dev);
  clearTimeout(tempTimer);
  const commit = () => {
    const v = pendingTarget;
    pendingTarget = null;
    if (v !== dev.target) send({ target: v }, { target: v });
    else render();
  };
  if (immediate) commit();
  else tempTimer = setTimeout(commit, TEMP_DEBOUNCE_MS);
}

// ------------------------------------------------------------ desenho geral

function render() {
  const has = devices.length > 0;
  $("empty").hidden = has;
  $("control").hidden = !has;
  if (has && !current()) selectedId = devices[0].id;
  renderRooms();
  const dev = current();
  const app = $("app");
  if (dev) {
    app.dataset.mode = dev.mode && ["cool", "heat", "dry", "fan", "auto"].includes(dev.mode) ? dev.mode : "other";
    app.dataset.power = dev.power ? "on" : "off";
    renderDevice(dev);
  } else {
    app.dataset.mode = "cool";
    app.dataset.power = "off";
    if (serverOk) setConn(meta.lgError || "Nenhum aparelho conectado", meta.lgError ? "err" : "");
  }
  $("version-text").textContent = meta.version ? `v${meta.version}` : "";
}

function statusText(d) {
  if (!d.loaded) return "Conectando…";
  if (d.error) return "Sem conexão";
  if (!d.power) return "Desligado";
  const mode = d.modes.find((m) => m.value === d.mode);
  return `${mode ? mode.label : "Ligado"} · ${fmt(d.target)}°`;
}

function renderRooms() {
  const rooms = $("rooms");
  rooms.hidden = devices.length < 2;
  rooms.replaceChildren(...devices.map((d) => {
    const b = el("button", "room");
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(d.id === selectedId));
    const top = el("span", "room-top");
    top.append(el("b", null, d.name), el("i", "dot" + (d.error ? " err" : d.power ? " on" : "")));
    b.append(top, el("span", "temp", d.current != null ? `${fmt(d.current)}°` : "—"), el("small", null, statusText(d)));
    b.addEventListener("click", () => {
      if (d.id === selectedId) return;
      selectedId = d.id;
      store("clima.selected", d.id);
      pendingTarget = null;
      clearTimeout(tempTimer);
      render();
    });
    return b;
  }));
}

function renderDevice(dev) {
  const unavailable = !dev.online;
  const control = $("control");
  control.classList.toggle("off", !dev.power);
  control.classList.toggle("unavailable", unavailable);

  $("name").textContent = dev.name;
  $("status-text").textContent = dev.error ? dev.error.split(".")[0] : `${statusText(dev)}${dev.brand === "lg" ? " · LG" : " · Gree"}`;

  const power = $("power");
  power.classList.toggle("on", !!dev.power);
  power.disabled = unavailable;
  power.title = dev.power ? "Desligar" : "Ligar";

  $("chip-temp").hidden = dev.current == null;
  $("chip-temp").querySelector("b").textContent = `${fmt(dev.current)}°`;
  $("chip-hum").hidden = dev.humidity == null;
  $("chip-hum").querySelector("b").textContent = `${fmt(dev.humidity)}%`;
  renderDial(dev);

  renderModes(dev, unavailable);
  renderFans(dev, unavailable);
  renderVanes(dev, unavailable);
  renderFeatures(dev, unavailable);

  const alert = $("alert");
  alert.hidden = !dev.error;
  alert.textContent = dev.error || "";

  if (!serverOk) return;
  if (!dev.loaded) setConn("Conectando ao aparelho…", "wait");
  else if (dev.error) setConn(`${dev.source}: sem conexão`, "err");
  else setConn(dev.brand === "gree" ? `Rede local${dev.address ? " · " + dev.address : ""}` : "LG ThinQ (internet)", "");
}

// ------------------------------------------------------------ mostrador de temperatura

function polar(angle, r = DIAL.r) {
  const rad = (angle * Math.PI) / 180;
  return [DIAL.cx + r * Math.cos(rad), DIAL.cy + r * Math.sin(rad)];
}

function arcPath(fromAngle, toAngle) {
  const [x0, y0] = polar(fromAngle);
  const [x1, y1] = polar(toAngle);
  const large = toAngle - fromAngle > 180 ? 1 : 0;
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${DIAL.r} ${DIAL.r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

function setupDial() {
  const full = arcPath(DIAL.start, DIAL.start + DIAL.sweep);
  $("arc-track").setAttribute("d", full);
  $("arc-value").setAttribute("d", full);

  const dial = $("dial");
  const toValue = (event) => {
    const dev = current();
    if (!dev) return null;
    const box = dial.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * 240 - DIAL.cx;
    const y = ((event.clientY - box.top) / box.height) * 240 - DIAL.cy;
    let rel = ((Math.atan2(y, x) * 180) / Math.PI - DIAL.start + 720) % 360;
    if (rel > DIAL.sweep) rel = rel > DIAL.sweep + (360 - DIAL.sweep) / 2 ? 0 : DIAL.sweep;
    const min = dev.tempMin ?? 16, max = dev.tempMax ?? 30;
    return min + (rel / DIAL.sweep) * (max - min);
  };
  let dragging = false;
  dial.addEventListener("pointerdown", (e) => {
    if ($("control").classList.contains("unavailable")) return;
    dragging = true;
    dial.setPointerCapture(e.pointerId);
    dial.classList.add("dragging");
    const v = toValue(e);
    if (v != null) setTarget(v);
  });
  dial.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const v = toValue(e);
    if (v != null) setTarget(v);
  });
  const stop = () => {
    if (!dragging) return;
    dragging = false;
    dial.classList.remove("dragging");
    if (pendingTarget != null) setTarget(pendingTarget, true);
  };
  dial.addEventListener("pointerup", stop);
  dial.addEventListener("pointercancel", stop);
  dial.addEventListener("keydown", (e) => {
    const dev = current();
    if (!dev) return;
    const step = dev.tempStep || 1;
    const base = pendingTarget ?? dev.target ?? 24;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") { setTarget(base + step); e.preventDefault(); }
    if (e.key === "ArrowDown" || e.key === "ArrowLeft") { setTarget(base - step); e.preventDefault(); }
  });
}

function renderDial(dev) {
  const min = dev.tempMin ?? 16, max = dev.tempMax ?? 30;
  const value = pendingTarget ?? dev.target;
  const pct = value == null ? 0 : Math.max(0, Math.min(1, (value - min) / (max - min || 1)));
  $("arc-value").setAttribute("stroke-dasharray", `${(pct * 100).toFixed(2)} 100`);
  const [kx, ky] = polar(DIAL.start + pct * DIAL.sweep);
  const knob = $("knob");
  knob.setAttribute("cx", kx.toFixed(2));
  knob.setAttribute("cy", ky.toFixed(2));
  knob.style.visibility = value == null ? "hidden" : "visible";
  $("target").textContent = fmt(value);
  $("dial-caption").textContent = dev.power ? "Ajustada para" : "Desligado";
  $("s-min").textContent = `${fmt(min)}°`;
  $("s-max").textContent = `${fmt(max)}°`;
  const dial = $("dial");
  dial.setAttribute("aria-valuemin", min);
  dial.setAttribute("aria-valuemax", max);
  if (value != null) dial.setAttribute("aria-valuenow", value);

  const ticks = $("dial-ticks");
  const count = Math.round((max - min) / (dev.tempStep >= 1 ? dev.tempStep : 1));
  if (ticks.dataset.count !== String(count)) {
    ticks.dataset.count = count;
    ticks.replaceChildren(...Array.from({ length: count + 1 }, (_, i) => {
      const angle = DIAL.start + (i / count) * DIAL.sweep;
      const [x0, y0] = polar(angle, 82);
      const [x1, y1] = polar(angle, i % 5 === 0 ? 74 : 78);
      return svgEl("line", { x1: x0, y1: y0, x2: x1, y2: y1 });
    }));
  }
}

// ------------------------------------------------------------ modos, ventilação, aletas, funções

function radio(button, checked) {
  button.setAttribute("role", "radio");
  button.setAttribute("aria-checked", String(checked));
  return button;
}

function renderModes(dev, unavailable) {
  $("modes").replaceChildren(...dev.modes.map((m) => {
    const b = radio(el("button", "mode"), m.value === dev.mode);
    b.disabled = unavailable;
    b.append(icon(m.icon), el("span", null, m.label));
    b.addEventListener("click", () => {
      if (m.value !== dev.mode) send({ mode: m.value }, { mode: m.value });
    });
    return b;
  }));
}

function bars(level, total) {
  const box = el("span", "bars");
  for (let i = 1; i <= total; i++) {
    const bar = el("i", i <= level ? "f" : "");
    bar.style.height = `${6 + (16 * i) / total}px`;
    box.append(bar);
  }
  return box;
}

function renderFans(dev, unavailable) {
  $("fan-card").hidden = dev.fans.length === 0;
  const isAuto = (f) => f.value === "0" || f.value === "AUTO";
  const levels = dev.fans.filter((f) => !isAuto(f));
  $("fans").replaceChildren(...dev.fans.map((f) => {
    const b = radio(el("button", "fan-step"), f.value === dev.fan);
    b.disabled = unavailable;
    b.title = f.label;
    if (isAuto(f)) b.append(el("span", "auto-badge", "A"), el("span", null, "Auto"));
    else {
      const level = levels.indexOf(f) + 1;
      b.append(bars(level, levels.length), el("span", null, String(level)));
    }
    b.addEventListener("click", () => send({ fan: f.value }, { fan: f.value }));
    return b;
  }));
  const match = dev.fans.find((f) => f.value === dev.fan);
  $("fan-label").textContent = match ? match.label : "—";
}

function vaneIcon(option) {
  const svg = svgEl("svg", { viewBox: "0 0 30 26" });
  svg.append(svgEl("path", { class: "body", d: "M2 3 H28" }));
  if (option.kind === "pos") {
    // Posição 1 = aleta mais horizontal; posição 5 = mais voltada para baixo.
    const angle = 8 + (option.pos - 1) * 15;
    const rad = (angle * Math.PI) / 180;
    const x = 6 + 13 * Math.cos(rad), y = 7 + 13 * Math.sin(rad);
    svg.append(svgEl("line", { class: "blade", x1: 6, y1: 7, x2: x.toFixed(1), y2: y.toFixed(1) }));
    const ax = 6 + 22 * Math.cos(rad), ay = 7 + 22 * Math.sin(rad);
    svg.append(svgEl("path", { class: "air", d: `M${(x + 2).toFixed(1)} ${(y + 1).toFixed(1)} L${ax.toFixed(1)} ${ay.toFixed(1)}` }));
  } else if (option.kind === "swing") {
    const g = svgEl("g", { class: "swing-blade" });
    g.append(svgEl("line", { class: "blade", x1: 6, y1: 7, x2: 19, y2: 7 }));
    svg.append(g, svgEl("path", { class: "air", d: "M22 6 A 14 14 0 0 1 14 22" }));
  } else {
    svg.append(svgEl("line", { class: "blade", x1: 6, y1: 7, x2: 18, y2: 12 }));
    const t = svgEl("text", { x: 22, y: 23, "font-size": 10, "font-weight": 800, fill: "currentColor", "text-anchor": "middle" });
    t.textContent = "A";
    svg.append(t);
  }
  return svg;
}

function renderVanes(dev, unavailable) {
  const hasHswing = dev.hswing !== null && dev.hswing !== undefined;
  $("vane-card").hidden = dev.vanes.length === 0 && !hasHswing;
  $("vanes").hidden = dev.vanes.length === 0;
  $("vanes").replaceChildren(...dev.vanes.map((v) => {
    const b = radio(el("button", "vane"), v.value === dev.vane);
    b.disabled = unavailable;
    b.title = v.label;
    b.append(vaneIcon(v), el("span", null, v.kind === "pos" ? String(v.pos) : v.label));
    b.addEventListener("click", () => send({ vane: v.value }, { vane: v.value }));
    return b;
  }));
  const match = dev.vanes.find((v) => v.value === dev.vane);
  $("vane-label").textContent = match ? match.label : "";
  $("hswing-row").hidden = !hasHswing;
  $("hswing").checked = !!dev.hswing;
  $("hswing").disabled = unavailable;
  const note = $("vane-note");
  note.hidden = dev.brand !== "lg";
  note.textContent = "A LG só permite ligar ou desligar a oscilação pelo acesso oficial; posições fixas ficam disponíveis apenas no controle remoto.";
}

function renderFeatures(dev, unavailable) {
  $("features-card").hidden = dev.features.length === 0;
  $("features").replaceChildren(...dev.features.map((f) => {
    const b = el("button", "feature");
    b.setAttribute("aria-pressed", String(!!f.on));
    b.disabled = unavailable;
    b.title = f.label;
    const ic = el("span", "ic");
    ic.append(icon(f.icon));
    b.append(ic, el("b", null, f.label), el("small", null, f.on ? "Ligado" : "Desligado"));
    b.addEventListener("click", () => {
      const features = dev.features.map((x) => (x.key === f.key ? { ...x, on: !f.on } : x));
      send({ feature: f.key, on: !f.on }, { features });
    });
    return b;
  }));
}

function setConn(text, kind) {
  $("conn-text").textContent = text;
  $("conn").className = `conn ${kind || ""}`;
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
$("hswing").addEventListener("change", (e) => send({ hswing: e.target.checked }, { hswing: e.target.checked }));

document.addEventListener("keydown", (e) => {
  if ($("settings").open || e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
  if (e.target === $("dial")) return;
  if (e.key === "ArrowUp" || e.key === "+") $("plus").click();
  if (e.key === "ArrowDown" || e.key === "-") $("minus").click();
});

// ------------------------------------------------------------ tema

function applyTheme(choice) {
  if (choice === "light" || choice === "dark") document.documentElement.dataset.theme = choice;
  else delete document.documentElement.dataset.theme;
  document.querySelectorAll("[data-theme-choice]").forEach((b) => {
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(b.dataset.themeChoice === (choice || "auto")));
  });
}
document.querySelectorAll("[data-theme-choice]").forEach((b) => b.addEventListener("click", () => {
  store("clima.theme", b.dataset.themeChoice);
  applyTheme(b.dataset.themeChoice);
}));
applyTheme(stored("clima.theme") || "auto");

// ------------------------------------------------------------ atualizações

async function checkUpdate(force) {
  try {
    updateInfo = await api("GET", `/api/update${force ? "?force=1" : ""}`);
  } catch (err) {
    updateInfo = { error: err.message };
  }
  renderUpdate();
}

function renderUpdate() {
  const info = updateInfo || {};
  $("update-banner").hidden = !info.available;
  $("update-version").textContent = info.latest || "";
  $("update-apply").hidden = !info.available;
  const status = $("update-status");
  if (info.error) {
    status.textContent = `Versão ${meta.version || "?"}. Não foi possível verificar: ${info.error}`;
    status.className = "hint bad";
  } else if (info.available) {
    status.textContent = `Versão instalada ${info.current}. Nova versão ${info.latest} disponível.${info.notes ? " " + info.notes : ""}`;
    status.className = "hint ok";
  } else if (info.current) {
    status.textContent = `Versão ${info.current} — você está com a versão mais recente.`;
    status.className = "hint";
  }
}

async function applyUpdate() {
  if (!confirm(`Atualizar o Clima Casa para a versão ${updateInfo?.latest || "nova"}? O programa reinicia sozinho em alguns segundos.`)) return;
  const before = await ping();
  showOverlay("Baixando e instalando a atualização…");
  try {
    await api("POST", "/api/update", {});
  } catch (err) {
    hideOverlay();
    toast(err.message, true);
    return;
  }
  showOverlay("Reiniciando o programa…");
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 1000));
    const now = await ping();
    if (now && (!before || now.instance !== before.instance)) {
      location.reload();
      return;
    }
  }
  showOverlay("A atualização foi instalada, mas o programa não reabriu. Feche esta janela e abra pelo atalho Clima Casa.");
}

function showOverlay(text) {
  $("overlay-text").textContent = text;
  $("overlay").hidden = false;
}
function hideOverlay() {
  $("overlay").hidden = true;
}

$("update-now").addEventListener("click", applyUpdate);
$("update-apply").addEventListener("click", applyUpdate);
$("update-check").addEventListener("click", (e) => withButton(e.currentTarget, () => checkUpdate(true)));

// ------------------------------------------------------------ configurações

const dialog = $("settings");
document.querySelectorAll("[data-open-settings]").forEach((b) => b.addEventListener("click", openSettings));

function openSettings() {
  $("lg-country").value = meta.lgCountry || "BR";
  $("lg-token").value = "";
  $("lg-remove").hidden = !meta.lgConfigured;
  const status = $("lg-status");
  if (meta.lgError) {
    status.textContent = meta.lgError;
    status.className = "hint bad";
  } else if (meta.lgConfigured) {
    const n = devices.filter((d) => d.brand === "lg").length;
    status.textContent = `Conta LG conectada (${n} ar-condicionado${n === 1 ? "" : "s"}).`;
    status.className = "hint ok";
  } else {
    status.textContent = "Conta LG ainda não conectada.";
    status.className = "hint";
  }
  renderNames();
  renderUpdate();
  dialog.showModal();
}

function renderNames() {
  const box = $("names");
  if (!devices.length) {
    box.textContent = "Nenhum aparelho encontrado ainda.";
    box.className = "hint";
    return;
  }
  box.className = "names-list";
  box.replaceChildren(...devices.map((d) => {
    const row = el("div", "name-row");
    const input = el("input");
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
    row.append(el("small", null, d.brand === "lg" ? "LG" : "Gree"), input);
    if (d.brand === "gree") {
      const del = el("button", "icon-btn");
      del.type = "button";
      del.title = "Remover este aparelho da lista";
      del.append(icon("trash"));
      del.addEventListener("click", async () => {
        if (!confirm(`Remover "${d.name}" da lista? Ele volta se você procurar os aparelhos de novo.`)) return;
        await api("POST", "/api/gree/remove", { mac: d.id.slice(5) }).catch((err) => toast(err.message, true));
        await load();
        renderNames();
      });
      row.append(del);
    } else {
      row.append(el("span", "spacer"));
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
    if (r.found === 0) {
      out.className = "hint bad";
      out.textContent = "Nenhum aparelho Gree respondeu. Confira se o cabo de rede do computador está ligado ao mesmo roteador do Wi-Fi dos aparelhos e se o Firewall do Windows liberou o programa (veja o LEIA-ME).";
      return;
    }
    const parts = [`${r.found} aparelho(s) encontrado(s)`];
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
  meta.lgConfigured = false;
  await load();
  openSettings();
});

$("quit").addEventListener("click", async () => {
  if (!confirm("Encerrar o Clima Casa?")) return;
  await api("POST", "/api/quit", {}).catch(() => {});
  dialog.close();
  document.body.replaceChildren(el("p", "empty", "Programa encerrado. Pode fechar esta janela."));
  window.close();
});

// ------------------------------------------------------------ início

setupDial();
schedulePoll(0);
checkUpdate(false);
setInterval(() => checkUpdate(false), UPDATE_CHECK_MS);

// Volta a falar com o programa assim que a janela "acorda".
document.addEventListener("visibilitychange", () => { if (!document.hidden) wake(); });
window.addEventListener("focus", wake);
window.addEventListener("online", wake);
window.addEventListener("pageshow", wake);
document.addEventListener("resume", wake);

// Ao fechar a janela, avisa o programa para encerrar (cancelado se for só um recarregamento).
window.addEventListener("pagehide", (e) => {
  if (!e.persisted) navigator.sendBeacon(`/api/bye?t=${encodeURIComponent(TOKEN)}`);
});
