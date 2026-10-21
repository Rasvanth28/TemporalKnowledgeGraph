"use strict";

// Storyline: ask a question, get the matching part of the knowledge graph as an interactive
// force-directed graph (events, people/organisations/places, topics). Same-origin API.
// Text from the graph is inserted with textContent or drawn on the canvas, never as HTML.

const KEY_STORAGE = "tkg.apiKey";
const EVENT_TYPES = {
  policy_change: "Policy decision", economic: "Economy", election: "Politics & elections",
  conflict: "Conflict", agreement: "Agreement", legal: "Legal", general: "News event",
};
const ENTITY_TYPES = { PERSON: "Person", ORG: "Organisation", LOCATION: "Place", POLICY: "Policy" };
const ENTITY_COLOR = { PERSON: "--k-person", ORG: "--k-org", LOCATION: "--k-location", POLICY: "--k-policy" };
const REASONS = { shared_entities: "same people or organisations", similar_topic: "similar subject", date_proximity: "close in time" };
const STATIC_EXAMPLES = ["How did interest rates change in 2024?", "What did Opec decide about oil production?"];

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
};
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ---------- API ----------
function getKey() { try { return localStorage.getItem(KEY_STORAGE) || ""; } catch { return ""; } }
function setKey(v) { try { v ? localStorage.setItem(KEY_STORAGE, v) : localStorage.removeItem(KEY_STORAGE); } catch { /* private mode */ } }

class ApiError extends Error { constructor(status, message) { super(message); this.status = status; } }

async function api(path, params = {}, key = getKey()) {
  const url = new URL(path, window.location.href);
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") url.searchParams.set(k, v);
  let response;
  try { response = await fetch(url, { headers: key ? { "X-API-Key": key } : {} }); }
  catch { throw new ApiError(0, "Can't reach the server. Check your connection and try again."); }
  if (response.ok) return response.json();
  if (response.status === 401) throw new ApiError(401, "The API key is missing or wrong.");
  if (response.status === 503) throw new ApiError(503, "The database is unavailable right now (it may be waking up). Try again in a minute.");
  let detail = "";
  try { detail = (await response.json()).detail; } catch { /* not JSON */ }
  throw new ApiError(response.status, typeof detail === "string" && detail ? detail : `Request failed (${response.status}).`);
}

// ---------- formatting ----------
const dayFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const asDate = (iso) => new Date(`${iso}T00:00:00Z`);
const fmtDate = (iso) => (iso ? dayFmt.format(asDate(iso)) : "Date unknown");
const strength = (c) => (c >= 0.55 ? "strong" : c >= 0.4 ? "medium" : "weak");
const explain = (reason) => (reason || "").split("+").map((r) => REASONS[r]).filter(Boolean).join(", ") || "weak similarity";
const safeUrl = (url) => { try { const u = new URL(url); return ["http:", "https:"].includes(u.protocol) ? u.href : null; } catch { return null; } };
const truncate = (text, n) => (text && text.length > n ? `${text.slice(0, n - 1)}…` : text || "");

// ---------- state ----------
let graph = null;          // ForceGraph instance
let data = null;           // { nodes, links, byId, neighbors, interpretation }
let articles = new Map();  // article id -> article
let hovered = null;
let selected = null;
let palette = {};

function readPalette() {
  palette = {
    edge: css("--edge"), accent: css("--accent"), text: css("--text"), muted: css("--muted"),
    canvas: css("--canvas"), event: css("--k-event"), topic: css("--k-topic"),
  };
}

function nodeColor(node) {
  if (node.kind === "topic") return palette.topic;
  if (node.kind === "entity") return css(ENTITY_COLOR[node.type] || "--k-org");
  return css(`--t-${(node.type || "general").split("_")[0]}`) || palette.event;
}
function nodeRadius(node) {
  const base = node.kind === "entity" ? 4.5 : node.kind === "topic" ? 3.8 : 2.8;
  return base + Math.sqrt(node.degree || 0) * 1.25;
}

// ---------- status / dialog ----------
function showStatus(content, { error = false } = {}) {
  const box = $("status");
  box.replaceChildren(...(Array.isArray(content) ? content : [content]));
  box.classList.toggle("error", error);
  box.classList.remove("hidden");
}
const hideStatus = () => $("status").classList.add("hidden");

function openKeyDialog(message = "") {
  $("key-input").value = getKey();
  $("key-error").textContent = message;
  $("key-error").classList.toggle("hidden", !message);
  $("key-dialog").showModal();
}

function handleError(err) {
  if (err.status === 401) { hideStatus(); openKeyDialog(getKey() ? "That key was rejected. Check it and try again." : ""); return; }
  showStatus(err.message || "Something went wrong.", { error: true });
}

// ---------- examples ----------
async function loadExamples() {
  const box = $("examples");
  const prompts = [...STATIC_EXAMPLES];
  try {
    const top = await api("entities/top", { limit: 12 });
    // Prefer specific names: skip one that is just the first word of another ("Bank" vs "Bank of England").
    const specific = top.filter((e) => e.name.length > 3 && !top.some((o) => o !== e && o.name.startsWith(`${e.name} `)));
    for (const entity of specific.slice(0, 3)) prompts.unshift(`What happened with ${entity.name}?`);
  } catch (err) {
    if (err.status === 401) handleError(err);
  }
  box.replaceChildren(el("span", { className: "label" }, "Try:"), ...prompts.slice(0, 5).map((prompt) => {
    const chip = el("button", { type: "button", className: "chip" }, prompt);
    chip.addEventListener("click", () => ask(prompt));
    return chip;
  }));
}

// ---------- ask ----------
async function ask(prompt) {
  prompt = (prompt || "").trim();
  $("prompt").value = prompt;
  if (!prompt) return;
  if (!getKey()) { openKeyDialog(); return; }
  history.replaceState(null, "", `?${new URLSearchParams({ q: prompt })}`);
  $("workspace").classList.add("hidden");
  $("understood").classList.add("hidden");
  showStatus(el("div", { className: "skeleton" }));
  try {
    const result = await api("graph", { q: prompt, limit: 40 });
    renderUnderstood(result.interpretation);
    if (!result.nodes.length) {
      showStatus("Nothing in the graph matches that yet. Try a name from the examples, a shorter question, or a different time period.");
      return;
    }
    hideStatus();
    await loadArticles(result.nodes);
    renderGraph(result);
  } catch (err) {
    handleError(err);
  }
}

async function loadArticles(nodes) {
  articles = new Map();
  const ids = [...new Set(nodes.filter((n) => n.kind === "event" && n.article_id).map((n) => n.article_id))];
  for (let i = 0; i < ids.length; i += 200) {
    try {
      for (const a of await api("articles", { ids: ids.slice(i, i + 200).join(",") })) articles.set(a.id, a);
    } catch { /* headlines are optional */ }
  }
}

function renderUnderstood(meaning) {
  const pills = [];
  for (const e of meaning.entities) pills.push(el("span", { className: "pill", title: `Matched ${ENTITY_TYPES[e.type] || "name"}${e.score < 100 ? " (approximate)" : ""}` }, e.name));
  if (meaning.start || meaning.end) {
    const range = meaning.start && meaning.end ? `${fmtDate(meaning.start)} – ${fmtDate(meaning.end)}`
      : meaning.start ? `since ${fmtDate(meaning.start)}` : `until ${fmtDate(meaning.end)}`;
    pills.push(el("span", { className: "pill" }, `📅 ${range}`));
  }
  if (meaning.keywords.length) pills.push(el("span", { className: "pill" }, `🔎 ${meaning.keywords.join(", ")}`));
  if (meaning.semantic) pills.push(el("span", { className: "pill weak", title: "Also matching events by meaning, not just words" }, "+ similar meaning"));
  $("understood").replaceChildren(el("span", { className: "label" }, "Understood:"), ...(pills.length ? pills : [el("span", { className: "muted" }, "general search")]));
  $("understood").classList.remove("hidden");
}

// ---------- graph ----------
function renderGraph(result) {
  const nodes = result.nodes.map((n) => ({ ...n }));
  const links = result.edges.map((e) => ({ ...e }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const neighbors = new Map(nodes.map((n) => [n.id, new Set()]));
  for (const l of links) { neighbors.get(l.source)?.add(l.target); neighbors.get(l.target)?.add(l.source); }
  data = { nodes, links, byId, neighbors, interpretation: result.interpretation };
  hovered = null; selected = null;

  $("workspace").classList.remove("hidden");
  readPalette();
  const container = $("graph");
  if (!graph) {
    graph = ForceGraph()(container)
      .backgroundColor("rgba(0,0,0,0)")
      .nodeId("id")
      .nodeRelSize(1)
      .nodeVal((n) => nodeRadius(n) ** 2)
      .nodeLabel(() => "")
      .nodeCanvasObject(drawNode)
      .nodePointerAreaPaint((n, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(n.x, n.y, nodeRadius(n) + 2, 0, 2 * Math.PI); ctx.fill(); })
      .linkColor((l) => linkActive(l) === false ? "rgba(128,128,128,0.06)" : l.kind === "linked_to" ? palette.accent : palette.edge)
      .linkWidth((l) => (l.kind === "linked_to" ? 0.6 + 2 * (l.confidence || 0) : 0.6) * (linkActive(l) ? 1.8 : 1))
      .linkDirectionalArrowLength((l) => (l.kind === "linked_to" ? 4 : 0))
      .linkDirectionalArrowRelPos(0.9)
      .onNodeHover((n) => { hovered = n || null; container.style.cursor = n ? "pointer" : ""; })
      .onNodeClick((n) => select(n))
      .onBackgroundClick(() => select(null))
      .autoPauseRedraw(false) // keep redrawing so hover highlights update after the layout settles
      .cooldownTicks(150)
      .onEngineStop(() => { if (data && !data.fitted) { data.fitted = true; graph.zoomToFit(500, 50); } });
    graph.d3Force("charge").strength(-70);
    // Gentle pull toward the centre (like Obsidian's "center force") so unconnected pieces stay nearby.
    let gravityNodes = [];
    const gravity = (alpha) => { for (const n of gravityNodes) { n.vx -= n.x * 0.06 * alpha; n.vy -= n.y * 0.06 * alpha; } };
    gravity.initialize = (nodes) => { gravityNodes = nodes; };
    graph.d3Force("gravity", gravity);
    graph.d3Force("link").distance((l) => (l.kind === "linked_to" ? 55 : l.kind === "about" ? 40 : 32));
    new ResizeObserver(() => graph.width(container.clientWidth).height(container.clientHeight)).observe(container);
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { readPalette(); graph.refresh?.(); });
  }
  graph.width(container.clientWidth).height(container.clientHeight).graphData({ nodes, links });
  showOverview();
}

const linkEnds = (l) => [typeof l.source === "object" ? l.source.id : l.source, typeof l.target === "object" ? l.target.id : l.target];

function focusSet() {
  const focus = hovered || selected;
  if (!focus) return null;
  return new Set([focus.id, ...(data.neighbors.get(focus.id) || [])]);
}
function linkActive(l) {
  const focus = hovered || selected;
  if (!focus) return null;
  const [s, t] = linkEnds(l);
  return s === focus.id || t === focus.id;
}

function drawNode(node, ctx, scale) {
  const set = focusSet();
  const dim = set && !set.has(node.id);
  const r = nodeRadius(node);
  const color = nodeColor(node);
  ctx.globalAlpha = dim ? 0.15 : 1;
  if (node === selected || node.matched) {
    ctx.beginPath(); ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI);
    ctx.fillStyle = node === selected ? palette.accent : color; ctx.globalAlpha = dim ? 0.08 : 0.25; ctx.fill();
    ctx.globalAlpha = dim ? 0.15 : 1;
  }
  ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
  if (node.kind === "topic") { ctx.lineWidth = 1.8; ctx.strokeStyle = color; ctx.fillStyle = palette.canvas; ctx.fill(); ctx.stroke(); }
  else { ctx.fillStyle = color; ctx.fill(); }

  // Obsidian-style labels: names appear as you zoom in; anything in focus is always labelled.
  const inFocus = set && set.has(node.id);
  const show = inFocus || (node.kind !== "event" && scale > 1.1) || scale > 2.6 || node.matched;
  if (show) {
    const size = 11 / scale;
    ctx.font = `${node.kind === "event" ? 400 : 600} ${size}px system-ui, sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    ctx.fillStyle = node.kind === "event" ? palette.muted : palette.text;
    ctx.fillText(truncate(node.label, node.kind === "event" ? 36 : 28), node.x, node.y + r + 2 / scale);
  }
  ctx.globalAlpha = 1;
}

function select(node) {
  selected = node || null;
  if (!node) { showOverview(); return; }
  graph.centerAt(node.x, node.y, 600);
  if (node.kind === "event") showEvent(node); else showGroup(node);
}

// ---------- panel ----------
function eventButton(node, extra) {
  const btn = el("button", { type: "button", className: "item-btn" },
    el("span", { className: "dot", style: `--c: ${nodeColor(node)}` }),
    el("span", {}, truncate(node.label, 90)),
    el("span", { className: "when" }, fmtDate(node.date)),
    extra ? el("span", { className: "why" }, extra) : null);
  btn.addEventListener("click", () => select(node));
  return el("li", {}, btn);
}

const eventsSorted = (nodes) => [...nodes].sort((a, b) => (a.date || "").localeCompare(b.date || ""));

function showOverview() {
  const events = eventsSorted(data.nodes.filter((n) => n.kind === "event"));
  const entities = data.nodes.filter((n) => n.kind === "entity").length;
  const topics = data.nodes.filter((n) => n.kind === "topic").length;
  const span = events.length && events[0].date ? `${fmtDate(events[0].date)} → ${fmtDate(events[events.length - 1].date)}` : "";
  $("panel").replaceChildren(
    el("h2", {}, `${events.length} events`),
    el("p", { className: "muted" }, `${entities} people, organisations & places · ${topics} topics${span ? ` · ${span}` : ""}`),
    el("p", { className: "muted" }, "Drag to move, scroll to zoom, hover to highlight connections, click anything for details."),
    el("h3", {}, "Events, oldest first"),
    el("ul", { className: "event-list" }, events.map((n) => eventButton(n))),
  );
}

function backButton() {
  const back = el("button", { type: "button", className: "ghost small back" }, "← All events");
  back.addEventListener("click", () => select(null));
  return back;
}

function chipFor(node) {
  const chip = el("button", { type: "button", className: "chip" }, node.kind === "topic" ? `# ${node.label}` : node.label);
  chip.addEventListener("click", () => select(node));
  return chip;
}

function showEvent(node) {
  const article = articles.get(node.article_id);
  const href = article && safeUrl(article.url);
  const parts = [
    backButton(),
    el("div", { className: "kind" }, `${EVENT_TYPES[node.type] || EVENT_TYPES.general} · ${fmtDate(node.date)}${node.date_source === "inferred" ? " (article date)" : ""}`),
    el("p", { className: "desc" }, node.label),
  ];
  if (article?.date && node.date && Math.abs(asDate(article.date) - asDate(node.date)) > 31 * 864e5) {
    parts.push(el("p", { className: "note" }, `Date taken from the text; the article is from ${fmtDate(article.date)}, so this may refer to an earlier event.`));
  }
  if (href) parts.push(el("a", { href, target: "_blank", rel: "noopener noreferrer" }, `📰 ${article.title || "Read the article"}${article.source ? ` — ${article.source}` : ""} ↗`));

  const neighbours = [...(data.neighbors.get(node.id) || [])].map((id) => data.byId.get(id));
  const tags = neighbours.filter((n) => n.kind !== "event");
  if (tags.length) parts.push(el("h3", {}, "Involves"), el("div", { className: "tags" }, tags.map(chipFor)));

  const out = [], inc = [];
  for (const l of data.links) {
    if (l.kind !== "linked_to") continue;
    const [s, t] = linkEnds(l);
    if (s === node.id) out.push([data.byId.get(t), l]);
    if (t === node.id) inc.push([data.byId.get(s), l]);
  }
  const list = (pairs) => el("ul", { className: "event-list" },
    pairs.sort((a, b) => b[1].confidence - a[1].confidence)
      .map(([n, l]) => eventButton(n, `${strength(l.confidence)} link: ${explain(l.reason)}`)));
  if (inc.length) parts.push(el("h3", {}, "Follows from"), list(inc));
  if (out.length) parts.push(el("h3", {}, "Led to"), list(out));
  $("panel").replaceChildren(...parts);
}

function showGroup(node) {
  const events = eventsSorted([...(data.neighbors.get(node.id) || [])].map((id) => data.byId.get(id)).filter((n) => n.kind === "event"));
  const kind = node.kind === "topic" ? "Topic" : ENTITY_TYPES[node.type] || "Entity";
  const explore = el("button", { type: "button", className: "small" }, `Explore “${truncate(node.label, 30)}”`);
  explore.addEventListener("click", () => ask(node.kind === "topic" ? `${node.label}` : `What happened with ${node.label}?`));
  $("panel").replaceChildren(
    backButton(),
    el("div", { className: "kind" }, kind),
    el("h2", {}, node.label),
    el("p", { className: "muted" }, `In ${events.length} of the events shown.`),
    explore,
    el("h3", {}, "Events, oldest first"),
    el("ul", { className: "event-list" }, events.map((n) => eventButton(n))),
  );
}

// ---------- wiring ----------
$("ask").addEventListener("submit", (e) => { e.preventDefault(); ask($("prompt").value); });
$("fit").addEventListener("click", () => graph && graph.zoomToFit(500, 50));
$("key-button").addEventListener("click", () => openKeyDialog());
$("key-clear").addEventListener("click", () => { setKey(""); $("key-input").value = ""; });
$("key-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const key = $("key-input").value.trim();
  if (!key) return;
  try { await api("entities/top", { limit: 1 }, key); }
  catch (err) {
    $("key-error").textContent = err.status === 401 ? "That key was rejected." : err.message;
    $("key-error").classList.remove("hidden");
    return;
  }
  setKey(key);
  $("key-dialog").close();
  loadExamples();
  const q = new URLSearchParams(window.location.search).get("q");
  if (q) ask(q);
});

if (!getKey()) {
  openKeyDialog();
} else {
  loadExamples();
  const q = new URLSearchParams(window.location.search).get("q");
  if (q) ask(q);
}
