"use strict";

const $ = (s) => document.querySelector(s);
const STATUS_LABEL = { draft: "draft", in_force: "in force", repealed: "repealed", error: "error" };
let current = null; // law id open in the review panel

function store(k, v) { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch { /* ignore */ } }
function load(k) { try { return sessionStorage.getItem(k); } catch { return null; } }
let token = load("fitih.admin");

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return n;
}

function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `show ${kind}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.className = ""; }, 5000);
}

async function api(path, opts = {}) {
  const res = await fetch(`/api/admin${path}`, {
    ...opts,
    headers: { ...(opts.headers || {}), Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) { signOut(); throw new Error("Wrong admin token."); }
  const body = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) throw new Error(body?.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : res.statusText);
  return body;
}

function badge(status) { return el("span", { class: `badge ${status}` }, STATUS_LABEL[status] || status); }

async function refresh() {
  const data = await api("/laws");
  $("#summary").textContent = `${data.laws.length} law file(s) · ${data.articles_searchable} articles searchable now`;
  const tbody = $("#laws tbody");
  tbody.replaceChildren(...data.laws.map((l) => el("tr", {},
    el("td", {}, el("strong", {}, l.title || l.file), el("div", { class: "muted small" }, l.id, l.proclamation ? ` · ${l.proclamation}` : "")),
    el("td", {}, l.language || "—"),
    el("td", {}, badge(l.status), l.reviewed_by ? el("div", { class: "muted small" }, `${l.reviewed_by}, ${l.reviewed_on}`) : null),
    el("td", {}, l.article_count),
    el("td", {}, l.error ? el("span", { class: "bad" }, "parse error") : l.issues.length ? el("span", { class: "warn-text" }, `${l.issues.length} to check`) : "✓"),
    el("td", {}, l.published ? "✓" : el("span", { class: "muted", title: "Press Publish changes" }, "pending")),
    el("td", {}, l.error ? null : el("button", { type: "button", class: "link", onclick: () => openLaw(l.id) }, "Review")),
  )));
  $("#empty").hidden = data.laws.length > 0;
}

async function openLaw(id) {
  const law = await api(`/laws/${encodeURIComponent(id)}`);
  current = id;
  $("#review").hidden = false;
  $("#rv-title").replaceChildren(law.title, " ", badge(law.status));
  $("#rv-meta").textContent = [law.id, law.proclamation && `Proclamation ${law.proclamation}`, law.language, law.domain,
    law.jurisdiction, law.source && `Source: ${law.source}`, law.reviewed_by && `Approved by ${law.reviewed_by} on ${law.reviewed_on}`]
    .filter(Boolean).join(" · ");
  $("#rv-issues").replaceChildren(law.issues.length
    ? el("div", { class: "notice" }, el("strong", {}, "Check these places first (possible extraction errors):"),
        el("ul", {}, law.issues.map((i) => el("li", {}, i))))
    : el("p", { class: "small ok-text" }, "Article numbering is continuous."));
  $("#rv-count").textContent = law.articles.length;
  $("#rv-articles").replaceChildren(...law.articles.map((a) =>
    el("li", {}, el("strong", {}, `Art. ${a.number}`), a.heading ? ` ${a.heading}` : "",
      el("span", { class: "muted small" }, ` · ${a.chars} chars`), el("div", { class: "muted small" }, a.preview))));
  $("#rv-content").value = law.content;
  $("#rv-delete").hidden = law.status !== "draft";
  $("#rv-repeal").hidden = law.status !== "in_force";
  $("#approve-form").hidden = law.status === "in_force";
  $("#rv-confirm").checked = false;
  $("#rv-download").onclick = (e) => { e.preventDefault(); download(id); };
  $("#review").scrollIntoView({ behavior: "smooth" });
}

async function download(id) {
  const res = await fetch(`/api/admin/laws/${encodeURIComponent(id)}/download`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return toast("Download failed.", "bad");
  const url = URL.createObjectURL(await res.blob());
  el("a", { href: url, download: `${id}.md` }).click();
  URL.revokeObjectURL(url);
}

async function action(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg, "ok"); await refresh(); return r; }
  catch (err) { toast(err.message, "bad"); return null; }
}

function signOut() { token = null; store("fitih.admin", null); $("#app").hidden = true; $("#login").hidden = false; $("#logout").hidden = true; }

async function signIn(t) {
  token = t;
  try {
    await refresh();
    store("fitih.admin", t);
    $("#login").hidden = true; $("#app").hidden = false; $("#logout").hidden = false;
  } catch (err) {
    $("#login-msg").textContent = err.message;
    token = null;
  }
}

$("#login-form").addEventListener("submit", (e) => { e.preventDefault(); signIn($("#token").value.trim()); });
$("#logout").addEventListener("click", signOut);
$("#rv-close").addEventListener("click", () => { $("#review").hidden = true; current = null; });

$("#rv-save").addEventListener("click", () => action(async () => {
  const r = await api(`/laws/${encodeURIComponent(current)}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: $("#rv-content").value }),
  });
  await openLaw(current);
  return r;
}, (r) => r.status === "draft" ? "Saved. The law is a draft again and needs approval." : "No changes."));

$("#approve-form").addEventListener("submit", (e) => {
  e.preventDefault();
  action(async () => {
    const r = await api(`/laws/${encodeURIComponent(current)}/approve`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reviewer: $("#rv-reviewer").value.trim() }),
    });
    await openLaw(current);
    return r;
  }, "Approved. Press Publish changes to make it searchable.");
});

$("#rv-repeal").addEventListener("click", () => {
  if (!confirm("Mark this law as repealed? It will stop being cited after you publish.")) return;
  action(async () => { const r = await api(`/laws/${encodeURIComponent(current)}/repeal`, { method: "POST" }); await openLaw(current); return r; },
    "Marked repealed. Press Publish changes.");
});

$("#rv-delete").addEventListener("click", () => {
  if (!confirm("Delete this draft permanently?")) return;
  action(async () => { const r = await api(`/laws/${encodeURIComponent(current)}`, { method: "DELETE" }); $("#review").hidden = true; current = null; return r; },
    "Draft deleted.");
});

$("#publish").addEventListener("click", async () => {
  const btn = $("#publish");
  btn.disabled = true; btn.textContent = "Publishing…";
  await action(() => api("/publish", { method: "POST" }),
    (r) => `Published: ${r.laws_loaded} law file(s), ${r.articles_searchable} articles searchable.${r.warning ? " " + r.warning : ""}`);
  btn.disabled = false; btn.textContent = "Publish changes";
});

$("#import-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const btn = form.querySelector("button[type=submit]");
  btn.disabled = true; btn.textContent = "Importing…";
  const data = new FormData(form);
  if (!data.get("overwrite")) data.set("overwrite", "false");
  const r = await action(() => api("/import", { method: "POST", body: data }),
    (r) => `Imported ${r.article_count} articles as a draft.${r.issues.length ? ` ${r.issues.length} place(s) to check.` : ""}`);
  btn.disabled = false; btn.textContent = "Import as draft";
  if (r) { form.reset(); openLaw(r.id); }
});

if (token) signIn(token);
