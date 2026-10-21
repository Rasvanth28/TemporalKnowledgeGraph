"use strict";

// Storyline: a small, dependency-free UI over the Temporal Knowledge Graph API (same origin).
// All text from the graph is inserted with textContent, never innerHTML: it comes from news articles.

const KEY_STORAGE = "tkg.apiKey";
const TYPE_LABELS = {
  policy_change: "Policy decision",
  economic: "Economy",
  election: "Politics & elections",
  conflict: "Conflict",
  agreement: "Agreement",
  legal: "Legal",
  general: "News",
};
const REASONS = {
  shared_entities: "same people or organisations",
  similar_topic: "similar subject",
  date_proximity: "close in time",
};
const STRONG = 0.55;
const MEDIUM = 0.4;

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
};

// ---------- API key (per browser) ----------
function getKey() {
  try { return localStorage.getItem(KEY_STORAGE) || ""; } catch { return ""; }
}
function setKey(value) {
  try { value ? localStorage.setItem(KEY_STORAGE, value) : localStorage.removeItem(KEY_STORAGE); } catch { /* private mode */ }
}

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function api(path, params = {}, key = getKey()) {
  const url = new URL(path, window.location.href);
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") url.searchParams.set(k, v);
  let response;
  try {
    response = await fetch(url, { headers: key ? { "X-API-Key": key } : {} });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (response.ok) return response.json();
  if (response.status === 401) throw new ApiError(401, "The API key is missing or wrong.");
  if (response.status === 503) throw new ApiError(503, "The database is unavailable right now (it may be waking up). Try again in a minute.");
  let detail = "";
  try { detail = (await response.json()).detail; } catch { /* not JSON */ }
  throw new ApiError(response.status, typeof detail === "string" && detail ? detail : `Request failed (${response.status}).`);
}

// ---------- formatting ----------
const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const monthFmt = new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric", timeZone: "UTC" });
const shortFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const asDate = (iso) => new Date(`${iso}T00:00:00Z`);

function strengthWord(confidence) {
  if (confidence >= STRONG) return "strong";
  if (confidence >= MEDIUM) return "medium";
  return "weak";
}
function explainReason(reason) {
  const parts = (reason || "").split("+").map((r) => REASONS[r]).filter(Boolean);
  return parts.length ? parts.join(", ") : "weak similarity";
}
function safeUrl(url) {
  try { const u = new URL(url); return ["http:", "https:"].includes(u.protocol) ? u.href : null; } catch { return null; }
}

// ---------- UI state ----------
let current = null; // { chain, articles: Map, mode, label }

function showStatus(message, { error = false } = {}) {
  const status = $("status");
  status.replaceChildren(...(Array.isArray(message) ? message : [message]));
  status.classList.toggle("error", error);
  status.classList.remove("hidden");
}
function hideStatus() { $("status").classList.add("hidden"); }

function showLoading() {
  $("results").classList.add("hidden");
  showStatus([el("div", { className: "skeleton" }), el("div", { className: "skeleton" }), el("div", { className: "skeleton" })]);
}

function openKeyDialog(message = "") {
  $("key-input").value = getKey();
  $("key-error").textContent = message;
  $("key-error").classList.toggle("hidden", !message);
  $("key-dialog").showModal();
}

function handleError(err) {
  if (err.status === 401) {
    hideStatus();
    openKeyDialog(getKey() ? "That key was rejected. Check it and try again." : "");
    return;
  }
  showStatus(err.message || "Something went wrong.", { error: true });
}

// ---------- suggestions ----------
async function loadSuggestions() {
  const box = $("suggestions");
  try {
    const top = await api("entities/top", { limit: 12 });
    if (!top.length) { box.replaceChildren(); return; }
    box.replaceChildren(
      el("span", { className: "label" }, "In the news:"),
      ...top.map((entity) => {
        const chip = el("button", { type: "button", className: "chip", title: `${entity.events} events` },
          entity.name, el("span", { className: "count" }, entity.events));
        chip.addEventListener("click", () => runSearch({ mode: "entity", query: entity.name }));
        return chip;
      }),
    );
  } catch (err) {
    if (err.status === 401) handleError(err);
    box.replaceChildren();
  }
}

// ---------- search ----------
function readForm() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  return { mode, query: $("query").value.trim(), start: $("start").value, end: $("end").value };
}

function syncForm({ mode, query = "", start = "", end = "" }) {
  document.querySelector(`input[name="mode"][value="${mode}"]`).checked = true;
  $("query").value = query;
  if (start) $("start").value = start;
  if (end) $("end").value = end;
  toggleRows();
}

function toggleRows() {
  const dates = document.querySelector('input[name="mode"]:checked').value === "dates";
  $("text-row").classList.toggle("hidden", dates);
  $("date-row").classList.toggle("hidden", !dates);
  $("query").required = !dates;
  $("query").placeholder = document.querySelector('input[name="mode"]:checked').value === "topic"
    ? "e.g. interest rates" : "e.g. Bank of England";
}

function updateUrl(search) {
  const params = new URLSearchParams();
  if (search.mode === "dates") { params.set("start", search.start); params.set("end", search.end); }
  else params.set(search.mode, search.query);
  history.replaceState(null, "", `?${params}`);
}

async function runSearch(search) {
  syncForm(search);
  if (search.mode !== "dates" && !search.query) return;
  if (search.mode === "dates" && (!search.start || !search.end)) {
    showStatus("Pick both a start and an end date.", { error: true });
    return;
  }
  if (!getKey()) { openKeyDialog(); return; }
  updateUrl(search);
  showLoading();
  try {
    let chain;
    if (search.mode === "entity") chain = await api("chains/entity", { name: search.query, limit: 200 });
    else if (search.mode === "topic") chain = await api("chains/topic", { topic: search.query, limit: 200 });
    else chain = await api("chains/date-range", { start: search.start, end: search.end, limit: 200 });

    const ids = [...new Set(chain.events.map((e) => e.article_id).filter(Boolean))];
    const articles = new Map();
    for (let i = 0; i < ids.length; i += 200) {
      for (const article of await api("articles", { ids: ids.slice(i, i + 200).join(",") })) articles.set(article.id, article);
    }
    current = { chain, articles, search };
    render();
  } catch (err) {
    $("results").classList.add("hidden");
    handleError(err);
  }
}

// ---------- rendering ----------
function render() {
  const { chain, articles, search } = current;
  const events = chain.events;
  const minConfidence = Number($("strength").value);
  const links = chain.links.filter((link) => link.confidence >= minConfidence);

  if (!events.length) {
    $("results").classList.add("hidden");
    const what = search.mode === "dates" ? "between those dates" : `for “${search.query}”`;
    showStatus(`No events found ${what}. Try one of the suggestions above, or a shorter name.`);
    return;
  }
  hideStatus();

  const subject = search.mode === "entity" ? (chain.entity?.name || search.query)
    : search.mode === "topic" ? (chain.topic || search.query)
    : `${shortFmt.format(asDate(search.start))} – ${shortFmt.format(asDate(search.end))}`;
  $("results-title").textContent = subject;
  const first = events[0].date, last = events[events.length - 1].date;
  const span = first && last ? ` · ${monthFmt.format(asDate(first))} → ${monthFmt.format(asDate(last))}` : "";
  const notes = [];
  if (chain.match_mode && chain.match_mode !== "exact") notes.push("closest name match");
  if (chain.ambiguous) notes.push("several entities share this name");
  if (chain.truncated) notes.push("showing the first 200 events");
  $("results-meta").textContent = `${events.length} events · ${links.length} connections${span}${notes.length ? ` · ${notes.join(", ")}` : ""}`;

  const byId = new Map(events.map((e) => [e.id, e]));
  const outgoing = new Map(), incoming = new Map();
  for (const link of links) {
    if (!byId.has(link.from_event_id) || !byId.has(link.to_event_id)) continue;
    (outgoing.get(link.from_event_id) || outgoing.set(link.from_event_id, []).get(link.from_event_id)).push(link);
    (incoming.get(link.to_event_id) || incoming.set(link.to_event_id, []).get(link.to_event_id)).push(link);
  }

  const items = [];
  let month = null;
  for (const event of events) {
    const label = event.date ? monthFmt.format(asDate(event.date)) : "Undated";
    if (label !== month) { month = label; items.push(el("li", { className: "month" }, label)); }
    items.push(renderEvent(event, articles.get(event.article_id), outgoing.get(event.id) || [], incoming.get(event.id) || [], byId));
  }
  $("timeline").replaceChildren(...items);
  $("results").classList.remove("hidden");
}

function renderEvent(event, article, outgoing, incoming, byId) {
  const { search } = current;
  const involvesSubject = search.mode !== "entity" || !current.chain.entity
    || event.entities.some((e) => e.id === current.chain.entity.id);

  const type = TYPE_LABELS[event.type] || TYPE_LABELS.general;
  const when = event.date ? dayFmt.format(asDate(event.date)) : "Date unknown";
  const dateLabel = event.date_source === "inferred" ? `${when} (article date)` : when;
  // Year-only mentions ("the first cut since 2008") can pull an event far from its article.
  // Say so instead of presenting a possibly wrong date as fact.
  const far = article?.date && event.date
    && Math.abs(asDate(article.date) - asDate(event.date)) > 31 * 864e5;

  const card = el("div", { className: "card" },
    el("div", { className: "card-top" },
      el("span", { className: "type" }, type),
      el("time", { dateTime: event.date || "" }, dateLabel)),
    el("p", { className: "desc" }, event.description),
  );
  if (far) {
    card.append(el("p", { className: "note" },
      `Date taken from the text; the article is from ${shortFmt.format(asDate(article.date))}, so this may be a reference to an earlier event.`));
  }

  const href = article && safeUrl(article.url);
  if (article && href) {
    card.append(el("a", { className: "headline", href, target: "_blank", rel: "noopener noreferrer" },
      `📰 ${article.title || "Read the article"}`, article.source ? ` — ${article.source}` : "", " ↗"));
  }

  const tags = el("div", { className: "tags" });
  for (const entity of event.entities) {
    const chip = el("button", { type: "button", className: "chip", title: `${entity.type}: see this story` }, entity.name);
    chip.addEventListener("click", () => runSearch({ mode: "entity", query: entity.name }));
    tags.append(chip);
  }
  for (const topic of event.topics) {
    if (topic === "general") continue;
    const chip = el("button", { type: "button", className: "chip", title: "Topic: see this story" }, `# ${topic}`);
    chip.addEventListener("click", () => runSearch({ mode: "topic", query: topic }));
    tags.append(chip);
  }
  if (!involvesSubject) tags.append(el("span", { className: "tag" }, "connected story"));
  if (tags.childElementCount) card.append(tags);

  if (outgoing.length || incoming.length) {
    const box = el("div", { className: "links" });
    if (incoming.length) box.append(el("p", {}, "Follows from"), linkList(incoming, "from_event_id", "←", byId));
    if (outgoing.length) box.append(el("p", {}, "Led to"), linkList(outgoing, "to_event_id", "→", byId));
    card.append(box);
  }

  const item = el("li", { className: `event${involvesSubject ? "" : " indirect"}`, id: `ev-${event.id}` }, card);
  item.style.setProperty("--dot", `var(--${TYPE_LABELS[event.type] ? event.type.split("_")[0] : "general"})`);
  return item;
}

function linkList(links, endKey, arrow, byId) {
  const sorted = [...links].sort((a, b) => b.confidence - a.confidence);
  return el("ul", {}, sorted.map((link) => {
    const other = byId.get(link[endKey]);
    const strength = strengthWord(link.confidence);
    const button = el("button", { type: "button", className: "link-btn", title: `Confidence ${link.confidence.toFixed(2)}` },
      el("span", { className: "arrow" }, arrow),
      el("span", {},
        el("span", { className: strength === "strong" ? "strong" : "" }, other.description),
        el("span", { className: "why" }, ` · ${other.date ? shortFmt.format(asDate(other.date)) : ""} · ${strength} link: ${explainReason(link.reason)}`)));
    button.addEventListener("click", () => focusEvent(other.id));
    return el("li", {}, button);
  }));
}

function focusEvent(id) {
  const target = document.getElementById(`ev-${id}`);
  if (!target) return;
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  target.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "center" });
  target.classList.add("flash");
  setTimeout(() => target.classList.remove("flash"), 1600);
}

// ---------- wiring ----------
function initDates() {
  const end = new Date();
  const start = new Date(end);
  start.setMonth(start.getMonth() - 3);
  $("end").value = end.toISOString().slice(0, 10);
  $("start").value = start.toISOString().slice(0, 10);
}

function searchFromUrl() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("entity")) return { mode: "entity", query: params.get("entity") };
  if (params.get("topic")) return { mode: "topic", query: params.get("topic") };
  if (params.get("start") && params.get("end")) return { mode: "dates", start: params.get("start"), end: params.get("end") };
  return null;
}

document.querySelectorAll('input[name="mode"]').forEach((radio) => radio.addEventListener("change", toggleRows));
$("search").addEventListener("submit", (event) => { event.preventDefault(); runSearch(readForm()); });
$("strength").addEventListener("change", () => current && render());
$("key-button").addEventListener("click", () => openKeyDialog());
$("key-clear").addEventListener("click", () => { setKey(""); $("key-input").value = ""; });

$("key-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const key = $("key-input").value.trim();
  if (!key) return;
  try {
    await api("entities/top", { limit: 1 }, key);
  } catch (err) {
    $("key-error").textContent = err.status === 401 ? "That key was rejected." : err.message;
    $("key-error").classList.remove("hidden");
    return;
  }
  setKey(key);
  $("key-dialog").close();
  loadSuggestions();
  const pending = searchFromUrl();
  if (pending) runSearch(pending);
});

initDates();
toggleRows();
if (!getKey()) {
  openKeyDialog();
} else {
  loadSuggestions();
  const initial = searchFromUrl();
  if (initial) runSearch(initial);
}
