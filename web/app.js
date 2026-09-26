"use strict";

// Web-only labels. Shared strings (disclaimer, errors) come from /api/meta and each response.
const LABELS = {
  tab_ask:   { am: "ጥያቄ", om: "Gaaffii", ti: "ሕቶ", en: "Ask" },
  tab_doc:   { am: "ሰነድ", om: "Sanada", ti: "ሰነድ", en: "Document" },
  new_chat:  { am: "አዲስ ውይይት", om: "Marii haaraa", ti: "ሓድሽ ዝርርብ", en: "New conversation" },
  drop:      { am: "የሰነድዎን ፎቶ፣ ስካን ወይም PDF ይምረጡ", om: "Suuraa, iskaanii ykn PDF sanada keessanii filadhaa", ti: "ስእሊ፣ ስካን ወይ PDF ሰነድኩም ምረጹ", en: "Photo, scan or PDF of your document" },
  analyze:   { am: "ሰነዱን ተንትን", om: "Sanada xiinxali", ti: "ሰነድ ተንትን", en: "Analyse document" },
  privacy:   { am: "ሰነድዎ ተተንትኖ ይወገዳል፤ አይቀመጥም።", om: "Sanadni keessan xiinxalamee ni balleeffama; hin kuufamu.", ti: "ሰነድኩም ተተንቲኑ ይድምሰስ፤ ኣይዕቀብን።", en: "Your document is processed and discarded. It is not stored." },
  placeholder: { am: "የሕግ ጥያቄዎን ይፃፉ… ለምሳሌ፡ አሠሪዬ ያለ ማስጠንቀቂያ አሰናበተኝ፤ መብቴ ምንድን ነው?", om: "Gaaffii seeraa keessan barreessaa…", ti: "ሕጋዊ ሕቶኹም ጽሓፉ…", en: "Type your legal question… e.g. My employer dismissed me without notice. What are my rights?" },
  summary:   { am: "ማጠቃለያ", om: "Cuunfaa", ti: "ጽማቕ", en: "Summary" },
  parties:   { am: "ተዋዋዮች", om: "Qaamolee", ti: "ተዋዋልቲ", en: "Parties" },
  clauses:   { am: "አንቀጾች እና አደጋዎች", om: "Keewwatoota fi balaa", ti: "ዓንቀጻትን ሓደጋታትን", en: "Clauses & risks" },
  danger:    { am: "አደገኛ", om: "Balaa", ti: "ሓደገኛ", en: "Dangerous" },
  attention: { am: "ትኩረት ይሻል", om: "Xiyyeeffannaa barbaada", ti: "ኣቓልቦ የድሊ", en: "Attention" },
  standard:  { am: "መደበኛ", om: "Idilee", ti: "ልሙድ", en: "Standard" },
  poor_scan: { am: "ሰነዱ በደንብ አልተነበበም። ግልጽ ፎቶ እንደገና ይላኩ።", om: "Sanadni sirriitti hin dubbifamne. Suuraa ifa ta'e irra deebi'aa ergaa.", ti: "ሰነድ ብግቡእ ኣይተነበበን። ንጹር ስእሊ እንደገና ስደዱ።", en: "Parts of the document could not be read. Try a clearer photo." },
  print:     { am: "አትም / አስቀምጥ", om: "Maxxansi / Olkaa'i", ti: "ሕተም / ዕቀብ", en: "Print / save as PDF" },
  no_law:    { am: "ቤተ-መጻሕፍቱ ስለዚህ ጉዳይ ሕግ ገና አልያዘም።", om: "Mana kitaabaa keessa seerri dhimma kanaa hin jiru.", ti: "ቤተ-መጻሕፍቲ ብዛዕባ እዚ ጉዳይ ሕጊ ገና ኣይሓዘን።", en: "The law library does not yet contain the law for this question." },
};

const state = {
  lang: localGet("fitih.lang") || "am",
  sessionId: null,
  meta: null,
};

function localGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } }
const $ = (sel) => document.querySelector(sel);
const L = (key) => (LABELS[key] && (LABELS[key][state.lang] || LABELS[key].en)) || key;
const U = (key) => state.meta?.ui?.[key]?.[state.lang] || state.meta?.ui?.[key]?.en || key;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  node.append(...nodes(children));
  return node;
}

function nodes(children) {
  return children.flat(Infinity).filter((c) => c != null && c !== false)
    .map((c) => (c instanceof Node ? c : document.createTextNode(String(c))));
}

function fill(target, ...children) { target.replaceChildren(...nodes(children)); }

function applyLanguage() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = L(n.dataset.i18n); });
  $("#question").placeholder = L("placeholder");
  $("#disclaimer").textContent = state.meta?.disclaimer?.[state.lang] || "";
}

async function init() {
  try {
    state.meta = await (await fetch("/api/meta")).json();
  } catch { state.meta = { languages: { am: "አማርኛ", om: "Afaan Oromoo", ti: "ትግርኛ", en: "English" }, ui: {} }; }
  const sel = $("#lang");
  for (const [code, name] of Object.entries(state.meta.languages)) sel.append(el("option", { value: code }, name));
  sel.value = state.lang;
  sel.addEventListener("change", () => { state.lang = sel.value; localSet("fitih.lang", state.lang); applyLanguage(); });
  applyLanguage();

  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${tab.dataset.tab}`));
  }));

  $("#ask-form").addEventListener("submit", onAsk);
  $("#question").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#ask-form").requestSubmit(); } });
  $("#new-chat").addEventListener("click", onNewChat);
  $("#file").addEventListener("change", onFilePicked);
  $("#doc-form").addEventListener("submit", onAnalyze);
}

function citationsBlock(citations) {
  if (!citations?.length) return null;
  return el("div", { class: "cites" },
    el("strong", {}, U("sources")),
    citations.map((c) => el("details", {},
      el("summary", {}, c.citation + (c.heading ? ` — ${c.heading}` : "")),
      el("p", {}, c.excerpt),
      c.source ? el("p", {}, el("a", { href: c.source, target: "_blank", rel: "noopener" }, c.source)) : null,
    )));
}

async function onAsk(e) {
  e.preventDefault();
  const q = $("#question").value.trim();
  if (q.length < 2) return;
  const chat = $("#chat");
  chat.append(el("div", { class: "msg user" }, q));
  $("#question").value = "";
  const pending = el("div", { class: "msg" }, el("span", { class: "spinner" }), "…");
  chat.append(pending);
  pending.scrollIntoView({ behavior: "smooth", block: "end" });
  $("#ask-btn").disabled = true;
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, language: state.lang, session_id: state.sessionId }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const data = await res.json();
    state.sessionId = data.session_id;
    fill(pending,
      data.urgent ? el("div", { class: "urgent" }, "⚠") : null,
      el("div", { class: "answer" }, data.answer),
      !data.found_relevant_law ? el("p", { class: "muted small" }, L("no_law")) : null,
      citationsBlock(data.citations),
      data.follow_up_suggestions?.length ? el("div", { class: "chips" }, data.follow_up_suggestions.map((s) =>
        el("button", { class: "chip", type: "button", onclick: () => { $("#question").value = s; $("#ask-form").requestSubmit(); } }, s))) : null,
      el("div", { class: "disc" }, data.disclaimer),
    );
  } catch (err) {
    fill(pending, el("span", { class: "muted" }, `${U("error")} (${err.message})`));
  } finally {
    $("#ask-btn").disabled = false;
  }
}

async function onNewChat() {
  if (state.sessionId) fetch(`/api/session/${encodeURIComponent(state.sessionId)}`, { method: "DELETE" }).catch(() => {});
  state.sessionId = null;
  $("#chat").replaceChildren();
}

function onFilePicked() {
  const f = $("#file").files[0];
  const img = $("#preview");
  $("#file-name").textContent = f ? `${f.name} · ${(f.size / 1024 / 1024).toFixed(1)} MB` : "";
  if (f && f.type.startsWith("image/")) { img.src = URL.createObjectURL(f); img.hidden = false; } else { img.hidden = true; }
}

async function onAnalyze(e) {
  e.preventDefault();
  const f = $("#file").files[0];
  if (!f) return;
  const out = $("#analysis");
  fill(out, el("div", { class: "card" }, el("span", { class: "spinner" }), U("working")));
  $("#doc-btn").disabled = true;
  const form = new FormData();
  form.append("file", f);
  form.append("language", state.lang);
  if (state.sessionId) form.append("session_id", state.sessionId);
  try {
    const res = await fetch("/api/analyze", { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const d = await res.json();
    state.sessionId = d.session_id;
    fill(out, renderAnalysis(d));
  } catch (err) {
    fill(out, el("div", { class: "card muted" }, `${U("error")} (${err.message})`));
  } finally {
    $("#doc-btn").disabled = false;
  }
}

function renderAnalysis(d) {
  const icon = { danger: "🔴", attention: "🟡", standard: "🟢" };
  return el("div", { class: "card" },
    el("h2", {}, d.title),
    el("p", { class: "muted small" }, `${d.document_type} · ${d.domain}`),
    d.legibility !== "good" ? el("p", { class: "urgent" }, L("poor_scan")) : null,
    el("h3", {}, L("summary")), el("p", {}, d.summary),
    d.parties.length ? [el("h3", {}, L("parties")), el("ul", {}, d.parties.map((p) => el("li", {}, p)))] : null,
    d.clauses.length ? [el("h3", {}, L("clauses")), d.clauses.map((c) => el("div", { class: `clause ${c.severity}` },
      el("span", { class: "badge" }, `${icon[c.severity]} ${L(c.severity)}`),
      el("q", {}, c.quote),
      el("div", {}, c.explanation),
    ))] : null,
    d.deadlines.length ? [el("h3", {}, `⏰ ${U("deadlines")}`), el("ul", {}, d.deadlines.map((x) => el("li", {},
      el("strong", {}, x.date_as_written), x.gregorian_date ? ` (${x.gregorian_date})` : "", ` — ${x.description}`)))] : null,
    d.lawyer_questions.length ? [el("h3", {}, `❓ ${U("ask_lawyer")}`), el("ul", {}, d.lawyer_questions.map((q) => el("li", {}, q)))] : null,
    citationsBlock(d.citations),
    el("div", { class: "disc" }, d.disclaimer),
    el("button", { class: "link", type: "button", onclick: () => window.print() }, `🖨 ${L("print")}`),
  );
}

init();
