/* Awlchemy frontend: plain JS, hash routing. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = $("#app");

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function md(text) {
  // Never render Markdown unsanitised: if either library failed to load, show plain text.
  const html = window.marked && window.DOMPurify
    ? DOMPurify.sanitize(marked.parse(text || "", { breaks: false }))
    : `<p>${esc(text).replace(/\n/g, "<br>")}</p>`;
  // "Title (#12)" in teacher answers -> link to that pattern
  return html.replace(/\(#(\d+)\)/g, '(<a href="#/p/$1">open pattern</a>)');
}

/* The demo site (see demo/) runs this same file without a server: it sets window.AWLCHEMY_DEMO,
   which answers the API calls and supplies the pictures. In the real app it is undefined. */
const demo = window.AWLCHEMY_DEMO;
const request = (path, init) => (demo ? demo.fetch(path, init) : fetch(path, init));
const asset = (path) => (demo ? demo.asset(path) : path);

async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) {
    init.method = init.method || "POST";
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.json);
  }
  const res = await request(path, init);
  if (!res.ok) {
    let msg = `${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function toast(text, ms = 3500) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

const DIFF = { Easy: 1, Medium: 2, Hard: 3, "Very Hard": 4 };
function holes(difficulty) {
  const n = DIFF[difficulty] || 0;
  const label = difficulty ? `${difficulty} difficulty` : "Difficulty not rated";
  return `<span class="holes ${n ? "" : "none"}" title="${label}" aria-label="${label}">${[1, 2, 3, 4].map((i) => `<i class="${i <= n ? "on" : ""}"></i>`).join("")}</span>`;
}
const STATUS = { "": "Not started", wishlist: "Want to make", in_progress: "Making", done: "Made" };
const STAR = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.8l2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.1l-5.7 3.2 1.2-6.4L2.8 9.5l6.4-.8z"/></svg>`;
const STAR_O = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2.8l2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.1l-5.7 3.2 1.2-6.4L2.8 9.5l6.4-.8z"/></svg>`;

function ago(iso) {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

/* ------------------------------------------------------------------ shared state */
const state = { stats: null, settings: null, filters: { q: "", difficulty: "", status: "", source: "", favorite: false, kind: "pattern" } };

async function loadSettings() {
  state.settings = await api("/api/settings");
  return state.settings;
}

/* ------------------------------------------------------------------ jobs */
async function pollJob(job, onUpdate) {
  let j = job;
  while (j.status === "running") {
    onUpdate?.(j);
    await new Promise((r) => setTimeout(r, 1200));
    j = await api(`/api/jobs/${j.id}`);
  }
  onUpdate?.(j);
  if (j.status === "error") throw new Error(j.error);
  return j;
}

/* ------------------------------------------------------------------ top bar: sync */
let syncWatching = false;
let libRefreshedAt = 0;
const BASE_TITLE = document.title;

async function refreshStats() {
  state.stats = await api("/api/stats");
  const job = state.stats.library_job;
  if (job && !syncWatching) state.job = job;
  renderSyncStatus();
  renderSyncPanel();
  if (job && !syncWatching) {
    syncWatching = true;
    pollJob(job, (j) => {
      state.job = j;
      renderSyncStatus();
      renderSyncPanel();
      // Patterns are saved one by one while they're read, so let them appear as they arrive.
      if (j.progress?.phase === "indexing" && route().name === "library" && Date.now() - libRefreshedAt > 6000) {
        libRefreshedAt = Date.now();
        renderLibrary();
      }
    })
      .then((j) => toast(doneMessage(j), 7000))
      .catch((e) => toast(`The library update stopped: ${e.message}`, 8000))
      .finally(async () => {
        syncWatching = false;
        state.job = null;
        document.title = BASE_TITLE;
        await refreshStats();
        if (route().name === "library" || route().name === "bench") render();
      });
  }
}

function doneMessage(j) {
  const r = j.result || {};
  const failed = r.failed ? ` ${r.failed} file(s) couldn't be downloaded; they'll be tried again next time.` : "";
  if (j.kind === "sync") {
    if (r.added) return `Your library is ready: ${r.added} new pattern file(s) added.${failed}`;
    return `Your library is up to date.${failed}`;
  }
  if (j.kind === "index" && r.added) return `${r.added} new pattern file(s) added to your library.`;
  return "Library updated.";
}

/* What the running library job is doing, in words a person can follow. */
const STEPS = {
  listing: "Find your patterns",
  downloading: "Bring them to this computer",
  indexing: "Read each pattern and make its cover",
};

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function fmtBytes(b) {
  if (!b) return "";
  return b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(b / 1e6))} MB`;
}

function timeLeft(p) {
  if (!p.total || !p.phase_started) return "";
  const elapsed = Date.now() / 1000 - p.phase_started;
  if (p.done < 3 || elapsed < 15) return "working out how long this takes…";
  const left = ((p.total - p.done) * elapsed) / p.done;
  if (left < 60) return "less than a minute left";
  if (left < 3600) return `about ${Math.round(left / 60)} min left`;
  const h = Math.floor(left / 3600), m = Math.round((left % 3600) / 60);
  return `about ${h} h${m ? ` ${m} min` : ""} left`;
}

function jobShort(job) {
  const p = job.progress || {};
  const pct = p.total ? Math.min(100, Math.round((100 * (p.done || 0)) / p.total)) : null;
  const fetching = p.source_kind === "folder" ? "Copying" : "Downloading";
  if (job.kind === "import") return { text: "Importing…", pct: null };
  if (p.phase === "listing") return { text: `Finding patterns… ${(p.found || 0) + (p.have || 0)} files`, pct: null };
  if (p.phase === "downloading" && p.total) return { text: `${fetching} ${p.done} of ${p.total}`, pct };
  if (p.phase === "indexing" && p.total) return { text: `Reading patterns ${p.done} of ${p.total}`, pct };
  return { text: "Updating library…", pct: null };
}

function renderSyncStatus() {
  const s = state.stats;
  const el = $("#sync-status");
  if (!s) return;
  const job = state.job?.status === "running" ? state.job : s.library_job;
  if (job) {
    const { text, pct } = jobShort(job);
    el.innerHTML = `<button class="sync-progress" id="sync-open" title="See what's happening">
        <span class="spinner"></span><span class="label">${esc(text)}</span>
        ${pct != null ? `<span class="bar" aria-hidden="true"><i style="width:${pct}%"></i></span>` : ""}</button>`;
    document.title = pct != null ? `(${pct}%) ${BASE_TITLE}` : BASE_TITLE;
    $("#sync-open").addEventListener("click", () => {
      if (route().name !== "library") location.hash = "#/";
      setTimeout(() => $("#sync-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }), 300);
    });
    return;
  }
  el.innerHTML = `<span class="label">Synced ${esc(ago(s.last_sync))}</span><button class="btn" id="sync-btn">Check for new patterns</button>`;
  $("#sync-btn")?.addEventListener("click", async () => {
    await api("/api/sync", { method: "POST" });
    refreshStats();
  });
}

function renderSyncPanel() {
  const el = $("#sync-panel");
  if (!el) return;
  const job = state.job;
  if (!job || job.status !== "running" || job.kind === "import") { el.innerHTML = ""; return; }
  const p = job.progress || {};
  const first = job.kind === "sync" && !state.stats?.last_sync;
  const drive = p.source_kind !== "folder";
  const order = job.kind === "sync" ? ["listing", "downloading", "indexing"] : ["indexing"];
  const at = Math.max(0, order.indexOf(p.phase));

  const detail = (k, st) => {
    if (k === "listing") {
      const have = p.have ? `, ${plural(p.have, "file")} already here` : "";
      if (st === "now") return `Looked in ${plural(p.folders || 0, "folder")} so far · ${plural(p.found || 0, "new file")} to download${have}`;
      return `${plural(p.found || 0, "new file")} to download${have}`;
    }
    if (k === "downloading") {
      if (st !== "now") return st === "done" ? `${plural(p.total || 0, "file")} downloaded` : "";
      return [`${p.done || 0} of ${p.total || 0}`, fmtBytes(p.bytes), timeLeft(p)].filter(Boolean).join(" · ");
    }
    if (st !== "now") return "";
    return [`${p.done || 0} of ${p.total || 0}`, timeLeft(p)].filter(Boolean).join(" · ") +
      `<br><span class="muted">Patterns show up below as soon as they're ready.</span>`;
  };
  const bar = (k) => (k === p.phase && p.total ? `<span class="bar"><i style="width:${Math.round((100 * (p.done || 0)) / p.total)}%"></i></span>` : "");
  const steps = order.map((k, i) => {
    const st = i < at ? "done" : i === at ? "now" : "next";
    const label = k === "downloading" && !drive ? "Copy them into your library" : STEPS[k];
    return `<li class="${st}"><span class="dot" aria-hidden="true">${st === "done" ? "✓" : i + 1}</span>
      <div><strong>${label}</strong><div class="step-detail">${detail(k, st)}</div>${bar(k)}</div></li>`;
  }).join("");

  const title = job.kind !== "sync" ? "Reading new patterns" : first ? "Setting up your library" : "Checking for new patterns";
  const source = p.source ? `<p class="muted">${p.source_count > 1 ? `Source ${p.source_index} of ${p.source_count}: ` : "From "}<strong>${esc(p.source)}</strong></p>` : "";
  const why = first
    ? `<div class="why"><h3>Why the first time takes a while</h3>
        <p>${drive
          ? "Every pattern file is downloaded from Google Drive one at a time, with a short pause between files so Drive keeps serving them. Collections often hold hundreds of files, because many patterns come in several paper sizes."
          : "Every pattern file is copied into your library first."}
        Then each one is opened to read its text and make a cover picture.</p>
        <p><strong>This only happens once.</strong> After this, Awlchemy only fetches files that are new.</p></div>`
    : "";
  el.innerHTML = `<section class="sync-panel" aria-live="polite">
      <h2>${title}</h2>${source}
      <ol class="steps-progress">${steps}</ol>
      ${p.current ? `<p class="now-file">Now: <span>${esc(p.current)}</span></p>` : ""}
      ${p.failed ? `<p class="warn">${p.failed} file(s) couldn't be downloaded. They'll be tried again next time.</p>` : ""}
      ${why}
      <p class="muted small">You can keep browsing or close this tab. The work carries on as long as Awlchemy is running, and if you stop it, it picks up where it left off.</p>
    </section>`;
}

/* ------------------------------------------------------------------ router */
function route() {
  const h = location.hash.replace(/^#/, "") || "/";
  let m;
  if ((m = h.match(/^\/p\/(\d+)(?:\/(\w+))?/))) return { name: "pattern", id: +m[1], tab: m[2] || "guide" };
  if (h.startsWith("/bench")) return { name: "bench" };
  if (h.startsWith("/learn")) return { name: "learn" };
  if (h.startsWith("/settings")) return { name: "settings" };
  return { name: "library" };
}

async function render() {
  const r = route();
  $$(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === r.name));
  try {
    if (r.name === "pattern") await renderPattern(r.id, r.tab);
    else if (r.name === "bench") await renderBench();
    else if (r.name === "learn") await renderLearn();
    else if (r.name === "settings") await renderSettings();
    else await renderLibrary();
  } catch (e) {
    app.innerHTML = `<div class="page empty"><h2>Something went wrong</h2><p>${esc(e.message)}</p></div>`;
  }
}
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); render(); });

/* ------------------------------------------------------------------ library */
function card(p) {
  const cls = p.status === "done" ? "made" : p.status === "in_progress" ? "making" : "";
  return `<a class="card ${cls}" href="#/p/${p.id}">
    <div class="cover"><img loading="lazy" src="${asset(`/api/patterns/${p.id}/cover`)}" alt=""></div>
    <button class="star fav ${p.favorite ? "on" : ""}" data-fav="${p.id}" aria-label="Favourite">${p.favorite ? STAR : STAR_O}</button>
    <div class="body">
      <div class="title">${esc(p.title)}</div>
      ${p.collection && p.collection !== p.title ? `<div class="muted small">${esc(p.collection)}</div>` : ""}
      ${p.papers?.length > 1 ? `<div class="papers" title="Print sizes included">${p.papers.map(esc).join(" · ")}</div>` : ""}
      <div class="meta">${p.kind === "guide" ? `<span>${p.pages} pages</span>` : holes(p.difficulty)}
        ${p.status ? `<span class="tag ${p.status}">${STATUS[p.status]}</span>` : p.has_guide ? `<span class="tag">Guide ready</span>` : ""}</div>
    </div></a>`;
}

function bindFavs(root, reload) {
  $$("[data-fav]", root).forEach((b) => b.addEventListener("click", async (ev) => {
    ev.preventDefault(); ev.stopPropagation();
    const on = !b.classList.contains("on");
    await api(`/api/patterns/${b.dataset.fav}`, { method: "PATCH", json: { favorite: on } });
    b.classList.toggle("on", on);
    b.innerHTML = on ? STAR : STAR_O;
    reload?.();
  }));
}

async function renderLibrary() {
  if (!state.stats) await refreshStats();
  const f = state.filters;
  const qs = new URLSearchParams({ q: f.q, difficulty: f.difficulty, status: f.status, source: f.source, kind: f.kind, favorite: f.favorite ? "true" : "false" });
  const items = await api(`/api/patterns?${qs}`);
  const s = state.stats;

  const chip = (group, value, label, extra = "") => `<button class="chip ${f[group] === value ? "on" : ""}" data-g="${group}" data-v="${esc(value)}">${label}${extra}</button>`;
  const sources = s.sources || [];

  if (!$(".lib", app)) {
    app.innerHTML = `<div class="page"><div class="lib">
      <aside class="filters" id="filters"></aside>
      <section>
        <div class="lib-head"><h1 id="lib-title">Patterns</h1><span class="count" id="lib-count"></span>
          <div class="actions"><button class="btn primary" id="add-btn">Add a pattern</button></div></div>
        <div id="sync-panel"></div>
        <div class="search"><input type="search" id="q" placeholder="Search titles, folders and pattern text, e.g. “wallet” or “rivet”" value="${esc(f.q)}"></div>
        <div id="results"></div>
      </section></div></div>`;
    let t;
    $("#q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { f.q = e.target.value; renderLibrary(); }, 250); });
    $("#add-btn").addEventListener("click", openAddModal);
  }
  renderSyncPanel();

  $("#filters").innerHTML = `
    <h3>Show</h3><div class="chip-list">${chip("kind", "pattern", "Patterns")}${chip("kind", "guide", "Guide books")}</div>
    <h3>Difficulty</h3><div class="chip-list">${chip("difficulty", "", "Any")}${["Easy", "Medium", "Hard", "Very Hard"].map((d) => chip("difficulty", d, d, holes(d))).join("")}${chip("difficulty", "unrated", "Not rated")}</div>
    <h3>Progress</h3><div class="chip-list">${chip("status", "", "Everything")}${chip("status", "wishlist", "Want to make")}${chip("status", "in_progress", "Making")}${chip("status", "done", "Made")}
      <button class="chip ${f.favorite ? "on" : ""}" data-g="favorite">Favourites</button></div>
    ${sources.length > 1 ? `<h3>Source</h3><div class="chip-list">${chip("source", "", "All")}${sources.map((x) => chip("source", x, esc(x))).join("")}</div>` : ""}`;
  $$("#filters .chip").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.g === "favorite") f.favorite = !f.favorite;
    else f[b.dataset.g] = b.dataset.v;
    renderLibrary();
  }));

  $("#lib-title").textContent = f.kind === "guide" ? "Guide books" : "Patterns";
  $("#lib-count").textContent = `${items.length} shown`;
  const results = $("#results");
  if (!items.length) {
    const nothing = !s.total;
    if (nothing && (state.job?.status === "running" || s.library_job)) { results.innerHTML = ""; return; }
    results.innerHTML = nothing
      ? `<div class="empty"><h2>Your library is empty</h2><p>${s.library_job ? "Fetching your patterns. They appear here as they're indexed." : s.source_count ? "Fetch the patterns from your sources, or add your own." : "Add where your patterns live (a shared Google Drive folder or a folder on this computer) under <a href=\"#/settings\">Settings</a>, or import PDFs directly."}</p>
          ${s.library_job || !s.source_count ? "" : `<p><button class="btn primary" id="first-sync">Fetch my patterns</button></p>`}</div>`
      : `<div class="empty"><h2>No matches</h2><p>Try fewer words or clear a filter.</p></div>`;
    $("#first-sync")?.addEventListener("click", async () => { await api("/api/sync", { method: "POST" }); refreshStats(); });
    return;
  }
  results.innerHTML = `<div class="grid">${items.map(card).join("")}</div>`;
  bindFavs(results);
}

/* ------------------------------------------------------------------ bench */
async function renderBench() {
  const [making, want, made] = await Promise.all(["in_progress", "wishlist", "done"].map((st) => api(`/api/patterns?status=${st}&kind=`)));
  const sec = (title, items, empty) => `<section class="section"><h2>${title}</h2>${items.length ? `<div class="grid">${items.map(card).join("")}</div>` : `<p class="muted">${empty}</p>`}</section>`;
  app.innerHTML = `<div class="page">
    <h1>My bench</h1>
    <p class="muted">Projects you're making, want to make, and have finished. Set the status on any pattern page.</p>
    ${sec("Making now", making, "Nothing on the bench yet. Open a pattern and choose “Making”.")}
    ${sec("Want to make", want, "Mark patterns as “Want to make” to build a shortlist.")}
    ${sec("Made", made, "Finished pieces will show up here.")}
    <p><a class="btn" href="#/learn">Ask the Awlchemist what to make next</a></p></div>`;
  bindFavs(app);
}

/* ------------------------------------------------------------------ add pattern modal */
function openAddModal() {
  const bg = document.createElement("div");
  bg.className = "modal-bg";
  bg.innerHTML = `<div class="modal" role="dialog" aria-label="Add a pattern">
    <button class="btn quiet close" aria-label="Close">✕</button>
    <h2>Add a pattern</h2>
    <p class="muted">Bought a pattern somewhere else? Drop the PDF (or ZIP) here, or paste a link.</p>
    <label for="coll">Folder name <span class="muted">(optional)</span></label>
    <input type="text" id="coll" placeholder="e.g. Etsy card wallets">
    <div class="hint">Groups the files together in your library. Leave empty to use the file or page name.</div>
    <label>Files</label>
    <div class="drop" id="drop" tabindex="0">Drop PDF or ZIP files here, or <u>choose files</u><input type="file" id="file" accept=".pdf,.zip" multiple hidden></div>
    <div class="or">or</div>
    <label for="url">Link</label>
    <input type="url" id="url" placeholder="Google Drive folder or file, a direct PDF link, or a page that links to PDFs">
    <div class="hint">Shops that need you to log in (Etsy, Gumroad…) can't be fetched: download the file there and drop it above.</div>
    <p style="margin-top:16px"><button class="btn primary" id="go-url">Add from link</button></p>
    <div class="joblog hidden" id="log"></div>
  </div>`;
  document.body.appendChild(bg);
  const close = () => bg.remove();
  $(".close", bg).onclick = close;
  bg.addEventListener("click", (e) => { if (e.target === bg) close(); });
  const log = $("#log", bg);
  const showJob = (j) => { log.classList.remove("hidden"); log.textContent = j.log.join("\n"); log.scrollTop = 1e9; };
  const finish = async (job) => {
    try {
      const j = await pollJob(job, showJob);
      const n = (j.result && j.result.added) || 0;
      toast(n ? `Added ${n} pattern(s)` : "Done. No new PDFs found.");
      close();
      await refreshStats();
      if (route().name === "library") renderLibrary();
    } catch (e) { log.textContent += `\n${e.message}`; }
  };
  const upload = async (files) => {
    if (!files.length) return;
    const fd = new FormData();
    [...files].forEach((f) => fd.append("files", f));
    fd.append("collection", $("#coll", bg).value);
    try { finish(await api("/api/import/upload", { method: "POST", body: fd })); }
    catch (e) { toast(e.message, 6000); }
  };
  const drop = $("#drop", bg), file = $("#file", bg);
  drop.onclick = () => file.click();
  drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") file.click(); };
  file.onchange = () => upload(file.files);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); upload(e.dataTransfer.files); };
  $("#go-url", bg).onclick = async () => {
    const url = $("#url", bg).value.trim();
    if (!url) return $("#url", bg).focus();
    try { finish(await api("/api/import/url", { json: { url, collection: $("#coll", bg).value } })); }
    catch (e) { toast(e.message, 6000); }
  };
}

/* ------------------------------------------------------------------ pattern page */
let current = null; // pattern being shown

// Letter is the everyday paper in North America and a few other places; A4 everywhere else.
const LETTER_REGIONS = ["US", "CA", "MX", "PH", "CL", "CO", "VE", "GT", "CR", "PR"];
const homePaper = () => (LETTER_REGIONS.includes((navigator.language.split("-")[1] || "").toUpperCase()) ? "Letter" : "A4");
const PAPER_HINT = {
  A4: "home printer", Letter: "home printer", Legal: "home printer", A5: "home printer",
  A3: "large office printer", Tabloid: "large office printer",
  A2: "print shop, large sheets", A1: "print shop, one big sheet", A0: "print shop, one big sheet",
};

function printBox(p, pdf) {
  const tip = `<p>Print at <strong>100% / “Actual size”</strong>, never “Fit to page”, and measure the calibration square before you cut leather.</p>`;
  const prints = p.prints || [];
  if (!prints.length) {
    return `<div class="print-box"><a class="btn primary" href="${pdf}" target="_blank" rel="noopener">Open the original PDF to print</a>${tip}</div>`;
  }
  const home = homePaper();
  const sorted = [...prints].sort((a, b) => (b.paper === home) - (a.paper === home));
  const fileUrl = (v) => asset(`/files/${v.id}/${encodeURIComponent(v.rel_path.split("/").pop())}`);
  const sizes = sorted.map((v, i) => `<a class="size ${i === 0 ? "first" : ""}" href="${fileUrl(v)}" target="_blank" rel="noopener">
      <strong>${esc(v.paper)}${v.label ? `<small>${esc(v.label)}</small>` : ""}</strong><span>${plural(v.pages || 0, "page")} · ${PAPER_HINT[v.paper] || "printer"}</span></a>`).join("");
  const instructions = p.paper ? "" : `<p class="small"><a href="${pdf}" target="_blank" rel="noopener">Open the instructions PDF</a></p>`;
  const tiled = prints.some((v) => PAPER_HINT[v.paper] === "home printer") && prints.some((v) => /^A[0-2]$/.test(v.paper));
  return `<div class="print-box">
      <h3>Print the pattern pieces</h3>
      <p class="small">Pick the paper you have. ${tiled ? "Home sizes print the pieces across several pages that you tape together; the big sizes are for a copy shop." : ""}</p>
      <div class="sizes">${sizes}</div>${tip}${instructions}</div>`;
}

async function renderPattern(id, tab) {
  if (!state.settings) await loadSettings();
  const p = await api(`/api/patterns/${id}`);
  current = p;
  const pdf = asset(`/files/${p.id}/${encodeURIComponent(p.rel_path.split("/").pop())}`);
  const pageBtns = Array.from({ length: Math.min(p.pages || 0, 24) }, (_, i) =>
    `<button data-page="${i}" title="Page ${i + 1}"><img loading="lazy" src="${asset(`/api/patterns/${p.id}/page/${i}?w=200`)}" alt="Page ${i + 1}"><span>${i + 1}</span></button>`).join("");

  app.innerHTML = `<div class="pat">
    <aside class="bench"><div class="bench-inner">
      <div class="crumbs"><a href="#/">Library</a>${p.collection ? ` / ${esc(p.collection)}` : ""}</div>
      <h1 id="pat-title">${esc(p.title)}</h1>
      <div class="sub">${p.kind === "guide" ? "Guide book" : holes(p.difficulty) + `<span>${esc(p.difficulty || "Not rated")}</span>`}<span>${p.pages} page${p.pages === 1 ? "" : "s"}</span><span>${esc(p.source)}</span>
        <button class="linkish" id="rename">Rename</button></div>
      <div class="hero-img"><img id="hero" src="${asset(`/api/patterns/${p.id}/cover?t=${Date.now()}`)}" alt="${esc(p.title)}"></div>
      ${printBox(p, pdf)}
      ${p.kind === "pattern" ? `<div class="pat-fields"><div><label for="status">Status</label>
      <select id="status">${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${p.status === k ? "selected" : ""}>${v}</option>`).join("")}</select></div>
      <div><label for="difficulty">Difficulty</label>
      <select id="difficulty"><option value="">Not rated</option>${Object.keys(DIFF).map((d) => `<option ${p.difficulty === d ? "selected" : ""}>${d}</option>`).join("")}</select></div></div>` : ""}
      <h3>Pages</h3>
      <div class="pages" id="pages">${pageBtns}</div>
      <p class="small" style="margin-top:8px"><button class="btn" id="set-cover" disabled>Use selected page as the picture</button></p>
      ${p.siblings?.length ? `<h3>Also in this folder</h3><div class="siblings">${p.siblings.map((s) => `<a href="#/p/${s.id}">${esc(s.title)}</a>`).join("")}</div>` : ""}
    </div></aside>
    <section class="desk">
      <div class="tabs" role="tablist">
        ${p.kind === "pattern" ? `<button data-tab="guide">Build guide</button>` : ""}
        <button data-tab="text">Instructions</button>
        <button data-tab="ask">Ask the Awlchemist</button>
        <button data-tab="notes">My notes</button>
      </div>
      <div class="tabpane" id="pane"></div>
    </section></div>`;

  let selectedPage = null;
  $$("#pages button").forEach((b) => b.addEventListener("click", () => {
    $$("#pages button").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    selectedPage = +b.dataset.page;
    $("#hero").src = asset(`/api/patterns/${p.id}/page/${selectedPage}?w=900`);
    $("#set-cover").disabled = false;
  }));
  $("#rename").addEventListener("click", () => {
    const h = $("#pat-title");
    if ($("input", h)) return;
    h.innerHTML = `<input type="text" id="title-in" maxlength="200" aria-label="Pattern name">`;
    const inp = $("#title-in");
    inp.value = p.title;
    inp.focus();
    inp.select();
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter") inp.blur();
      if (e.key === "Escape") { inp.value = p.title; inp.blur(); }
    });
    inp.addEventListener("blur", async () => {
      const name = inp.value.trim();
      if (name && name !== p.title) {
        try {
          await api(`/api/patterns/${p.id}`, { method: "PATCH", json: { title: name } });
          p.title = name;
          toast("Renamed");
        } catch (e) { toast(e.message, 6000); }
      }
      h.textContent = p.title;
    });
  });
  $("#difficulty")?.addEventListener("change", async (e) => {
    await api(`/api/patterns/${p.id}`, { method: "PATCH", json: { difficulty: e.target.value } });
    toast(e.target.value ? `Rated “${e.target.value}”` : "Rating cleared");
    renderPattern(p.id, route().tab);
  });
  $("#set-cover").addEventListener("click", async () => {
    const fd = new FormData(); fd.append("page", selectedPage);
    await api(`/api/patterns/${p.id}/cover`, { method: "POST", body: fd });
    toast("Picture updated");
  });
  $("#status")?.addEventListener("change", async (e) => {
    await api(`/api/patterns/${p.id}`, { method: "PATCH", json: { status: e.target.value } });
    toast(`Marked as “${STATUS[e.target.value]}”`);
  });

  const tabs = $$(".tabs button");
  if (!tabs.some((b) => b.dataset.tab === tab)) tab = tabs[0].dataset.tab;
  const show = (t, opts) => {
    tabs.forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
    history.replaceState(null, "", `#/p/${p.id}/${t}`);
    const pane = $("#pane");
    if (t === "guide") renderGuide(pane, p);
    if (t === "text") renderInstructions(pane, p);
    if (t === "ask") renderChat(pane, { patternId: p.id, ...opts });
    if (t === "notes") renderNotes(pane, p);
  };
  tabs.forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  current.showTab = show;
  show(tab);
}

async function renderInstructions(pane, p) {
  pane.innerHTML = `<p class="muted">Loading…</p>`;
  const { markdown } = await api(`/api/patterns/${p.id}/markdown`);
  pane.innerHTML = markdown.trim()
    ? `<p class="muted small">The pattern's text, converted for easy reading at the bench. Diagrams and the printable pieces stay in the original PDF.</p><div class="md instructions">${md(markdown)}</div>`
    : `<div class="empty"><h2>This pattern is all pictures</h2><p>There's no text to convert, so use the page previews on the left or the original PDF. The build guide and the Awlchemist still read the pages as images.</p></div>`;
}

function renderNotes(pane, p) {
  pane.innerHTML = `<label for="notes">Notes for this project</label>
    <textarea id="notes" rows="12" placeholder="Leather you used, what went well, what you'd change next time…">${esc(p.notes)}</textarea>
    <p class="hint" id="saved"></p>`;
  let t;
  $("#notes").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(async () => {
      await api(`/api/patterns/${p.id}`, { method: "PATCH", json: { notes: e.target.value } });
      p.notes = e.target.value;
      $("#saved").textContent = "Saved";
    }, 600);
  });
}

/* ------------------------------------------------------------------ guide */
const norm = (s) => s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
function ownsTool(name) {
  const n = norm(name);
  return (state.settings.toolkit || []).some((t) => { const o = norm(t); return o && (n === o || n.includes(o) || o.includes(n)); });
}

async function renderGuide(pane, p) {
  const g = p.guide;
  if (!g) {
    const job = await api(`/api/patterns/${p.id}/guide-job`);
    pane.innerHTML = `<div class="guide-cta">
      <h2>Get a build guide for this pattern</h2>
      <p>The Awlchemist reads every page of the PDF, including the drawings, and writes you:</p>
      <ul><li>which leather to use for each part, with thickness and why</li>
      <li>the tools, hardware and thread you need, and what you already own</li>
      <li>every step explained for a beginner, with tips and the mistakes to avoid</li>
      <li>the places where the pattern is vague, and how to handle them</li></ul>
      ${state.stats?.claude?.found === false ? `<p class="callout warn">Claude Code wasn't found on this computer. See <a href="#/settings">Settings</a>.</p>` : ""}
      <p><button class="btn primary" id="mk">Write the build guide</button> <span class="muted small" id="mk-status"></span></p></div>`;
    const go = async (jobStart) => {
      $("#mk").disabled = true;
      $("#mk-status").innerHTML = `<span class="spinner"></span> Reading the pattern… this takes a minute or two.`;
      try {
        await pollJob(jobStart, (j) => { if (j.log.length) $("#mk-status").innerHTML = `<span class="spinner"></span> ${esc(j.log[j.log.length - 1])}`; });
        if (current?.id === p.id) renderPattern(p.id, "guide");
      } catch (e) {
        $("#mk").disabled = false;
        $("#mk-status").textContent = e.message;
      }
    };
    $("#mk").addEventListener("click", async () => {
      try { go(await api(`/api/patterns/${p.id}/guide`, { method: "POST" })); } catch (e) { $("#mk-status").textContent = e.message; }
    });
    if (job.id) go(job);
    return;
  }

  const done = new Set(p.progress || []);
  const steps = g.steps || [];
  const pct = steps.length ? Math.round((done.size / steps.length) * 100) : 0;
  const missingTools = (g.tools || []).filter((t) => !ownsTool(t.name)).map((t) => t.name);
  const list = (arr) => (arr && arr.length ? `<ul>${arr.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");
  const vids = p.videos || {};
  const techs = Object.keys(vids);
  const haveVideos = techs.some((t) => vids[t].length);
  // first video of each technique in a step, max 2 per step
  const stepVideos = (s) => [...new Set((s.techniques || []).map(normTech))].map((t) => vids[t]?.[0]).filter(Boolean).slice(0, 2);

  pane.innerHTML = `
    <p class="md" style="font-size:1.08rem">${esc(g.summary)}</p>
    <dl class="facts">
      <div><dt>Level</dt><dd>${esc(g.difficulty)}</dd></div>
      <div><dt>Time</dt><dd>${esc(g.time_estimate)}</dd></div>
      ${g.finished_size ? `<div><dt>Finished size</dt><dd>${esc(g.finished_size)}</dd></div>` : ""}
      <div><dt>Tools you still need</dt><dd>${missingTools.length}</dd></div>
    </dl>
    ${g.difficulty_reason ? `<p class="muted">${esc(g.difficulty_reason)}</p>` : ""}
    ${g.skills_learned?.length ? `<p><strong>You'll practise:</strong> ${g.skills_learned.map(esc).join(", ")}</p>` : ""}
    <p><button class="btn" id="shop">Find where to buy what I need</button></p>

    ${g.before_you_start ? `<div class="section"><h2>Before you start</h2><div class="md">${md(g.before_you_start)}</div></div>` : ""}

    <div class="section"><h2>Leather</h2>
      <div class="table-wrap"><table class="spec"><thead><tr><th>Parts</th><th>Leather</th><th>Thickness</th><th>Why</th></tr></thead><tbody>
      ${(g.leather || []).map((l) => `<tr><td><strong>${esc(l.parts)}</strong></td><td>${esc(l.leather)}${l.alternative ? `<div class="muted small">Or: ${esc(l.alternative)}</div>` : ""}</td>
        <td class="thick">${esc(l.thickness_mm)}${/mm/i.test(l.thickness_mm || "") ? "" : " mm"}${l.thickness_oz ? `<div class="muted small">${esc(l.thickness_oz)}${/oz/i.test(l.thickness_oz) ? "" : " oz"}</div>` : ""}</td><td>${esc(l.why)}</td></tr>`).join("")}
      </tbody></table></div>
      ${g.leather_amount ? `<p style="margin-top:10px"><strong>How much to buy:</strong> ${esc(g.leather_amount)}</p>` : ""}
    </div>

    <div class="section"><h2>Tools</h2>
      <p class="muted small">Tick what you own. It's saved to your toolkit, so every guide knows.</p>
      <ul class="toollist">${(g.tools || []).map((t, i) => {
        const have = ownsTool(t.name);
        return `<li><label class="own ${have ? "have" : ""}"><input type="checkbox" data-tool="${i}" ${have ? "checked" : ""}>${have ? "Have it" : "Need it"}</label>
          <div class="name">${esc(t.name)}${t.essential ? `<span class="badge-ess">essential</span>` : ""}</div>
          <div class="why">${esc(t.purpose)}${t.substitute ? ` <br><em>No ${esc(t.name.toLowerCase())}?</em> ${esc(t.substitute)}` : ""}</div></li>`;
      }).join("")}</ul></div>

    ${(g.hardware?.length || g.consumables?.length) ? `<div class="section"><h2>Hardware, thread and finishing</h2>
      <table class="spec"><tbody>
      ${(g.hardware || []).map((h) => `<tr><td><strong>${esc(h.item)}</strong></td><td>${esc([h.quantity, h.size].filter(Boolean).join(" · "))}</td><td class="muted">${esc(h.notes || "")}</td></tr>`).join("")}
      ${(g.consumables || []).map((c) => `<tr><td><strong>${esc(c.item)}</strong></td><td>${esc(c.spec || "")}</td><td class="muted">${esc(c.notes || "")}</td></tr>`).join("")}
      </tbody></table></div>` : ""}

    ${g.practice_first ? `<div class="section"><h2>Practise on scrap first</h2><div class="md">${md(g.practice_first)}</div></div>` : ""}

    ${techs.length ? `<div class="section" id="videos"><h2>Watch how it's done</h2>
      ${haveVideos ? `<p class="muted small">Video tutorials for the techniques in this pattern. Click a picture to play it here.</p>
        <div class="videos">${techs.filter((t) => vids[t]?.length).flatMap((t) => vids[t].map((v) => videoCard(v, false, cap(t)))).join("")}</div>
        ${techs.some((t) => !vids[t]?.length) ? `<p class="muted small">No good video found yet for: ${techs.filter((t) => !vids[t]?.length).map(esc).join(", ")}.</p>` : ""}
        <p><button class="btn quiet" id="vid-refresh">Search YouTube again</button> <span class="muted small" id="vid-status"></span></p>`
      : `<p>This pattern uses ${techs.map(esc).join(", ")}. Find beginner video tutorials for each on YouTube.</p>
        <p><button class="btn" id="vid-find">Find technique videos</button> <span class="muted small" id="vid-status"></span></p>`}
    </div>` : ""}

    <div class="section"><h2>Steps</h2>
      <div class="progress" aria-label="${pct}% done"><div style="width:${pct}%"></div></div>
      ${steps.map((s, i) => `<details class="step ${done.has(i) ? "done" : ""}" ${!done.has(i) && i === firstOpen(steps, done) ? "open" : ""}>
        <summary><span class="num">${i + 1}</span><span class="st">${esc(s.title)}</span>
          <label class="check" onclick="event.stopPropagation()"><input type="checkbox" data-step="${i}" ${done.has(i) ? "checked" : ""}> Done</label></summary>
        <div class="inner">
          ${s.pattern_says ? `<div class="says">The pattern says: ${esc(s.pattern_says)}</div>` : ""}
          <div class="md">${md(s.how_to)}</div>
          ${s.tips?.length ? `<div class="callout tip"><strong>Tips</strong>${list(s.tips)}</div>` : ""}
          ${s.watch_out?.length ? `<div class="callout warn"><strong>Watch out</strong>${list(s.watch_out)}</div>` : ""}
          ${s.tools_used?.length ? `<p class="small muted">Tools: ${s.tools_used.map(esc).join(", ")}</p>` : ""}
          ${stepVideos(s).length ? `<div class="step-videos"><strong class="small">Watch:</strong><div class="videos">${stepVideos(s).map((v) => videoCard(v, true)).join("")}</div></div>` : ""}
          <div class="actions">
            <button class="btn" data-ask="${i}">Explain this step differently</button>
            ${(s.techniques || []).filter((t) => !vids[normTech(t)]?.length).slice(0, 2).map((t) => `<button class="btn quiet" data-video="${esc(t)}">Ask for a video: ${esc(t)}</button>`).join("")}
          </div>
        </div></details>`).join("")}
    </div>

    ${g.unclear_points?.length ? `<div class="section"><h2>Where the pattern is vague</h2>${list(g.unclear_points)}</div>` : ""}
    ${g.finishing_and_care ? `<div class="section"><h2>Finishing and care</h2><div class="md">${md(g.finishing_and_care)}</div></div>` : ""}
    <p class="muted small">Written by ${esc(p.guide_model || "Claude")} ${p.guide_at ? esc(ago(p.guide_at)) : ""}. <button class="btn quiet" id="regen">Write it again</button></p>`;

  bindVideos(pane);
  $("#vid-find", pane)?.addEventListener("click", (e) => { e.target.disabled = true; startVideoSearch(p, false, $("#vid-status", pane)); });
  $("#vid-refresh", pane)?.addEventListener("click", (e) => { e.target.disabled = true; startVideoSearch(p, true, $("#vid-status", pane)); });

  // step checkboxes
  $$("[data-step]", pane).forEach((c) => c.addEventListener("change", async () => {
    const i = +c.dataset.step;
    c.checked ? done.add(i) : done.delete(i);
    const res = await api(`/api/patterns/${p.id}`, { method: "PATCH", json: { progress: [...done], ...(p.status === "" ? { status: "in_progress" } : {}) } });
    Object.assign(p, { progress: res.progress, status: res.status });
    if (res.status && $("#status")) $("#status").value = res.status;
    renderGuide(pane, p);
  }));
  // toolkit
  $$("[data-tool]", pane).forEach((c) => c.addEventListener("change", async () => {
    const name = g.tools[+c.dataset.tool].name;
    let kit = state.settings.toolkit || [];
    kit = c.checked ? [...kit, name] : kit.filter((t) => { const o = norm(t), n = norm(name); return !(n === o || n.includes(o) || o.includes(n)); });
    state.settings = await api("/api/settings", { method: "PUT", json: { toolkit: kit } });
    renderGuide(pane, p);
  }));
  $$("[data-ask]", pane).forEach((b) => b.addEventListener("click", () => {
    const s = steps[+b.dataset.ask];
    current.showTab("ask", { prefill: `I'm on step ${+b.dataset.ask + 1} (“${s.title}”). Can you explain it differently, in smaller steps? What should it look like when I've done it right?` });
  }));
  $$("[data-video]", pane).forEach((b) => b.addEventListener("click", () => {
    current.showTab("ask", { prefill: `Find me 2–3 good video tutorials that show ${b.dataset.video} for a beginner, and tell me what to watch for in each.`, send: true });
  }));
  $("#shop").addEventListener("click", () => {
    const need = missingTools.length ? ` Tools I don't own yet: ${missingTools.join(", ")}.` : "";
    current.showTab("ask", { prefill: `Make me a shopping list for this pattern: the leather, hardware, thread and finishing products${need ? " plus the tools I'm missing" : ""}. Find shops that ship to me, with rough prices.${need}`, send: true });
  });
  $("#regen").addEventListener("click", async () => {
    await api(`/api/patterns/${p.id}/guide`, { method: "POST" });
    p.guide = null;
    renderGuide(pane, p);
  });
}
/* ------------------------------------------------------------------ videos */
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const normTech = (t) => t.toLowerCase().replace(/[^a-z0-9 /&+-]/g, " ").replace(/\s+/g, " ").trim();

function videoCard(v, compact = false, label = "") {
  return `<div class="video ${compact ? "compact" : ""}">${label ? `<div class="vlabel">${esc(label)}</div>` : ""}
    <button class="vthumb" data-yt="${esc(v.video_id)}" aria-label="Play ${esc(v.title)}">
      <img loading="lazy" src="https://i.ytimg.com/vi/${esc(v.video_id)}/mqdefault.jpg" alt=""><span class="play" aria-hidden="true"></span></button>
    <div class="vmeta"><a href="${esc(v.url)}" target="_blank" rel="noopener">${esc(v.title)}</a>
      ${v.channel ? `<div class="muted small">${esc(v.channel)}</div>` : ""}
      ${!compact && v.why ? `<div class="small">${esc(v.why)}</div>` : ""}</div></div>`;
}

function bindVideos(root) {
  $$("[data-yt]", root).forEach((b) => b.addEventListener("click", () => {
    const f = document.createElement("iframe");
    f.src = `https://www.youtube-nocookie.com/embed/${b.dataset.yt}?autoplay=1&rel=0`;
    f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
    f.allowFullscreen = true;
    f.title = "YouTube video";
    f.className = "vframe";
    b.replaceWith(f);
  }));
}

async function startVideoSearch(p, refresh, statusEl) {
  try {
    const job = await api(`/api/patterns/${p.id}/videos${refresh ? "?refresh=true" : ""}`, { method: "POST" });
    await pollJob(job, (j) => { if (statusEl && j.log.length) statusEl.innerHTML = `<span class="spinner"></span> ${esc(j.log[j.log.length - 1])}`; });
    if (current?.id === p.id) renderPattern(p.id, "guide");
  } catch (e) { if (statusEl) statusEl.textContent = e.message; }
}

function firstOpen(steps, done) { for (let i = 0; i < steps.length; i++) if (!done.has(i)) return i; return -1; }

/* ------------------------------------------------------------------ chat */
const PATTERN_STARTERS = [
  "I'm a complete beginner. What should I practise before starting this one?",
  "Which parts of this pattern are the hardest, and how do I get them right?",
  "Can I make this with thinner or cheaper leather?",
  "What can I make if I don't have all the hardware?",
];
const GENERAL_STARTERS = [
  "Which pattern in my library should I make first, and why?",
  "Teach me the saddle stitch, step by step",
  "How do I get smooth, burnished edges?",
  "Explain leather thickness: oz vs mm, and what to use for what",
  "What's the minimum toolkit I need to start?",
  "Where can I buy veg-tan leather near me?",
];

async function renderChat(pane, { patternId = null, prefill = "", send = false, chatId = null } = {}) {
  const chats = await api(`/api/chats${patternId ? `?pattern_id=${patternId}` : ""}`);
  let active = chatId ?? (prefill ? null : chats[0]?.id ?? null);
  pane.innerHTML = `<div class="chat ${chats.length ? "" : "solo"}">
    ${chats.length ? `<div class="chat-list" id="chat-list"><button data-chat="" class="${active ? "" : "on"}">+ New question</button>
      ${chats.map((c) => `<button data-chat="${c.id}" class="${c.id === active ? "on" : ""}" title="${esc(c.title)}">${esc(c.title)}</button>`).join("")}</div>` : ""}
    <div>
      <div class="thread" id="thread"></div>
      <div class="composer">
        <textarea id="msg" placeholder="${patternId ? "Ask anything about this pattern, or add a photo of your work for feedback" : "Ask about techniques, tools, leather, or what to make next"}"></textarea>
        <div class="row">
          <label class="btn quiet" style="margin:0;font-weight:400">Add photo<input type="file" id="photo" accept="image/*" multiple hidden></label>
          <div class="thumbs" id="thumbs"></div><span class="spacer"></span>
          ${active ? `<button class="btn quiet" id="del">Delete chat</button>` : ""}
          <button class="btn primary" id="send">Ask</button>
        </div>
      </div>
    </div></div>`;

  const thread = $("#thread", pane);
  const starters = patternId ? PATTERN_STARTERS : GENERAL_STARTERS;
  const showStarters = () => {
    thread.innerHTML = `<div><p class="muted">${patternId ? "The Awlchemist has this pattern open on the bench, plus the build guide if you made one." : "The Awlchemist knows your library, your toolkit and your level."} Ask anything, or start with:</p>
      <div class="starters">${starters.map((s) => `<button>${esc(s)}</button>`).join("")}</div></div>`;
    $$(".starters button", thread).forEach((b) => b.addEventListener("click", () => { $("#msg", pane).value = b.textContent; sendMsg(); }));
  };
  const msgHtml = (m) => m.role === "user"
    ? `<div class="msg user">${m.photos?.length ? `<div class="photos">${m.photos.map((f) => `<img src="${asset(`/photos/${f}`)}" alt="Your photo">`).join("")}</div>` : ""}${esc(m.text)}</div>`
    : `<div class="msg assistant"><div class="md">${md(m.text)}</div>${sourcesHtml(m.sources)}</div>`;

  if (active) {
    const c = await api(`/api/chats/${active}`);
    thread.innerHTML = c.messages.map(msgHtml).join("");
  } else showStarters();

  $$("#chat-list button", pane).forEach((b) => b.addEventListener("click", () => renderChat(pane, { patternId, chatId: b.dataset.chat ? +b.dataset.chat : null, prefill: b.dataset.chat ? "" : " " })));
  $("#del", pane)?.addEventListener("click", async () => {
    await api(`/api/chats/${active}`, { method: "DELETE" });
    renderChat(pane, { patternId });
  });

  let photos = [];
  $("#photo", pane).addEventListener("change", (e) => {
    photos = [...photos, ...e.target.files].slice(0, 4);
    $("#thumbs", pane).innerHTML = photos.map((f) => `<img src="${URL.createObjectURL(f)}" alt="">`).join("");
  });
  const box = $("#msg", pane);
  box.value = prefill.trim();
  box.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) sendMsg(); });
  $("#send", pane).addEventListener("click", sendMsg);

  async function sendMsg() {
    const text = box.value.trim();
    if (!text) return box.focus();
    $("#send", pane).disabled = true;
    const isNew = !active;
    if (!active) {
      const { id } = await api("/api/chats", { json: { pattern_id: patternId, title: text.slice(0, 80) } });
      active = id;
      thread.innerHTML = "";
    }
    thread.insertAdjacentHTML("beforeend", msgHtml({ role: "user", text, photos: [] }));
    if (photos.length) {
      const last = thread.lastElementChild;
      last.insertAdjacentHTML("afterbegin", `<div class="photos">${photos.map((f) => `<img src="${URL.createObjectURL(f)}" alt="">`).join("")}</div>`);
    }
    const out = document.createElement("div");
    out.className = "msg assistant";
    out.innerHTML = `<div class="status"></div><div class="md typing"></div>`;
    thread.appendChild(out);
    out.scrollIntoView({ block: "end", behavior: "smooth" });

    const fd = new FormData();
    fd.append("text", text);
    photos.forEach((f) => fd.append("photos", f));
    box.value = ""; photos = []; $("#thumbs", pane).innerHTML = "";

    let acc = "";
    try {
      const res = await request(`/api/chats/${active}/message`, { method: "POST", body: fd });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const line = buf.slice(0, idx).replace(/^data: /, "");
          buf = buf.slice(idx + 2);
          if (!line) continue;
          const ev = JSON.parse(line);
          if (ev.type === "text") { acc += ev.text; $(".md", out).innerHTML = md(acc); }
          else if (ev.type === "status") $(".status", out).textContent = ev.text;
          else if (ev.type === "error") { out.classList.add("error"); $(".md", out).textContent = ev.text; }
          else if (ev.type === "done") { $(".status", out).remove(); out.insertAdjacentHTML("beforeend", sourcesHtml(ev.sources)); }
        }
      }
    } catch (e) {
      out.classList.add("error");
      $(".md", out).textContent = e.message;
    }
    $(".md", out)?.classList.remove("typing");
    $("#send", pane).disabled = false;
    if (isNew) renderChat(pane, { patternId, chatId: active });
  }
  if (send && prefill.trim()) sendMsg();
}

function sourcesHtml(sources) {
  if (!sources?.length) return "";
  return `<div class="sources"><strong>Sources</strong>${sources.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join("")}</div>`;
}

/* ------------------------------------------------------------------ learn */
async function renderLearn() {
  const [guides, videos] = await Promise.all([api("/api/patterns?kind=guide"), api("/api/videos")]);
  const techs = Object.keys(videos).filter((t) => videos[t].length);
  app.innerHTML = `<div class="page"><div class="learn">
    <section><h1>Learn</h1>
      <p class="muted">Ask the Awlchemist about anything that isn't one specific pattern: techniques, tools, buying leather, and what to make next.</p>
      <div id="learn-chat"></div></section>
    <aside>
      <h3>Guide books in your library</h3>
      <div class="guides-list">${guides.length ? guides.map((g) => `<a href="#/p/${g.id}/text"><img src="${asset(`/api/patterns/${g.id}/cover`)}" alt="" loading="lazy"><span>${esc(g.title)}</span></a>`).join("") : `<p class="muted small">None yet. They arrive with the next sync.</p>`}</div>
      <h3>Technique videos</h3>
      ${techs.length ? techs.map((t) => `<details class="tech-videos"><summary>${esc(cap(t))} <span class="muted small">(${videos[t].length})</span></summary>
        <div class="videos">${videos[t].map((v) => videoCard(v, true)).join("")}</div></details>`).join("")
        : `<p class="muted small">Videos collect here as you write build guides: every technique a pattern uses gets its tutorials.</p>`}
    </aside></div></div>`;
  bindVideos(app);
  renderChat($("#learn-chat"), {});
}

/* ------------------------------------------------------------------ settings */
async function renderSettings() {
  const s = await loadSettings();
  if (!state.stats) await refreshStats();
  app.innerHTML = `<div class="page settings"><h1>Settings</h1>
    <fieldset><legend>The Awlchemist (your teacher)</legend>
      <p class="small">The Awlchemist runs on <strong>Claude Code</strong> on this computer and uses the Claude account you're signed in with there. No API key needed.</p>
      <p class="hint">Claude Code: <code>${esc(state.stats.claude?.cli || "not found")}</code>. Not signed in yet? Open a terminal, run <code>claude</code> and type <code>/login</code>.</p>
      <p><button class="btn" id="cc-check">Test the connection</button> <span class="muted small" id="cc-status"></span></p>
      <label for="model">Model</label>
      <select id="model">${s.models.map((m) => `<option ${m === s.model ? "selected" : ""}>${m}</option>`).join("")}</select>
      <div class="hint">Sonnet is a good balance. Opus writes the most careful guides but uses your plan's limits fastest; Haiku uses the least.</div>
    </fieldset>
    <fieldset><legend>About you</legend>
      <label for="exp">Experience</label>
      <select id="exp">${["complete beginner", "made a few small pieces", "comfortable with the basics", "experienced"].map((x) => `<option ${x === s.experience ? "selected" : ""}>${x}</option>`).join("")}</select>
      <label for="country">Country for shopping</label>
      <input type="text" id="country" value="${esc(s.country)}" maxlength="2" style="max-width:90px">
      <div class="hint">Two-letter code, e.g. NL. The Awlchemist looks for shops that ship there.</div>
      <label for="currency">Currency</label>
      <input type="text" id="currency" value="${esc(s.currency)}" style="max-width:110px">
      <label for="about">Anything else the Awlchemist should know</label>
      <textarea id="about" placeholder="e.g. I have a small desk to work at; I'd like to make gifts">${esc(s.about_me)}</textarea>
    </fieldset>
    <fieldset><legend>My toolkit</legend>
      <p class="muted small">Guides mark these as “Have it”. Tools you tick in a guide are added here too.</p>
      <div style="display:flex;gap:8px"><input type="text" id="tool-new" placeholder="Add a tool, e.g. 4 mm diamond stitching chisel"><button class="btn" id="tool-add">Add</button></div>
      <div class="toolkit-edit" id="kit"></div>
    </fieldset>
    <fieldset><legend>Pattern library</legend>
      <h3 style="margin-top:0">Pattern sources</h3>
      <p class="muted small">Where your patterns live. Each source is copied into its own folder in the library, and later checks only fetch new files.</p>
      <div id="src-list"></div>
      <label for="src-name">Add a source</label>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <input type="text" id="src-name" placeholder="Name, e.g. My patterns" style="max-width:200px">
        <input type="text" id="src-loc" placeholder="Shared Google Drive folder link, or a folder like D:\\Patterns" style="flex:1;min-width:220px">
        <button class="btn" id="src-add">Add</button>
      </div>
      <div class="hint">Google Drive folders must be shared as “Anyone with the link”. No Google login is used.</div>
      <label style="font-weight:400;display:flex;gap:8px;align-items:center"><input type="checkbox" id="auto" ${s.auto_sync_on_start ? "checked" : ""}> Check for new patterns when the app starts (at most once a day)</label>
      <p class="hint">Files are kept in <code>${esc(state.stats.library_path)}</code>. Copy PDFs in there by hand if you like, then use “Re-scan”.</p>
      <p><button class="btn" id="rescan">Re-scan the library folder</button></p>
    </fieldset>
    <p><button class="btn primary" id="save">Save settings</button></p></div>`;

  let kit = [...(s.toolkit || [])];
  const drawKit = () => {
    $("#kit").innerHTML = kit.length ? kit.map((t, i) => `<span>${esc(t)}<button data-rm="${i}" aria-label="Remove ${esc(t)}">×</button></span>`).join("") : `<span class="muted">Nothing yet</span>`;
    $$("[data-rm]").forEach((b) => b.addEventListener("click", () => { kit.splice(+b.dataset.rm, 1); drawKit(); }));
  };
  drawKit();
  const addTool = () => { const v = $("#tool-new").value.trim(); if (v) { kit.push(v); $("#tool-new").value = ""; drawKit(); } };
  $("#tool-add").addEventListener("click", addTool);
  $("#tool-new").addEventListener("keydown", (e) => { if (e.key === "Enter") addTool(); });
  $("#cc-check").addEventListener("click", async () => {
    $("#cc-status").innerHTML = `<span class="spinner"></span> Asking Claude Code…`;
    try { await api("/api/claude/check", { method: "POST" }); $("#cc-status").textContent = "Connected and signed in."; }
    catch (e) { $("#cc-status").textContent = e.message; }
  });
  const drawSources = (list) => {
    $("#src-list").innerHTML = list.length
      ? list.map((x, i) => `<div class="toolkit-edit" style="margin:4px 0"><span><strong>${esc(x.name)}</strong>&nbsp;<span class="muted small">${x.kind === "gdrive" ? "Google Drive" : "Folder"} · ${plural(x.patterns || 0, "pattern")} · ${esc(x.location)}</span><button data-src="${i}" aria-label="Remove ${esc(x.name)}">×</button></span></div>`).join("")
      : `<p class="muted small">No sources yet.</p>`;
    $$("[data-src]").forEach((b) => b.addEventListener("click", () => removeSourceDialog(list[+b.dataset.src], drawSources)));
  };
  api("/api/sources").then(drawSources);
  $("#src-add").addEventListener("click", async () => {
    try {
      await api("/api/sources", { json: { name: $("#src-name").value, location: $("#src-loc").value } });
      $("#src-name").value = ""; $("#src-loc").value = "";
      drawSources(await api("/api/sources"));
      refreshStats();
      toast("Source added. Fetching its patterns…");
    } catch (e) { toast(e.message, 6000); }
  });
  $("#rescan").addEventListener("click", async () => { await api("/api/reindex", { method: "POST" }); refreshStats(); toast("Re-scanning the library…"); });
  $("#save").addEventListener("click", async () => {
    state.settings = await api("/api/settings", { method: "PUT", json: {
      model: $("#model").value, experience: $("#exp").value,
      country: $("#country").value.toUpperCase(), currency: $("#currency").value, about_me: $("#about").value,
      toolkit: kit, auto_sync_on_start: $("#auto").checked,
    } });
    await refreshStats();
    toast("Settings saved");
    renderSettings();
  });
}

/* Removing a source: keep what it brought in, or take its patterns out of the library too. */
function removeSourceDialog(src, redraw) {
  const bg = document.createElement("div");
  bg.className = "modal-bg";
  bg.innerHTML = `<div class="modal" role="dialog" aria-label="Remove a source">
    <button class="btn quiet close" aria-label="Close">✕</button>
    <h2>Remove “${esc(src.name)}”?</h2>
    <p>Awlchemy stops checking this source for new patterns. What should happen to the ${plural(src.patterns || 0, "pattern")} it already brought in?</p>
    <p class="choices"><button class="btn" id="rm-keep">Keep them in my library</button>
      <button class="btn danger" id="rm-all">Delete them too</button></p>
    <p class="muted small">Deleting removes this source's folder from your library on this computer. Patterns you wrote notes or a build guide for keep those. ${src.kind === "folder" ? "The original folder is not touched." : "Nothing changes on Google Drive."}</p>
  </div>`;
  document.body.appendChild(bg);
  const close = () => bg.remove();
  $(".close", bg).onclick = close;
  bg.addEventListener("click", (e) => { if (e.target === bg) close(); });
  const go = async (del) => {
    $$("button", bg).forEach((b) => { b.disabled = true; });
    try {
      const r = await api(`/api/sources/${encodeURIComponent(src.name)}${del ? "?delete_files=true" : ""}`, { method: "DELETE" });
      toast(del ? `Removed, along with ${plural(r.removed || 0, "pattern file")}.` : "Removed. Its patterns stay in your library.");
      redraw(r.sources);
      refreshStats();
    } catch (e) { toast(e.message, 6000); }
    close();
  };
  $("#rm-keep", bg).onclick = () => go(false);
  $("#rm-all", bg).onclick = () => go(true);
}

/* ------------------------------------------------------------------ boot */
(async () => {
  await Promise.all([refreshStats(), loadSettings()]);
  render();
  setInterval(() => { if (!syncWatching) refreshStats(); }, 30000);
})();
