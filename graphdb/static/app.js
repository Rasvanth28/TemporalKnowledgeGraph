"use strict";

// Storyline: ask a question, get the matching part of the knowledge graph as an interactive
// force-directed graph, with every connection explained in plain words and cited to its source.
// Text from the graph is inserted with textContent or drawn on the canvas. The only HTML string
// (force-graph's hover tooltip) is built from escaped text.

const KEY_STORAGE = "tkg.apiKey";
const EVENT_TYPES = {
  policy_change: "Policy decision", economic: "Economy", election: "Politics & elections",
  conflict: "Conflict", agreement: "Agreement", legal: "Legal", general: "News event",
};
const ENTITY_TYPES = { PERSON: "Person", ORG: "Organisation", LOCATION: "Place", POLICY: "Policy" };
const ENTITY_COLOR = { PERSON: "--k-person", ORG: "--k-org", LOCATION: "--k-location", POLICY: "--k-policy" };
const STATIC_EXAMPLES = ["How did interest rates change in 2024?", "What did Opec decide about oil production?"];
const CAVEAT = "A link means the two events were scored as part of the same story (shared names, similar subject, close in time). It does not prove that one caused the other.";

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
const escapeHtml = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

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
const fmtDate = (iso) => (iso ? dayFmt.format(asDate(iso)) : "date unknown");
const daysBetween = (a, b) => Math.round(Math.abs(asDate(b) - asDate(a)) / 864e5);
const strengthWord = (c) => (c >= 0.55 ? "strong" : c >= 0.4 ? "medium" : "weak");
const safeUrl = (url) => { try { const u = new URL(url); return ["http:", "https:"].includes(u.protocol) ? u.href : null; } catch { return null; } };
const truncate = (text, n) => (text && text.length > n ? `${text.slice(0, n - 1)}…` : text || "");
const capital = (text) => (text ? text[0].toUpperCase() + text.slice(1) : "");
const listWords = (items) => (items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`);
const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;
// Older topic names can carry a stray possessive ("’s monetary policy committee"); tidy them for display.
const cleanTopic = (name) => (name || "").replace(/['’‘]s\b/g, " ").replace(/\s+/g, " ").trim();

// ---------- state ----------
let graph = null;
let data = null;          // { nodes, links, byId, neighbors, sources, cite, interpretation, query }
let hovered = null;
let selected = null;      // node
let selectedLink = null;  // link
let palette = {};

function readPalette() {
  palette = { edge: css("--edge"), accent: css("--accent"), text: css("--text"), muted: css("--muted"), canvas: css("--canvas"), event: css("--k-event"), topic: css("--k-topic") };
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

// ---------- graph relationships ----------
const endId = (end) => (typeof end === "object" ? end.id : end);
const linkEnds = (l) => [endId(l.source), endId(l.target)];
const nodeOf = (end) => data.byId.get(endId(end));
const neighboursOf = (node, kind) => [...(data.neighbors.get(node.id) || [])].map((id) => data.byId.get(id)).filter((n) => !kind || n.kind === kind);
const sharedNeighbours = (a, b, kind) => neighboursOf(a, kind).filter((n) => data.neighbors.get(b.id)?.has(n.id));
const eventsSorted = (nodes) => [...nodes].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
const storyLinks = () => data.links.filter((l) => l.kind === "linked_to");

function linkFacts(link) {
  const a = nodeOf(link.source), b = nodeOf(link.target);
  return {
    a, b,
    names: sharedNeighbours(a, b, "entity").map((n) => n.label),
    topics: sharedNeighbours(a, b, "topic").map((n) => n.label),
    days: a.date && b.date ? daysBetween(a.date, b.date) : null,
    strength: strengthWord(link.confidence || 0),
  };
}

// "strong link: both involve Bank of England; same subject (interest rates); 12 days apart"
function linkReasonText(link) {
  const f = linkFacts(link);
  const reasons = [];
  if (f.names.length) reasons.push(`both involve ${listWords(f.names.slice(0, 3))}`);
  else if ((link.reason || "").includes("shared_entities")) reasons.push("they share names");
  if (f.topics.length) reasons.push(`same subject (${listWords(f.topics.slice(0, 2))})`);
  else if ((link.reason || "").includes("similar_topic")) reasons.push("similar subject");
  if (f.days !== null) reasons.push(f.days === 0 ? "same day" : `${plural(f.days, "day")} apart`);
  return `${f.strength} link: ${reasons.join("; ") || "weak similarity"}`;
}

// Strongest thread: start at the most confident link, extend forwards/backwards by the best link.
function strongestThread() {
  const links = storyLinks();
  if (!links.length) return [];
  const out = new Map(), inc = new Map();
  for (const l of links) {
    const [s, t] = linkEnds(l);
    (out.get(s) || out.set(s, []).get(s)).push(l);
    (inc.get(t) || inc.set(t, []).get(t)).push(l);
  }
  const best = (list, seen, end) => (list || []).filter((l) => !seen.has(endId(l[end]))).sort((x, y) => y.confidence - x.confidence)[0];
  const seed = [...links].sort((x, y) => y.confidence - x.confidence)[0];
  const steps = [seed];
  const seen = new Set(linkEnds(seed));
  for (let next = best(out.get(endId(seed.target)), seen, "target"); next && steps.length < 5; next = best(out.get(endId(next.target)), seen, "target")) {
    steps.push(next); seen.add(endId(next.target));
  }
  for (let prev = best(inc.get(endId(seed.source)), seen, "source"); prev && steps.length < 5; prev = best(inc.get(endId(prev.source)), seen, "source")) {
    steps.unshift(prev); seen.add(endId(prev.source));
  }
  return steps;
}

// ---------- citations ----------
function cite(articleId) {
  const n = data.cite.get(articleId);
  const source = data.sources[n - 1];
  if (!source) return null;
  const href = safeUrl(source.url);
  const title = `${source.title || "Source"} — ${source.publisher || ""}, ${fmtDate(source.date)}`;
  return href ? el("a", { className: "cite", href, target: "_blank", rel: "noopener noreferrer", title }, `[${n}]`)
    : el("span", { className: "cite", title }, `[${n}]`);
}

function sourceLine(articleId) {
  const n = data.cite.get(articleId);
  const source = data.sources[n - 1];
  if (!source) return null;
  const href = safeUrl(source.url);
  const text = source.title || "Read the article";
  return el("p", { className: "source-line" }, `[${n}] `,
    href ? el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text, " ↗") : text,
    el("span", { className: "muted" }, ` — ${source.publisher || "source"}, ${fmtDate(source.date)}`));
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
  const prompts = [...STATIC_EXAMPLES];
  try {
    const top = await api("entities/top", { limit: 12 });
    const specific = top.filter((e) => e.name.length > 3 && !top.some((o) => o !== e && o.name.startsWith(`${e.name} `)));
    for (const entity of specific.slice(0, 3)) prompts.unshift(`What happened with ${entity.name}?`);
  } catch (err) {
    if (err.status === 401) handleError(err);
  }
  $("examples").replaceChildren(el("span", { className: "label" }, "Try:"), ...prompts.slice(0, 5).map((prompt) => {
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
    renderGraph(result);
  } catch (err) {
    handleError(err);
  }
}

function dateRangeText(m) {
  return m.start && m.end ? `${fmtDate(m.start)} – ${fmtDate(m.end)}` : m.start ? `since ${fmtDate(m.start)}` : `until ${fmtDate(m.end)}`;
}

function renderUnderstood(meaning) {
  const pills = [];
  for (const e of meaning.entities) pills.push(el("span", { className: "pill", title: `Matched ${ENTITY_TYPES[e.type] || "name"}${e.score < 100 ? " (approximate)" : ""}` }, e.name));
  if (meaning.start || meaning.end) pills.push(el("span", { className: "pill" }, `📅 ${dateRangeText(meaning)}`));
  if (meaning.keywords.length) pills.push(el("span", { className: "pill" }, `🔎 ${meaning.keywords.join(", ")}`));
  if (meaning.semantic) pills.push(el("span", { className: "pill weak", title: "Also matching events by meaning, not just words" }, "+ similar meaning"));
  $("understood").replaceChildren(el("span", { className: "label" }, "Understood:"), ...(pills.length ? pills : [el("span", { className: "muted" }, "general search")]));
  $("understood").classList.remove("hidden");
}

// ---------- graph ----------
function renderGraph(result) {
  const nodes = result.nodes.map((n) => ({ ...n, label: n.kind === "topic" ? cleanTopic(n.label) : n.label }));
  const links = result.edges.map((e) => ({ ...e }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const neighbors = new Map(nodes.map((n) => [n.id, new Set()]));
  for (const l of links) { neighbors.get(l.source)?.add(l.target); neighbors.get(l.target)?.add(l.source); }
  const sources = result.sources || [];
  data = { nodes, links, byId, neighbors, sources, cite: new Map(sources.map((s, i) => [s.id, i + 1])),
           interpretation: result.interpretation, query: result.query };
  hovered = null; selected = null; selectedLink = null;

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
      .linkColor((l) => (linkActive(l) === false ? "rgba(128,128,128,0.06)" : l.kind === "linked_to" ? palette.accent : palette.edge))
      .linkWidth((l) => (l === selectedLink ? 4 : (l.kind === "linked_to" ? 0.6 + 2 * (l.confidence || 0) : 0.6) * (linkActive(l) ? 1.8 : 1)))
      .linkDirectionalArrowLength((l) => (l.kind === "linked_to" ? 4 : 0))
      .linkDirectionalArrowRelPos(0.9)
      .linkHoverPrecision(6)
      .linkLabel(linkTooltip)
      .onLinkClick((l) => showRelationship(l))
      .onNodeHover((n) => { hovered = n || null; container.style.cursor = n ? "pointer" : ""; })
      .onNodeClick((n) => select(n))
      .onBackgroundClick(() => select(null))
      .autoPauseRedraw(false) // keep redrawing so hover highlights update after the layout settles
      .cooldownTicks(150)
      .onEngineStop(() => { if (data && !data.fitted) { data.fitted = true; graph.zoomToFit(500, 50); } });
    graph.d3Force("charge").strength(-70);
    graph.d3Force("link").distance((l) => (l.kind === "linked_to" ? 55 : l.kind === "about" ? 40 : 32));
    // Gentle pull toward the centre (like Obsidian's "center force") so unconnected pieces stay nearby.
    let gravityNodes = [];
    const gravity = (alpha) => { for (const n of gravityNodes) { n.vx -= n.x * 0.06 * alpha; n.vy -= n.y * 0.06 * alpha; } };
    gravity.initialize = (ns) => { gravityNodes = ns; };
    graph.d3Force("gravity", gravity);
    new ResizeObserver(() => graph.width(container.clientWidth).height(container.clientHeight)).observe(container);
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { readPalette(); graph.refresh?.(); });
  }
  graph.width(container.clientWidth).height(container.clientHeight).graphData({ nodes, links });
  showOverview();
}

function linkTooltip(link) {
  // force-graph renders this string as HTML: escape everything.
  const a = nodeOf(link.source), b = nodeOf(link.target);
  if (link.kind === "linked_to") return `<b>Led to</b> · ${escapeHtml(linkReasonText(link))}<br>Click for the full explanation`;
  const what = link.kind === "involves" ? "names" : "is about";
  return `${escapeHtml(truncate(capital(a.label), 40))} <b>${what}</b> ${escapeHtml(b.label)}`;
}

function focusSet() {
  if (selectedLink) return new Set(linkEnds(selectedLink));
  const focus = hovered || selected;
  if (!focus) return null;
  return new Set([focus.id, ...(data.neighbors.get(focus.id) || [])]);
}
function linkActive(l) {
  if (selectedLink) return l === selectedLink;
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
  const inFocus = set && set.has(node.id);
  if (inFocus || (node.kind !== "event" && scale > 1.1) || scale > 2.6 || node.matched) {
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
  selectedLink = null;
  if (!node) { showOverview(); return; }
  graph.centerAt(node.x, node.y, 600);
  if (node.kind === "event") showEvent(node); else showGroup(node);
}

// ---------- panel building blocks ----------
function nodeButton(node, sub) {
  const btn = el("button", { type: "button", className: "item-btn" },
    el("span", { className: "dot", style: `--c: ${nodeColor(node)}` }),
    el("span", {}, capital(truncate(node.label, 90))),
    el("span", { className: "when" }, node.kind === "event" ? fmtDate(node.date) : (node.kind === "topic" ? "Topic" : ENTITY_TYPES[node.type] || "")),
    sub ? el("span", { className: "why" }, sub) : null);
  btn.addEventListener("click", () => select(node));
  return btn;
}
function linkButton(link, label) {
  const btn = el("button", { type: "button", className: "item-btn" },
    el("span", { className: "dot arrow-dot" }),
    el("span", {}, label),
    el("span", { className: "why" }, capital(linkReasonText(link)), " · why?"));
  btn.addEventListener("click", () => showRelationship(link));
  return btn;
}
function backButton() {
  const back = el("button", { type: "button", className: "ghost small back" }, "← Overview");
  back.addEventListener("click", () => select(null));
  return back;
}
const section = (title, ...children) => [el("h3", {}, title), ...children];
const eventItem = (node, sub) => el("li", { className: "with-cite" }, nodeButton(node, sub), cite(node.article_id));

// ---------- overview: the story + sources ----------
function showOverview() {
  const events = eventsSorted(data.nodes.filter((n) => n.kind === "event"));
  const top = data.nodes.filter((n) => n.kind === "entity")
    .map((n) => [n, neighboursOf(n, "event").length]).sort((x, y) => y[1] - x[1]).slice(0, 4);
  const thread = strongestThread();
  const first = events[0], last = events[events.length - 1];

  const story = el("div", { className: "story" },
    el("p", {}, `${plural(events.length, "event")}${first?.date ? ` from ${fmtDate(first.date)} to ${fmtDate(last.date)}` : ""}, drawn from ${plural(data.sources.length, "news article")} (listed under Sources).`));
  if (top.length) {
    const p = el("p", {}, "Most connected: ");
    top.forEach(([node, count], i) => {
      const chip = el("button", { type: "button", className: "chip inline" }, node.label);
      chip.addEventListener("click", () => select(node));
      p.append(chip, ` in ${plural(count, "event")}${i < top.length - 1 ? ", " : "."}`);
    });
    story.append(p);
  }
  if (thread.length) {
    const steps = [nodeOf(thread[0].source), ...thread.map((l) => nodeOf(l.target))];
    const list = el("ol", { className: "thread" });
    steps.forEach((node, i) => {
      list.append(eventItem(node));
      if (i < thread.length) {
        const why = el("button", { type: "button", className: "thread-why" }, `↓ ${linkReasonText(thread[i])}`);
        why.addEventListener("click", () => showRelationship(thread[i]));
        list.append(el("li", { className: "thread-link" }, why));
      }
    });
    story.append(el("p", {}, "Strongest thread (click an arrow to see why the events are linked):"), list);
  } else {
    story.append(el("p", { className: "muted" }, "None of these events are linked to each other directly; they are connected only through shared people, organisations or topics."));
  }

  $("panel").replaceChildren(
    el("h2", {}, "The story"),
    story,
    ...section("How to read the graph",
      el("ul", { className: "how" },
        el("li", {}, "A line from an event to a person, organisation or place means they are named in the sentence the event was taken from."),
        el("li", {}, "A ring is a topic; a line to it means the event is about that subject."),
        el("li", {}, "A blue arrow points from an earlier event to a later one in the same story. ", CAVEAT),
        el("li", {}, "Hover a line to see why it exists; click it for the full explanation and its sources."))),
    ...section(`Events, oldest first (${events.length})`, el("ul", { className: "event-list" }, events.map((n) => eventItem(n)))),
    ...section(`Sources (${data.sources.length})`, el("ol", { className: "sources" }, data.sources.map((s) => {
      const href = safeUrl(s.url);
      const count = events.filter((e) => e.article_id === s.id).length;
      return el("li", {}, href ? el("a", { href, target: "_blank", rel: "noopener noreferrer" }, s.title || "Untitled", " ↗") : (s.title || "Untitled"),
        el("span", { className: "muted" }, ` — ${s.publisher || "source"}, ${fmtDate(s.date)} · ${plural(count, "event")}`));
    }))),
  );
}

// ---------- event ----------
function whyItems(node) {
  const why = node.why || {};
  const items = [];
  if (why.names?.length) items.push(`It involves ${listWords(why.names)}, which you asked about.`);
  if (why.keywords?.length) items.push(`Its text mentions ${listWords(why.keywords.map((k) => `“${k}”`))}.`);
  if (why.meaning) items.push("Its meaning is close to your question, even where the words differ.");
  if (why.in_date_range) items.push(`It falls within ${dateRangeText(data.interpretation)}.`);
  if (!items.length) items.push("It is connected to other events in these results.");
  return items;
}

function showEvent(node) {
  const n = data.cite.get(node.article_id);
  const source = data.sources[n - 1];
  const parts = [
    backButton(),
    el("div", { className: "kind" }, `${EVENT_TYPES[node.type] || EVENT_TYPES.general} · ${fmtDate(node.date)}${node.date_source === "inferred" ? " (article date)" : ""}`),
    el("p", { className: "desc" }, capital(node.label), " ", cite(node.article_id)),
    ...section("Why it's here", el("ul", { className: "how" }, whyItems(node).map((t) => el("li", {}, t)))),
  ];
  if (source?.date && node.date && daysBetween(source.date, node.date) > 31) {
    parts.push(el("p", { className: "note" }, `The date comes from the text; the article is from ${fmtDate(source.date)}, so this may refer to an earlier event.`));
  }
  if (node.evidence || source) {
    parts.push(...section("Evidence", node.evidence ? el("blockquote", {}, `“${node.evidence}”`) : null, sourceLine(node.article_id)));
  }

  const connected = [
    ...neighboursOf(node, "entity").map((x) => eventItemFor(x, `Named in this event's sentence${n ? ` [${n}]` : ""}`)),
    ...neighboursOf(node, "topic").map((x) => eventItemFor(x, "This event is about this subject")),
  ];
  const inc = [], out = [];
  for (const l of storyLinks()) {
    const [s, t] = linkEnds(l);
    if (t === node.id) inc.push(l);
    if (s === node.id) out.push(l);
  }
  const byConfidence = (x, y) => y.confidence - x.confidence;
  const linkItem = (l, other) => el("li", { className: "with-cite" }, linkButton(l, `${capital(other.label)} (${fmtDate(other.date)})`), cite(other.article_id));
  if (connected.length) parts.push(...section("Connected to", el("ul", { className: "event-list" }, connected)));
  if (inc.length) parts.push(...section("Follows from (earlier events)", el("ul", { className: "event-list" }, inc.sort(byConfidence).map((l) => linkItem(l, nodeOf(l.source))))));
  if (out.length) parts.push(...section("Led to (later events)", el("ul", { className: "event-list" }, out.sort(byConfidence).map((l) => linkItem(l, nodeOf(l.target))))));
  $("panel").replaceChildren(...parts);
}
const eventItemFor = (node, sub) => el("li", {}, nodeButton(node, sub));

// ---------- entity / topic ----------
function showGroup(node) {
  const events = eventsSorted(neighboursOf(node, "event"));
  const articles = new Set(events.map((e) => e.article_id).filter(Boolean));
  const kind = node.kind === "topic" ? "Topic" : ENTITY_TYPES[node.type] || "Entity";
  const explore = el("button", { type: "button", className: "small" }, `Explore “${truncate(node.label, 30)}”`);
  explore.addEventListener("click", () => ask(node.kind === "topic" ? node.label : `What happened with ${node.label}?`));
  const sentence = node.kind === "topic"
    ? `${plural(events.length, "event")} here ${events.length === 1 ? "is" : "are"} about “${node.label}”, from ${plural(articles.size, "source")}.`
    : `${node.label} is named in ${plural(events.length, "event")} here, across ${plural(articles.size, "source")}. Events that share ${node.label} are drawn together in the graph.`;
  $("panel").replaceChildren(
    backButton(),
    el("div", { className: "kind" }, kind),
    el("h2", {}, node.label),
    el("p", {}, sentence, node.matched ? " You asked about it directly." : ""),
    explore,
    ...section("Events, oldest first", el("ul", { className: "event-list" }, events.map((x) => eventItem(x)))),
  );
}

// ---------- relationship ----------
function showRelationship(link) {
  selected = null;
  selectedLink = link;
  const a = nodeOf(link.source), b = nodeOf(link.target);
  if (a.x !== undefined) graph.centerAt((a.x + b.x) / 2, (a.y + b.y) / 2, 600);
  const card = (node) => el("div", { className: "rel-card" }, nodeButton(node), node.evidence ? el("blockquote", {}, `“${node.evidence}”`) : null, sourceLine(node.article_id));
  const parts = [backButton(), el("div", { className: "kind" }, "Relationship")];

  if (link.kind === "linked_to") {
    const f = linkFacts(link);
    parts.push(el("h2", {}, "How these events are connected"),
      card(a), el("p", { className: "rel-arrow" }, `↓ linked to a later event${f.days !== null ? ` (${plural(f.days, "day")} later)` : ""}`), card(b));
    const evidence = [];
    if (f.names.length) evidence.push(`Shared names: both events involve ${listWords(f.names)}.`);
    if (f.topics.length) evidence.push(`Same subject: both are about ${listWords(f.topics.map((t) => `“${t}”`))}.`);
    else if ((link.reason || "").includes("similar_topic")) evidence.push("Similar subject: their sentences use closely related wording.");
    if (f.days !== null) evidence.push(f.days <= 30 ? `Close in time: ${plural(f.days, "day")} apart.` : `Time: ${plural(f.days, "day")} apart (too far apart to add to the score).`);
    if (a.article_id && a.article_id === b.article_id) evidence.push("Both come from the same article.");
    if (!evidence.length) evidence.push("The two events scored as similar, but no single shared name or topic explains it.");
    parts.push(...section("Why they are linked", el("ul", { className: "how" }, evidence.map((t) => el("li", {}, t)))),
      el("p", {}, "Link strength: ", el("strong", {}, f.strength), ` (${(link.confidence || 0).toFixed(2)} on a 0–1 scale, combining shared names 50%, subject 30% and timing 20%).`),
      el("p", { className: "note" }, CAVEAT));
  } else {
    const explanation = link.kind === "involves"
      ? `${b.label} is named in the sentence this event was taken from, so the event is connected to ${b.label}.`
      : `This event is filed under the subject “${b.label}”, taken from the main noun phrase of its sentence.`;
    parts.push(el("h2", {}, link.kind === "involves" ? `This event names ${b.label}` : `This event is about “${b.label}”`), card(a), el("p", {}, explanation));
    const others = neighboursOf(b, "event").filter((x) => x !== a);
    if (others.length) parts.push(...section(`Also connected to ${b.label} (${others.length})`, el("ul", { className: "event-list" }, eventsSorted(others).map((x) => eventItem(x)))));
  }
  $("panel").replaceChildren(...parts);
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
