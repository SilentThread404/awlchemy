// Runs demo/demo.js under Node and walks through the API calls the frontend makes.
// Usage: node tests/demo_smoke.mjs <path to demo.js> <path to app.js>
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const [demoPath, appPath] = process.argv.slice(2);
globalThis.window = globalThis;
new Function(readFileSync(demoPath, "utf8"))();
const demo = globalThis.AWLCHEMY_DEMO;
const call = async (path, init) => {
  const res = await demo.fetch(path, init);
  return { status: res.status, body: await res.json() };
};
const json = (method, body) => ({ method, body: JSON.stringify(body) });
const ok = async (path, init) => {
  const r = await call(path, init);
  assert.equal(r.status, 200, `${path}: ${JSON.stringify(r.body)}`);
  return r.body;
};

// Every fixed /api path in app.js must be answered by the demo (a 404 would mean the two drifted apart).
const app = readFileSync(appPath, "utf8");
const paths = new Set([...app.matchAll(/["'`](\/api\/[a-z/]+)["'`?$]/g)].map((m) => m[1].replace(/\/$/, "")));
assert.ok(paths.size >= 8, "found the API paths in app.js");
const PREFIXES = ["/api/patterns", "/api/chats", "/api/jobs", "/api/sources"]; // need an id or a body; covered below
for (const p of paths) {
  if (PREFIXES.includes(p)) continue;
  const r = await call(p, { method: /sync|reindex|check|import/.test(p) ? "POST" : "GET" });
  assert.notEqual(r.status, 404, `the demo has no answer for ${p}`);
  assert.notEqual(r.status, 500, `${p} crashed: ${r.body.detail}`);
}

const stats = await ok("/api/stats");
assert.ok(stats.total >= 12 && stats.sources.length === 2);
const lib = stats.library_job || (await ok("/api/sync", { method: "POST" }));
assert.ok(["listing", "downloading", "indexing"].includes(lib.progress.phase)); // what the sync panel draws

const all = await ok("/api/patterns?kind=pattern");
assert.ok(all.every((p) => p.kind === "pattern" && !("guide" in p)));
assert.deepEqual((await ok("/api/patterns?q=wallet&kind=pattern&difficulty=Medium")).map((p) => p.title), ["Bifold Wallet"]);
assert.equal((await ok("/api/patterns?status=in_progress&kind=")).length, 1);

const holder = await ok("/api/patterns/2");
assert.equal(holder.guide.steps.length, 7);
assert.deepEqual(holder.prints.map((v) => v.paper), ["A4", "Letter"]);
assert.ok(Object.keys(holder.videos).includes("saddle stitch"));
for (const step of holder.guide.steps) assert.ok(step.title && step.how_to);
assert.ok((await ok("/api/patterns/2/markdown")).markdown.includes("## Parts"));
assert.equal((await ok("/api/patterns/2", json("PATCH", { progress: [2, 0, 2], title: "My holder", difficulty: "" }))).difficulty, null);
assert.deepEqual((await ok("/api/patterns/2")).progress, [0, 2]);
assert.equal((await call("/api/patterns/999")).status, 404);

// the drawings are complete SVG documents with no broken numbers in them
for (const p of await ok("/api/patterns?kind=")) {
  const drawings = [demo.svg.cover(p.id), ...Array.from({ length: p.pages }, (_, n) => demo.svg.page(p.id, n))];
  for (const svg of drawings) {
    assert.match(svg, /^<svg[\s\S]+<\/svg>$/);
    assert.ok(!/NaN|undefined|Infinity/.test(svg), p.title);
  }
}

// jobs: the key fob's guide gets "written"
const job = await ok("/api/patterns/1/guide", { method: "POST" });
assert.equal(job.status, "running");
assert.equal((await ok("/api/patterns/1/guide-job")).id, job.id);
assert.equal((await ok(`/api/jobs/${job.id}`)).kind, "guide");

// chat: a streamed, pre-written answer that links to patterns and never to the web
const { id } = await ok("/api/chats", json("POST", { pattern_id: null, title: "first" }));
const form = new FormData();
form.set("text", "Which pattern in my library should I make first, and why?");
const res = await demo.fetch(`/api/chats/${id}/message`, { method: "POST", body: form });
const events = (await res.text()).split("\n\n").filter(Boolean).map((l) => JSON.parse(l.replace(/^data: /, "")));
assert.equal(events.at(-1).type, "done");
const text = events.filter((e) => e.type === "text").map((e) => e.text).join("");
assert.ok(text.includes("(#1)") && !/https?:\/\//.test(text));
assert.equal((await ok(`/api/chats/${id}`)).messages.length, 2);
assert.equal((await ok("/api/chats")).length, 1);

// sources
assert.equal((await call("/api/sources", json("POST", { name: "x", location: "y" }))).status, 400);
const left = await ok("/api/sources/My%20own%20designs?delete_files=true", { method: "DELETE" });
assert.equal(left.sources.length, 1);
assert.equal(left.removed, 3);

console.log("demo ok");
process.exit(0);
