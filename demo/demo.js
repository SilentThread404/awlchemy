/* Awlchemy demo: a stand-in for the server, so the real frontend (awlchemy/static/app.js) can run
   as a static page, e.g. on GitHub Pages.

   Everything here is made up for the demo: the patterns, their drawings, the build guides and
   the Awlchemist's answers. No real pattern, seller or web link is included, nothing is sent
   anywhere, and changes last until the page is reloaded.

   app.js looks for window.AWLCHEMY_DEMO and, when it's there, calls
     fetch(path, init)  instead of the browser's fetch for every /api/... request
     asset(path)        to turn a picture or file path into something an <img> or link can open
*/
"use strict";

(() => {
  const REPO = "https://github.com/SilentThread404/awlchemy";
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const nowIso = () => new Date().toISOString();
  const hoursAgo = (h) => new Date(Date.now() - h * 3600e3).toISOString();
  const xml = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* ---------------------------------------------------------------- the made-up library */
  const SRC_A = "Workshop samples", SRC_B = "My own designs";
  const LEATHER = { tan: "#c8955c", natural: "#d9b38a", chestnut: "#8a4f2a", brown: "#5a3520", oxblood: "#7a2e2a", olive: "#6b6a3a", navy: "#2f3e55", black: "#3a2a22" };

  // [id, title, collection, difficulty, source, drawing, colour, parts [name, w mm, h mm, how many], hardware, paper sizes]
  const ROWS = [
    [1, "Key Fob", "Key rings", "Easy", SRC_A, "keyfob", "tan", [["A Body", 40, 80, 2], ["B Strap", 20, 110, 1]], ["Split key ring, 30 mm"], []],
    [2, "Card Holder", "Wallets and card holders", "Easy", SRC_A, "cardholder", "chestnut", [["A Body", 100, 72, 2], ["B Pocket", 100, 50, 2]], [], ["A4", "Letter"]],
    [3, "Bifold Wallet", "Wallets and card holders", "Medium", SRC_A, "wallet", "brown", [["A Outer", 230, 95, 1], ["B Lining", 225, 95, 1], ["C Card pocket", 105, 55, 4], ["D Pocket base", 105, 90, 2]], [], ["A4", "Letter"]],
    [4, "Coin Pouch", "Small goods", "Easy", SRC_A, "pouch", "oxblood", [["A Back and flap", 90, 150, 1], ["B Front", 90, 80, 1], ["C Gusset", 25, 200, 1]], ["Line 20 snap"], []],
    [5, "Watch Strap", "Small goods", "Medium", SRC_A, "strap", "black", [["A Long strap", 20, 125, 2], ["B Buckle strap", 20, 85, 2], ["C Keeper", 8, 60, 2]], ["Buckle, 18 mm", "Spring bars, 20 mm, 2 pieces"], []],
    [6, "Passport Cover", "Travel", "Easy", SRC_A, "passport", "navy", [["A Cover", 200, 140, 1], ["B Pocket", 65, 140, 2]], [], []],
    [7, "Notebook Cover", "Travel", "Medium", SRC_A, "notebook", "olive", [["A Cover", 330, 220, 1], ["B Sleeve", 80, 220, 2], ["C Pen loop", 25, 60, 1]], ["Elastic cord, 2 mm"], ["A4", "Letter"]],
    [8, "Dress Belt", "Belts", "Medium", SRC_A, "belt", "brown", [["A Strap", 38, 1150, 1], ["B Keeper", 15, 110, 1]], ["Buckle, 38 mm", "Chicago screws, 2 pieces"], ["A4", "Letter", "A1"]],
    [9, "Glasses Case", "Small goods", "Medium", SRC_A, "glasses", "tan", [["A Body", 170, 160, 1], ["B End cap", 40, 70, 1]], [], []],
    [10, "Tote Bag", "Bags", "Hard", SRC_B, "tote", "natural", [["A Body panel", 380, 340, 2], ["B Base", 380, 120, 1], ["C Handle", 30, 600, 2], ["D Inner pocket", 180, 150, 1]], ["Rivets, 9 mm, 8 pieces"], ["A4", "Letter", "A1"]],
    [11, "Sling Bag", "Bags", "Hard", SRC_B, "sling", "chestnut", [["A Front", 200, 280, 1], ["B Back", 200, 280, 1], ["C Gusset", 60, 560, 1], ["D Strap", 38, 900, 1]], ["Zip, 25 cm", "D-rings, 38 mm, 2 pieces", "Strap slider, 38 mm"], []],
    [12, "Backpack", "Bags", "Very Hard", SRC_B, "backpack", "brown", [["A Front", 300, 400, 1], ["B Back", 300, 400, 1], ["C Side gusset", 120, 900, 1], ["D Flap", 300, 220, 1], ["E Pocket", 180, 150, 1], ["F Shoulder strap", 50, 700, 2]], ["Buckles, 25 mm, 2 pieces", "D-rings, 25 mm, 4 pieces", "Rivets, 9 mm, 12 pieces"], []],
  ];
  const FOLDER = { Easy: "1. EASY", Medium: "2. MEDIUM", Hard: "3. HARD", "Very Hard": "4. VERY HARD" };

  const patterns = ROWS.map(([id, title, collection, difficulty, source, art, colour, parts, hardware, papers]) => ({
    id, title, collection, difficulty, source, kind: "pattern", art, colour, parts, hardware, papers,
    rel_path: `${source}/${FOLDER[difficulty]}/${collection}/${title}.pdf`,
    pages: 1 + Math.ceil(parts.length / 2), favorite: 0, status: "", notes: "", progress: [],
    guide: null, guide_model: null, guide_at: null, added_at: hoursAgo(24 * 9), coverPage: null,
  }));
  const booklet = (id, title, lines) => ({
    id, title, collection: "BONUS", difficulty: null, source: SRC_A, kind: "guide", art: "book", colour: "natural", parts: [], hardware: [], papers: [],
    rel_path: `${SRC_A}/BONUS/${title}.pdf`, pages: 3, favorite: 0, status: "", notes: "", progress: [],
    guide: null, guide_model: null, guide_at: null, added_at: hoursAgo(24 * 9), coverPage: null, lines,
  });
  patterns.push(
    booklet(13, "The Beginner's Toolkit", ["## What you need to start", "A sharp knife, a steel ruler and a cutting mat cover every cut. Add a wing divider to mark stitch lines, stitching chisels to punch the holes, two blunt needles and waxed thread, and a mallet that isn't metal.", "## What can wait", "An edge beveler, a burnishing tool and a skiving knife make cleaner work, but sandpaper and a scrap of canvas get you through the first projects.", "## Leather for learning", "Buy vegetable-tanned offcuts around 1.2 to 1.6 mm thick. They cut cleanly, hold stitch marks and burnish well, so mistakes are easy to see and fix."]),
    booklet(14, "Reading a Pattern", ["## Lines", "A solid line is a cut line. A dashed line is a stitch line or a fold line; the legend says which. Small circles are holes for hardware.", "## Scale", "Every sheet has a calibration square. Print at 100% and measure it before cutting anything.", "## Part labels", "Parts carry a letter and a count, for example “B Pocket, cut 2”. Mirror a part when the pattern says “cut 1 + 1 mirrored”."]),
  );
  const LUGGAGE_TAG = { // arrives the first time "Check for new patterns" is clicked
    id: 15, title: "Luggage Tag", collection: "Travel", difficulty: "Easy", source: SRC_A, kind: "pattern", art: "keyfob", colour: "oxblood",
    parts: [["A Tag", 65, 110, 2], ["B Strap", 12, 220, 1]], hardware: ["Buckle, 12 mm"], papers: [],
    rel_path: `${SRC_A}/1. EASY/Travel/Luggage Tag.pdf`, pages: 2, favorite: 0, status: "", notes: "", progress: [],
    guide: null, guide_model: null, guide_at: null, added_at: null, coverPage: null,
  };
  const byId = (id) => patterns.find((p) => p.id === +id);

  /* ---------------------------------------------------------------- pattern text (what a seller's PDF says) */
  function patternText(p) {
    if (p.lines) return `# ${p.title}\n\n${p.lines.join("\n\n")}`;
    const parts = p.parts.map(([n, w, h, c]) => `- ${n}: ${w} × ${h} mm, cut ${c}`).join("\n");
    const hw = p.hardware.length ? p.hardware.map((h) => `- ${h}`).join("\n") : "- None";
    return `# ${p.title}\n\nLeather: vegetable tanned. Seam allowance included. Stitch line 3.5 mm from the edge.\n\n## Parts\n\n${parts}\n\n## Hardware\n\n${hw}\n\n## Assembly\n\n1. Print at 100% and check the 20 mm square.\n2. Cut all parts and transfer the marks.\n3. Finish the edges that will be hidden.\n4. Glue, punch and stitch.\n5. Finish the outer edges.\n\n*This text was written for the demo. Like many patterns it says what to do and leaves out how, which is the gap the build guide fills.*`;
  }

  /* ---------------------------------------------------------------- drawings */
  const STITCH = 'fill="none" stroke="#f3e3c8" stroke-width="2.5" stroke-dasharray="7 6" stroke-linecap="round"';
  const BRASS = "#c9a24a";
  function shade(hex, f) {
    const n = parseInt(hex.slice(1), 16);
    const ch = (v) => Math.max(0, Math.min(255, Math.round(v * f)));
    return `rgb(${ch(n >> 16)},${ch((n >> 8) & 255)},${ch(n & 255)})`;
  }
  function item(art, c) {
    const d = shade(c, 0.78), l = shade(c, 1.12);
    switch (art) {
      case "keyfob": return `<circle cx="320" cy="112" r="44" fill="none" stroke="${BRASS}" stroke-width="9"/><rect x="302" y="110" width="36" height="70" rx="6" fill="${d}"/><rect x="250" y="160" width="140" height="232" rx="42" fill="${c}"/><rect x="264" y="174" width="112" height="204" rx="30" ${STITCH}/>`;
      case "cardholder": return `<rect x="150" y="124" width="340" height="240" rx="18" fill="${d}"/><rect x="186" y="140" width="268" height="60" rx="6" fill="#f4eee2"/><path d="M150 205 L490 172 L490 346 Q490 364 472 364 L168 364 Q150 364 150 346 Z" fill="${c}"/><path d="M164 214 L164 350 L476 350 L476 184" ${STITCH}/>`;
      case "wallet": return `<rect x="84" y="136" width="472" height="228" rx="16" fill="${c}"/><rect x="100" y="196" width="204" height="152" rx="6" fill="${d}"/><rect x="336" y="196" width="204" height="152" rx="6" fill="${d}"/><rect x="100" y="236" width="204" height="112" rx="6" fill="${l}"/><rect x="336" y="236" width="204" height="112" rx="6" fill="${l}"/><line x1="320" y1="136" x2="320" y2="364" stroke="${d}" stroke-width="3"/><rect x="94" y="146" width="452" height="208" rx="10" ${STITCH}/>`;
      case "pouch": return `<rect x="196" y="150" width="248" height="220" rx="70" fill="${d}"/><path d="M196 220 Q196 150 266 150 L374 150 Q444 150 444 220 Q444 262 320 282 Q196 262 196 220 Z" fill="${c}"/><path d="M210 222 Q214 166 268 164 L372 164 Q426 166 430 222" ${STITCH}/><circle cx="320" cy="258" r="13" fill="${BRASS}"/>`;
      case "strap": return `<rect x="284" y="52" width="72" height="168" rx="12" fill="${c}"/><rect x="294" y="62" width="52" height="148" rx="6" ${STITCH}/><rect x="272" y="40" width="96" height="34" rx="6" fill="none" stroke="${BRASS}" stroke-width="7"/><path d="M284 262 L356 262 L356 400 L320 436 L284 400 Z" fill="${c}"/><path d="M294 272 L346 272 L346 396 L320 422 L294 396 Z" ${STITCH}/>${[300, 328, 356, 384].map((y) => `<circle cx="320" cy="${y}" r="4.5" fill="#1d1612"/>`).join("")}`;
      case "passport": return `<rect x="196" y="84" width="248" height="330" rx="12" fill="${c}"/><rect x="208" y="96" width="224" height="306" rx="6" ${STITCH}/><circle cx="320" cy="222" r="42" fill="none" stroke="${l}" stroke-width="3"/><ellipse cx="320" cy="222" rx="18" ry="42" fill="none" stroke="${l}" stroke-width="3"/><line x1="278" y1="222" x2="362" y2="222" stroke="${l}" stroke-width="3"/><rect x="262" y="300" width="116" height="10" rx="5" fill="${l}"/>`;
      case "notebook": return `<rect x="176" y="74" width="296" height="340" rx="10" fill="${c}"/><rect x="188" y="86" width="272" height="316" rx="5" ${STITCH}/><rect x="404" y="74" width="14" height="340" fill="#1d1612" opacity=".75"/><rect x="472" y="170" width="20" height="92" rx="9" fill="${d}"/><rect x="478" y="120" width="8" height="180" rx="4" fill="${BRASS}"/>`;
      case "belt": return `<path d="M96 210 L520 210 L560 240 L520 270 L96 270 Z" fill="${c}"/><path d="M108 220 L516 220 L544 240 L516 260 L108 260" ${STITCH}/><rect x="56" y="196" width="72" height="88" rx="8" fill="none" stroke="${BRASS}" stroke-width="9"/><line x1="92" y1="240" x2="150" y2="240" stroke="${BRASS}" stroke-width="6" stroke-linecap="round"/>${[360, 396, 432, 468, 504].map((x) => `<circle cx="${x}" cy="240" r="4.5" fill="#1d1612"/>`).join("")}<rect x="196" y="204" width="20" height="72" rx="4" fill="${d}"/>`;
      case "glasses": return `<rect x="126" y="164" width="388" height="156" rx="78" fill="${c}"/><rect x="140" y="178" width="360" height="128" rx="64" ${STITCH}/><path d="M418 172 Q470 240 418 312" fill="none" stroke="${d}" stroke-width="5"/>`;
      case "tote": return `<path d="M226 190 Q226 76 284 76 Q342 76 342 190" fill="none" stroke="${d}" stroke-width="15"/><path d="M298 190 Q298 76 356 76 Q414 76 414 190" fill="none" stroke="${c}" stroke-width="15"/><path d="M176 184 L464 184 L500 410 L140 410 Z" fill="${c}"/><path d="M190 198 L450 198 L482 396 L158 396 Z" ${STITCH}/>${[232, 296, 348, 408].map((x) => `<circle cx="${x}" cy="206" r="5.5" fill="${BRASS}"/>`).join("")}`;
      case "sling": return `<line x1="120" y1="60" x2="500" y2="430" stroke="${d}" stroke-width="20" stroke-linecap="round"/><rect x="208" y="140" width="224" height="268" rx="56" fill="${c}"/><rect x="222" y="154" width="196" height="240" rx="44" ${STITCH}/><path d="M250 216 L390 216" stroke="${BRASS}" stroke-width="6" stroke-dasharray="3 5"/><rect x="386" y="208" width="26" height="16" rx="4" fill="${BRASS}"/>`;
      case "backpack": return `<path d="M250 110 Q250 56 320 56 Q390 56 390 110" fill="none" stroke="${d}" stroke-width="13"/><rect x="196" y="100" width="248" height="316" rx="62" fill="${c}"/><path d="M196 190 Q196 100 258 100 L382 100 Q444 100 444 190 L444 226 Q320 268 196 226 Z" fill="${d}"/><path d="M210 190 Q212 116 260 114 L380 114 Q428 116 430 190 L430 216 Q320 252 210 216 Z" ${STITCH}/><rect x="238" y="290" width="164" height="96" rx="16" fill="${l}"/><rect x="248" y="300" width="144" height="76" rx="10" ${STITCH}/><rect x="306" y="226" width="28" height="44" rx="6" fill="none" stroke="${BRASS}" stroke-width="6"/>`;
      default: return "";
    }
  }
  const MAT = `<defs><pattern id="g" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="rgba(255,255,255,.09)" stroke-width="1"/></pattern></defs><rect width="640" height="480" fill="#2f5d50"/><rect width="640" height="480" fill="url(#g)"/>`;
  const words = (title, n) => title.split(" ").reduce((rows, w) => {
    if (rows.length && (rows[rows.length - 1] + " " + w).length <= n) rows[rows.length - 1] += " " + w; else rows.push(w);
    return rows;
  }, []);
  // The item on the cutting mat, with a soft shadow under it.
  const onMat = (p) => `${MAT}<g transform="translate(9 12)" opacity=".28">${item(p.art, "#000000").replace(/(fill|stroke)="(?!none)[^"]*"/g, '$1="#000"')}</g>${item(p.art, LEATHER[p.colour])}`;
  function coverSvg(p) {
    if (p.art === "book") {
      const rows = words(p.title, 14);
      return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480">${MAT}<rect x="204" y="60" width="264" height="380" rx="6" fill="#000" opacity=".25"/><rect x="196" y="50" width="264" height="380" rx="6" fill="#f4eee2"/><rect x="196" y="50" width="26" height="380" fill="#c8955c"/><rect x="236" y="66" width="208" height="348" rx="3" fill="none" stroke="#c8955c" stroke-width="2" stroke-dasharray="7 6"/>${rows.map((r, i) => `<text x="340" y="${190 + i * 44}" text-anchor="middle" font-family="Georgia, serif" font-weight="700" font-size="34" fill="#3a2a22">${xml(r)}</text>`).join("")}<text x="340" y="380" text-anchor="middle" font-family="Georgia, serif" font-size="17" fill="#6b3e22">Guide book</text></svg>`;
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480">${onMat(p)}</svg>`;
  }
  const PAGE = (inner, note = "") => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 595 842"><rect width="595" height="842" fill="#fff"/>${inner}<text x="50" y="812" font-family="Helvetica, Arial, sans-serif" font-size="10" fill="#8a8178">${xml(note || "Made-up pattern for the Awlchemy demo")}</text></svg>`;
  const greyLines = (y, n) => Array.from({ length: n }, (_, i) => `<rect x="50" y="${y + i * 19}" width="${i % 5 === 4 ? 300 : 495}" height="7" rx="3" fill="#dcd7cd"/>`).join("");
  function textPage(p, first) {
    const head = `<text x="50" y="76" font-family="Georgia, serif" font-weight="700" font-size="30" fill="#221c18">${xml(p.title)}</text>`;
    if (p.art === "book") return PAGE(head + greyLines(120, first ? 16 : 30) + (first ? `<rect x="50" y="450" width="495" height="2" fill="#c8955c"/>` + greyLines(480, 14) : ""));
    return PAGE(`${head}<svg x="50" y="100" width="495" height="371" viewBox="0 0 640 480">${onMat(p)}</svg>${greyLines(510, 13)}`);
  }
  function sheetPage(p, n, note) {
    const parts = p.parts.slice((n - 1) * 2, n * 2);
    const s = Math.min(2.2, 480 / Math.max(...parts.map((x) => x[1])), 560 / Math.max(...parts.map((x) => x[2])));
    let x = 50, y = 150, row = 0, out = "";
    for (const [name, w, h, count] of parts) {
      const W = w * s, H = h * s;
      if (x + W > 548) { x = 50; y += row + 46; row = 0; }
      const r = Math.min(10, W / 5);
      out += `<rect x="${x}" y="${y}" width="${W}" height="${H}" rx="${r}" fill="none" stroke="#221c18" stroke-width="1.4"/>`;
      if (W > 26 && H > 26) out += `<rect x="${x + 7}" y="${y + 7}" width="${W - 14}" height="${H - 14}" rx="${Math.max(0, r - 4)}" fill="none" stroke="#8a8178" stroke-width="1" stroke-dasharray="3 4"/>`;
      out += `<text x="${x}" y="${y - 8}" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#221c18">${xml(name)} · ${w} × ${h} mm · cut ${count}</text>`;
      x += Math.max(W, 150) + 28; row = Math.max(row, H);
    }
    const square = `<rect x="485" y="50" width="56.7" height="56.7" fill="none" stroke="#221c18" stroke-width="1.2"/><text x="513" y="82" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="10" fill="#221c18">20 mm</text>`;
    const head = `<text x="50" y="72" font-family="Georgia, serif" font-weight="700" font-size="22" fill="#221c18">${xml(p.title)}: pieces, sheet ${n}</text><text x="50" y="92" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#5d544c">Print at 100%. Solid = cut line, dashed = stitch line.</text><text x="50" y="106" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#5d544c">Drawn smaller here to fit the preview.</text>`;
    return PAGE(head + square + out, note);
  }
  const pageSvg = (p, n, note) => (n === 0 || p.art === "book" ? textPage(p, n === 0) : sheetPage(p, Math.min(n, p.pages - 1), note));

  const urls = new Map();
  function svgUrl(key, make) {
    if (!urls.has(key)) urls.set(key, URL.createObjectURL(new Blob([make()], { type: "image/svg+xml" })));
    return urls.get(key);
  }
  const photos = new Map(); // name -> object URL of a photo attached in this session

  function asset(path) {
    let m;
    if ((m = path.match(/^\/api\/patterns\/(\d+)\/cover/))) {
      const p = byId(m[1]);
      return p.coverPage == null ? svgUrl(`cover-${p.id}`, () => coverSvg(p)) : svgUrl(`page-${p.id}-${p.coverPage}`, () => pageSvg(p, p.coverPage));
    }
    if ((m = path.match(/^\/api\/patterns\/(\d+)\/page\/(\d+)/))) {
      const p = byId(m[1]);
      return svgUrl(`page-${p.id}-${m[2]}`, () => pageSvg(p, +m[2]));
    }
    if ((m = path.match(/^\/files\/(\d+)\//))) {
      const id = +m[1], p = byId(id) || byId(Math.floor((id - 1000) / 10));
      const note = "Demo sheet. In the real app this link opens your original, untouched PDF.";
      return svgUrl(`file-${p.id}`, () => pageSvg(p, p.pages > 1 ? 1 : 0, note));
    }
    if ((m = path.match(/^\/photos\/(.+)$/))) return photos.get(m[1]) || "";
    return path;
  }

  /* ---------------------------------------------------------------- build guides (pre-written) */
  const GUIDES = {
    2: {
      summary: "A slim card holder with a pocket on each side and a third in the middle. Four flat pieces, one line of stitching around three sides: a good second project once you can cut straight.",
      difficulty: "beginner",
      difficulty_reason: "Everything is flat and the stitch line is one U shape. The only fiddly part is keeping four layers lined up while you punch.",
      time_estimate: "3 to 4 hours, in two sittings so the glue can set",
      finished_size: "100 × 72 mm, about 5 mm thick at the seam",
      skills_learned: ["cutting to a line", "edge finishing before assembly", "gluing in a narrow band", "punching through several layers", "saddle stitch"],
      before_you_start: "Print the pattern sheet at **100% / Actual size** and measure the 20 mm calibration square with a steel ruler. If it measures 19.4 mm, the printer scaled the page: turn off *Fit to page* and print again.\n\nRead all the steps once. The pocket tops are finished in step 3 because you can't reach them after stitching.",
      leather: [
        { parts: "A Body (2)", leather: "Vegetable-tanned cowhide, full grain", thickness_mm: "1.0–1.2", thickness_oz: "2.5–3", why: "Firm enough to hold cards without a lining, and the edges burnish to a smooth finish.", alternative: "A veg-tan shoulder offcut; many suppliers sell bags of them" },
        { parts: "B Pocket (2)", leather: "The same leather as the body", thickness_mm: "1.0–1.2", thickness_oz: "2.5–3", why: "Four layers meet at the seam. Thicker pockets would make it bulky and hard to punch.", alternative: "0.8–1.0 mm if you have it, for a slimmer holder" },
      ],
      leather_amount: "One piece of about 22 × 15 cm is enough, with room for a practice strip.",
      hardware: [],
      consumables: [
        { item: "Waxed polyester thread", spec: "0.45–0.55 mm, about 1.2 m", notes: "Four times the stitched length, plus a little" },
        { item: "Contact cement or water-based leather glue", spec: "", notes: "Water-based has less smell and gives you a few seconds to reposition" },
        { item: "Burnishing gum or plain water", spec: "", notes: "For the edges" },
      ],
      tools: [
        { name: "Craft knife", purpose: "Cutting the four pieces", essential: true, substitute: "A utility knife with a fresh blade" },
        { name: "Steel ruler", purpose: "Guiding the knife and checking the print scale", essential: true },
        { name: "Cutting mat", purpose: "Protects the table and the blade", essential: true, substitute: "Thick cardboard, replaced when it gets grooved" },
        { name: "Wing divider", purpose: "Scribing the stitch line at an even distance from the edge", essential: true, substitute: "A ruler and a blunt point, marked every few centimetres" },
        { name: "Stitching chisels, 3 mm", purpose: "Punching evenly spaced stitch holes", essential: true, substitute: "A fork to mark the spacing and an awl to pierce each hole" },
        { name: "Mallet", purpose: "Driving the chisels", essential: true, substitute: "A rubber or wooden hammer, never a steel one" },
        { name: "Blunt harness needles", purpose: "Saddle stitching", essential: true },
        { name: "Edge beveler", purpose: "Rounding the sharp corner of each edge", essential: false, substitute: "Fine sandpaper held at an angle" },
        { name: "Burnishing tool", purpose: "Polishing the edges", essential: false, substitute: "A scrap of canvas or denim" },
      ],
      steps: [
        { title: "Print and check the scale", pattern_says: "Print at 100% and check the 20 mm square.", how_to: "Open the pattern from the **Print** box, not a screenshot, and choose *Actual size* in the print dialog. Measure the square. Then cut the paper pieces out roughly and tape them to thin card if you want templates you can reuse.", techniques: [], tools_used: ["Steel ruler"], tips: ["Write the pattern name and scale on each template."], watch_out: ["A square that is 1 mm short means every piece is 5% too small: cards won't fit."] },
        { title: "Cut the four pieces", pattern_says: "Cut all parts and transfer the marks.", how_to: "Lay the templates on the **flesh side** (the rough side) and trace around them with a scratch awl or a silver pen. You need two A pieces and two B pieces.\n\nCut the straight lines against the steel ruler. Make two or three light passes instead of one heavy one, and keep the blade upright so the edge is square.", techniques: ["cutting leather with a knife"], tools_used: ["Craft knife", "Steel ruler", "Cutting mat"], tips: ["Put the ruler on the piece you're keeping, so a slip cuts into the waste."], watch_out: ["Cutting is permanent. Check each tracing against the template before you cut.", "Keep the hand that holds the ruler behind the blade."] },
        { title: "Finish the pocket tops", pattern_says: "Finish the edges that will be hidden.", how_to: "The top edge of each B pocket, and the top edge of each A body, will be visible but out of reach once the holder is stitched. Finish them now.\n\nRun the beveler along both corners of each top edge, or sand them lightly. Dampen the edge with a fingertip of water and rub it briskly with the burnishing tool until it turns darker and feels smooth.", techniques: ["edge beveling", "edge burnishing"], tools_used: ["Edge beveler", "Burnishing tool"], tips: ["Try it on an offcut first to learn how much water is enough: damp, not wet."], watch_out: ["Only the four top edges. Leave the other edges raw, because they are finished together at the end."] },
        { title: "Glue the pockets to the bodies", pattern_says: "Glue.", how_to: "Each B pocket sits on the grain side of an A body, lined up along the bottom and both sides.\n\nGlue only a **5 mm band** along those three edges, on both surfaces. Keep the glue out of the middle or the pocket won't open. Press together, then glue the two finished halves back to back the same way: flesh side to flesh side, 5 mm band on three edges. Let it set under a book for 20 minutes.", techniques: ["gluing with contact cement"], tools_used: [], tips: ["Scuff the grain side lightly where the glue goes, so it grips.", "A strip of masking tape 5 mm from the edge keeps the glue band neat."], watch_out: ["Contact cement grabs on touch. Line up one corner first and lower the rest.", "Work with a window open."] },
        { title: "Mark and punch the stitch holes", pattern_says: "Punch.", how_to: "Set the wing divider to **3.5 mm** and scribe a line along the two sides and the bottom of the front.\n\nStart at a top corner. Place the chisel on the line, hold it upright, and strike until the teeth just come through the back. For the next hit, put the first tooth in the last hole you made so the spacing stays even. Use a two-tooth chisel around the corners.", techniques: ["punching stitch holes"], tools_used: ["Wing divider", "Stitching chisels, 3 mm", "Mallet"], tips: ["Punch on a poly board or a stack of scrap leather, not on the cutting mat.", "Check the back after the first hit: the holes should sit the same distance from the edge as on the front."], watch_out: ["Holes can't be undone. Punch a test row through four layers of scrap first.", "A leaning chisel puts the back row off line."] },
        { title: "Saddle stitch around three sides", pattern_says: "Stitch.", how_to: "Cut about 1.2 m of thread and put a needle on each end. Pass one needle through the first hole and pull until both ends are the same length.\n\nFor every stitch: push the left needle through the next hole, then the right needle through the same hole, behind the first thread, and pull both snug. Keep the same order every time. At the end, stitch back through the last two holes, trim the thread to 2 mm and melt the ends flat with a lighter.", techniques: ["saddle stitch"], tools_used: ["Blunt harness needles"], tips: ["Go around the top corner twice at the start and at the end: that's where the pocket takes the strain.", "Pull each stitch with the same force for an even line."], watch_out: ["Don't pierce the first thread with the second needle. Pull the first thread back a little as the second goes through."] },
        { title: "Finish the outer edges", pattern_says: "Finish the outer edges.", how_to: "Sand the three stitched edges flat so the four layers look like one. Start with 240 grit and finish with 600. Bevel both corners, dampen, and burnish as in step 3 until the edge shines.\n\nRub a little leather balm into the grain and buff with a soft cloth.", techniques: ["edge beveling", "edge burnishing"], tools_used: ["Edge beveler", "Burnishing tool"], tips: ["Round the two bottom corners with sandpaper before burnishing; they wear better."], watch_out: [] },
      ],
      unclear_points: ["The pattern says “Glue, punch and stitch” in one line. The order matters: glue first, so the layers can't shift while you punch.", "No thread size or stitch spacing is given. 3 mm chisels with 0.45–0.55 mm thread suit a piece this small.", "It doesn't say the pocket tops need finishing before assembly. They do."],
      practice_first: "Glue two 10 cm scraps together, scribe a line, punch ten holes and saddle stitch them. Then burnish that edge. It takes fifteen minutes and shows you the whole project in miniature.",
      finishing_and_care: "Veg-tan darkens with light and handling. A thin coat of balm every few months keeps it supple. New pockets are tight: leave two cards in each overnight and they ease.",
    },
    1: {
      summary: "A key fob made from two layers with a folded strap held in the seam. One short line of stitching, so it's an ideal first project.",
      difficulty: "beginner",
      difficulty_reason: "Small, flat and quick. The strap adds two more layers at the top, which is the only place to take care.",
      time_estimate: "1.5 to 2 hours",
      finished_size: "40 × 80 mm body",
      skills_learned: ["cutting curves", "punching stitch holes", "saddle stitch", "edge burnishing"],
      before_you_start: "Print at **100% / Actual size** and measure the 20 mm square before cutting.",
      leather: [
        { parts: "A Body (2)", leather: "Vegetable-tanned cowhide", thickness_mm: "1.4–1.8", thickness_oz: "3.5–4.5", why: "Two layers give a fob that feels solid and keeps its shape.", alternative: "Any firm veg-tan offcut" },
        { parts: "B Strap", leather: "Vegetable-tanned cowhide", thickness_mm: "1.0–1.2", thickness_oz: "2.5–3", why: "It's folded double inside the seam, so thinner leather avoids a lump.", alternative: "Thin down the last 15 mm of a thicker strap with sandpaper" },
      ],
      leather_amount: "A 10 × 12 cm offcut.",
      hardware: [{ item: "Split key ring", quantity: "1", size: "30 mm", notes: "Threaded onto the strap before stitching" }],
      consumables: [{ item: "Waxed polyester thread", spec: "0.55–0.65 mm, about 1 m" }, { item: "Leather glue", spec: "", notes: "A thin layer, kept away from the stitch line" }],
      tools: [
        { name: "Craft knife", purpose: "Cutting the pieces", essential: true, substitute: "A sharp utility knife" },
        { name: "Stitching chisels, 4 mm", purpose: "Punching the stitch holes", essential: true, substitute: "An awl, with the spacing marked by a fork" },
        { name: "Mallet", purpose: "Driving the chisels", essential: true, substitute: "A wooden or rubber hammer" },
        { name: "Blunt harness needles", purpose: "Saddle stitching", essential: true },
        { name: "Burnishing tool", purpose: "Polishing the edge", essential: false, substitute: "A scrap of canvas" },
      ],
      steps: [
        { title: "Print, check and cut", pattern_says: "Print at 100%. Cut all parts.", how_to: "Check the calibration square, then trace both A pieces and the B strap on the flesh side. Cut the straight parts against a ruler. For the rounded ends, turn the leather, not the knife, and cut in short strokes.", techniques: ["cutting leather with a knife"], tools_used: ["Craft knife"], tips: ["A coin makes a good guide for the rounded corners."], watch_out: ["Measure the square first. A fob printed at 94% still works, but the strap won't fit the ring."] },
        { title: "Fold the strap and glue the layers", pattern_says: "Glue.", how_to: "Thread the key ring onto the strap and fold the strap in half. Glue the last 15 mm of the two strap ends together.\n\nSpread a thin layer of glue on the flesh side of both A pieces. Lay the strap ends on one piece, centred at the top, with 15 mm inside. Press the second piece on top and let it set.", techniques: ["gluing with contact cement"], tools_used: [], tips: ["Clamp the top with a bulldog clip over a scrap, so the clip doesn't mark the leather."], watch_out: ["Put the ring on before you glue. It can't go on afterwards."] },
        { title: "Punch and stitch", pattern_says: "Punch and stitch.", how_to: "Scribe a line 3.5 mm from the edge all the way around. Punch along it, starting at the top where the strap is, because that is the thickest part.\n\nSaddle stitch around the whole edge with a needle on each end of the thread. Finish by stitching back two holes, then trim and melt the ends.", techniques: ["punching stitch holes", "saddle stitch"], tools_used: ["Stitching chisels, 4 mm", "Mallet", "Blunt harness needles"], tips: ["Use a two-tooth chisel on the curves so the holes follow the line."], watch_out: ["The top has four layers. Strike harder there and check that the teeth come through."] },
        { title: "Finish the edge", pattern_says: "Finish the outer edges.", how_to: "Sand the edge until the layers are flush, dampen it, and rub with the burnishing tool or canvas until it is smooth and slightly glossy.", techniques: ["edge burnishing"], tools_used: ["Burnishing tool"], tips: ["A little beeswax rubbed on at the end seals the edge."], watch_out: [] },
      ],
      unclear_points: ["The pattern doesn't say how far the strap goes into the body. 15 mm is enough for the stitching to catch it twice."],
      practice_first: "Stitch ten holes through two scraps to get the rhythm of the saddle stitch.",
      finishing_and_care: "A drop of leather balm now and then. Keys scratch veg-tan; the marks blend in as it darkens.",
    },
  };
  const normTech = (t) => t.toLowerCase().replace(/[^a-z0-9 /&+-]/g, " ").replace(/\s+/g, " ").trim();
  function techniques(guide) {
    const counts = {};
    for (const s of guide.steps || []) for (const t of s.techniques || []) counts[normTech(t)] = (counts[normTech(t)] || 0) + 1;
    return Object.keys(counts).sort((a, b) => counts[b] - counts[a] || a.localeCompare(b)).slice(0, 10);
  }

  // The state a visitor first sees: one project on the bench with its guide half done.
  Object.assign(byId(2), { guide: GUIDES[2], guide_model: "claude-sonnet-5-5", guide_at: hoursAgo(26), status: "in_progress", progress: [0, 1], favorite: 1, notes: "Used a 1.2 mm natural veg-tan offcut. Templates taped to card worked well." });
  Object.assign(byId(3), { status: "wishlist" });
  Object.assign(byId(5), { status: "done", notes: "Second attempt. Skive the fold next time." });
  Object.assign(byId(10), { favorite: 1, status: "wishlist" });

  const settings = {
    model: "claude-sonnet-5-5", auto_sync_on_start: true, last_sync: hoursAgo(3), experience: "complete beginner",
    country: "", currency: "", units: "metric", about_me: "",
    toolkit: ["Craft knife", "Steel ruler", "Cutting mat", "Wing divider", "Mallet"],
    sources: [
      { name: SRC_A, kind: "gdrive", location: "https://drive.google.com/drive/folders/your-shared-folder", enabled: true },
      { name: SRC_B, kind: "folder", location: "D:\\Leather\\My own designs", enabled: true },
    ],
  };
  const MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"];

  /* ---------------------------------------------------------------- API views */
  class Http extends Error { constructor(status, detail) { super(detail); this.status = status; } }
  const DEMO_ONLY = (what) => new Http(400, `The demo can't ${what}. Run Awlchemy on your own computer to use it with your patterns.`);
  const ORDER = { Easy: 1, Medium: 2, Hard: 3, "Very Hard": 4 };
  const printsOf = (p) => p.papers.map((paper, i) => ({
    id: 1000 + p.id * 10 + i, rel_path: p.rel_path.replace(/\.pdf$/, ` ${paper}.pdf`), paper, label: "",
    pages: /^A[0-2]$/.test(paper) ? 1 : Math.max(2, Math.round(p.parts.reduce((a, [, w, h]) => a + w * h, 0) / 42000)),
  }));
  function listView(p) {
    const { guide, notes, parts, hardware, art, colour, coverPage, lines, ...rest } = p;
    return { ...rest, has_guide: !!guide, paper: null, print_of: null };
  }
  function detailView(p) {
    const g = p.guide;
    return {
      ...listView(p), notes: p.notes, guide: g, has_text: true, prints: printsOf(p),
      siblings: patterns.filter((x) => x.id !== p.id && x.collection === p.collection && x.source === p.source).map((x) => ({ id: x.id, title: x.title })),
      videos: g ? Object.fromEntries(techniques(g).map((t) => [t, []])) : {},
    };
  }
  function listPatterns(q) {
    const rows = patterns.filter((p) => {
      if (q.get("kind") && p.kind !== q.get("kind")) return false;
      const d = q.get("difficulty");
      if (d && (d === "unrated" ? p.difficulty : p.difficulty !== d)) return false;
      if (q.get("status") && p.status !== q.get("status")) return false;
      if (q.get("source") && p.source !== q.get("source")) return false;
      if (q.get("favorite") === "true" && !p.favorite) return false;
      const hay = `${p.title} ${p.collection} ${patternText(p)} ${p.notes}`.toLowerCase();
      return (q.get("q") || "").toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
    });
    rows.sort((a, b) => (ORDER[a.difficulty] || 5) - (ORDER[b.difficulty] || 5) || a.collection.localeCompare(b.collection) || a.title.localeCompare(b.title));
    return rows.map(listView);
  }
  function stats() {
    const n = (f) => patterns.filter(f).length;
    return {
      total: patterns.length, patterns: n((p) => p.kind === "pattern"), guides: n((p) => p.kind === "guide"), with_guide: n((p) => p.guide),
      in_progress: n((p) => p.status === "in_progress"), done: n((p) => p.status === "done"),
      sources: [...new Set(patterns.map((p) => p.source))].sort(), last_sync: settings.last_sync,
      library_job: runningJob("library"), claude: { cli: "not connected (this is the demo)", found: true },
      library_path: "library/ (on your computer, in the real app)", source_count: settings.sources.length,
    };
  }
  const sourcesView = () => settings.sources.map((s) => ({ ...s, patterns: patterns.filter((p) => p.source === s.name).length }));

  /* ---------------------------------------------------------------- pretend background jobs */
  const jobs = new Map();
  let jobSeq = 0;
  // tick(job, seconds since start) fills in log/progress and returns true when the job is over.
  function startJob(kind, key, tick) {
    const old = runningJob(key);
    if (old) return old;
    const job = { id: `demo${++jobSeq}`, kind, key, status: "running", log: [], progress: {}, result: null, error: null, started_at: nowIso(), finished_at: null, t0: Date.now(), tick };
    jobs.set(job.id, job);
    return publicJob(job);
  }
  function publicJob(job) {
    if (job.status === "running") {
      try {
        if (job.tick(job, (Date.now() - job.t0) / 1000)) { job.status = job.error ? "error" : "done"; job.finished_at = nowIso(); }
      } catch (e) { job.status = "error"; job.error = e.message; }
    }
    const { tick, t0, key, ...pub } = job;
    return { ...pub, log: [...job.log], progress: { ...job.progress } };
  }
  function runningJob(key) {
    for (const job of jobs.values()) if (job.key === key && job.status === "running") { const pub = publicJob(job); if (pub.status === "running") return pub; }
    return null;
  }
  function setPhase(job, phase) {
    if (job.progress.phase !== phase) Object.assign(job.progress, { phase, phase_started: Date.now() / 1000, done: 0 });
  }
  const logOnce = (job, line) => { if (!job.log.includes(line)) job.log.push(line); };

  function syncJob() {
    const fresh = byId(LUGGAGE_TAG.id) ? [] : ["Luggage Tag.pdf", "Luggage Tag A4.pdf", "Luggage Tag Letter.pdf"];
    return startJob("sync", "library", (job, t) => {
      Object.assign(job.progress, { source: SRC_A, source_kind: "gdrive", source_index: 1, source_count: settings.sources.length, failed: 0 });
      logOnce(job, `Checking '${SRC_A}' for new files…`);
      if (t < 3.5) {
        setPhase(job, "listing");
        Object.assign(job.progress, { folders: Math.min(9, 1 + Math.floor(t * 2.6)), found: t > 2 ? fresh.length : 0, have: Math.min(31, Math.floor(t * 10)) });
        return false;
      }
      const dl = fresh.length ? 5 : 0.8;
      if (t < 3.5 + dl) {
        setPhase(job, "downloading");
        const done = Math.min(fresh.length, Math.floor(((t - 3.5) / dl) * (fresh.length + 0.4)));
        Object.assign(job.progress, { total: fresh.length, done, bytes: done * 1.4e6, current: fresh[Math.min(done, fresh.length - 1)] || "" });
        return false;
      }
      const ix = fresh.length ? 4 : 0.8;
      if (t < 3.5 + dl + ix) {
        setPhase(job, "indexing");
        const done = Math.min(fresh.length, Math.floor(((t - 3.5 - dl) / ix) * (fresh.length + 0.4)));
        Object.assign(job.progress, { total: fresh.length, done, current: fresh[Math.min(done, fresh.length - 1)] || "" });
        return false;
      }
      if (fresh.length && !byId(LUGGAGE_TAG.id)) patterns.push({ ...LUGGAGE_TAG, added_at: nowIso(), papers: ["A4", "Letter"] });
      settings.last_sync = nowIso();
      job.result = { downloaded: fresh.length, failed: 0, errors: [], added: fresh.length ? 1 : 0, updated: 0, total: patterns.length };
      job.log.push(`Library: ${job.result.added} new, 0 updated.`);
      return true;
    });
  }
  const indexJob = () => startJob("index", "library", (job, t) => {
    setPhase(job, "indexing");
    Object.assign(job.progress, { total: 0, done: 0, current: "" });
    if (t < 1.5) return false;
    job.result = { added: 0, updated: 0, total: patterns.length };
    return true;
  });
  function guideJob(p) {
    const guide = GUIDES[p.id];
    return startJob("guide", `guide-${p.id}`, (job, t) => {
      const lines = [`Asking Claude Code (${settings.model}) to read '${p.title}'…`, `Reading ${p.id}.md…`,
        ...Array.from({ length: p.pages }, (_, i) => `Reading ${i}_1100.jpg…`)];
      lines.slice(0, 1 + Math.floor(t / 1.1)).forEach((l) => logOnce(job, l));
      if (t < lines.length * 1.1 + 1.5) return false;
      if (!guide) {
        job.error = "The demo has two build guides: Card Holder (ready) and Key Fob (written when you click). On your own computer, the Awlchemist writes one for any pattern PDF.";
        return true;
      }
      logOnce(job, `Guide ready: ${guide.steps.length} steps.`);
      Object.assign(p, { guide, guide_model: settings.model, guide_at: nowIso() });
      job.result = { pattern_id: p.id, steps: guide.steps.length };
      return true;
    });
  }
  const videoJob = (p) => startJob("videos", `guide-${p.id}`, (job, t) => {
    logOnce(job, "Searching YouTube…");
    if (t < 2) return false;
    job.error = "The demo can't search the web. In the real app, the Awlchemist looks up beginner tutorials for each technique and keeps only links that really came back from the search.";
    return true;
  });

  /* ---------------------------------------------------------------- the Awlchemist's pre-written answers */
  const DEMO_NOTE = "\n\n*This answer was written in advance for the demo. On your own computer the Awlchemist reads the pattern's pages and answers the question you actually asked.*";
  const ANSWERS = [
    [/explain it differently|smaller steps/i, () => "Here is the same step, slower.\n\n1. **Set up.** Put only the tools for this step on the bench, and a scrap of the same leather next to your work.\n2. **Try it on the scrap.** Do the whole motion once where it doesn't matter. You'll feel how much pressure it takes.\n3. **Do the first centimetre and stop.** Look at the front and the back. If the line is straight and the same on both sides, carry on. If it isn't, it's a small fix now.\n4. **Finish in one sitting.** Stopping halfway is where spacing and tension drift.\n\n**What right looks like:** the mark or stitch sits the same distance from the edge all the way along, the back matches the front, and nothing puckers when you lay the piece flat."],
    [/shopping list|where to buy what/i, (p) => {
      const g = p && p.guide;
      if (!g) return "I'd build your shopping list from the build guide: the leather for each part, the hardware, thread and glue, and the tools you don't own yet. Write the guide for this pattern first.";
      const own = (name) => settings.toolkit.some((t) => name.toLowerCase().includes(t.toLowerCase()) || t.toLowerCase().includes(name.toLowerCase()));
      return `Here is what this pattern needs.\n\n**Leather**\n${g.leather.map((l) => `- ${l.parts}: ${l.leather}, ${l.thickness_mm} mm`).join("\n")}\n- Amount: ${g.leather_amount}\n\n**Thread, glue and finishing**\n${g.consumables.map((c) => `- ${c.item}${c.spec ? `, ${c.spec}` : ""}`).join("\n")}\n${g.hardware.length ? `\n**Hardware**\n${g.hardware.map((h) => `- ${h.item}${h.size ? `, ${h.size}` : ""}`).join("\n")}\n` : ""}\n**Tools you don't have yet**\n${g.tools.filter((t) => !own(t.name)).map((t) => `- ${t.name}${t.essential ? "" : " (optional)"}${t.substitute ? `. Until then: ${t.substitute.charAt(0).toLowerCase()}${t.substitute.slice(1)}` : ""}`).join("\n")}\n\nIn the real app I'd now search the web for shops that ship to your country and add links with rough prices. The demo has no web search, so there are no shop links here.`;
    }],
    [/video/i, () => "In the real app I'd search for two or three beginner tutorials, link them, and tell you what to watch for in each. The demo has no web search, and I won't make up links.\n\nWhat to look for when you search yourself:\n\n- **A close-up of the hands**, filmed from the maker's point of view.\n- **Real speed, not sped up**, at least once through.\n- **The back of the work shown**, not only the front.\n- **A fix for a mistake.** Makers who show one are the ones worth learning from."],
    [/practi[sc]e before|complete beginner/i, (p) => `Before ${p ? `the ${p.title}` : "your first project"}, spend half an hour on scrap:\n\n1. **Cut three straight strips** against a steel ruler, 2 cm wide. Light passes, blade upright. Check that the edges are square.\n2. **Scribe a stitch line** 3.5 mm from the edge with a divider.\n3. **Punch ten holes**, placing the first tooth in the last hole each time.\n4. **Saddle stitch them**, with the same needle going first every stitch.\n5. **Burnish one edge**: dampen, then rub until it darkens.\n\nIf the stitches lean the same way and the back looks like the front, you're ready. If not, do one more strip: it's cheaper than the project leather.`],
    [/hardest/i, (p) => `Three places usually decide how ${p ? `a ${p.title.toLowerCase()}` : "a project"} turns out:\n\n- **Keeping layers lined up while you punch.** Glue first and let it set, then punch from the side people will see.\n- **Corners.** Switch to a two-tooth chisel and make sure a hole lands exactly on the corner, or the stitch cuts across it.\n- **Edges where several layers meet.** Sand them flush before burnishing, or each layer shows as a ridge.\n\nNone of these need special tools. They need a test on scrap and a slower pace for those few minutes.`],
    [/thinner|cheaper leather/i, () => "Yes, within limits.\n\n- **Thinner:** going down about 0.3 mm is fine for pockets and linings. For the body it makes the piece floppy, so keep that within 0.2 mm of the guide.\n- **Cheaper:** veg-tan *shoulder* or *belly* offcuts cost much less than a panel cut from the bend. Belly stretches, so use it for small flat parts.\n- **Not for this:** very soft chrome-tanned garment leather. It won't burnish and it shifts while you stitch.\n\nIf you change the thickness, punch a test seam through the full stack first. Thread and chisel size depend on it."],
    [/don'?t have all the hardware|without.*hardware/i, () => "Hardware is the easiest thing to design around:\n\n- **No snap:** close a flap with a slit and a tab cut from the same leather.\n- **No rivets:** stitch the joint instead. A small box stitch, a square with a cross in it, holds a strap very well.\n- **No buckle:** a fixed loop, or two holes and a short lace knotted through them.\n\nA split key ring is the one thing worth buying: nothing home-made replaces it."],
    [/which pattern.*first|make first|make next/i, () => "From your library, in this order:\n\n1. **Key Fob (#1).** Two layers, one short seam. You finish it in an evening and learn cutting, punching and the saddle stitch.\n2. **Card Holder (#2).** The same skills over a longer seam, plus gluing in a narrow band and finishing edges before assembly. You've already started this one.\n3. **Passport Cover (#6).** Bigger panels, so you practise cutting long straight lines.\n\nLeave the Bifold Wallet (#3) until those feel easy: it adds stacked pockets, where a 1 mm error shows.\n\nYou own a knife, ruler, mat, divider and mallet. For the first two you still need stitching chisels and two needles."],
    [/saddle stitch/i, () => "**The saddle stitch**, one thread and two needles:\n\n1. **Measure the thread:** four times the seam length, plus 10 cm. Put a blunt needle on each end.\n2. **Start:** pass one needle through the first hole and pull until both sides are equal.\n3. **Each stitch:** push the left needle through the next hole. Pull that thread slightly back toward you, then push the right needle through the same hole *behind* it. Pull both ends snug.\n4. **Same order every time.** Left first, right second, right needle behind the thread. That's what makes the stitches lean the same way.\n5. **Finish:** stitch back two or three holes, trim to 2 mm, melt the ends of polyester thread flat.\n\nIf one thread breaks, the other still holds the seam. That's the difference from a machine stitch.\n\n**Common mistakes:** piercing the first thread with the second needle, and pulling some stitches harder than others."],
    [/burnish|smooth.*edges/i, () => "Smooth edges come from four steps in order:\n\n1. **Flush.** Sand the edge until the layers look like one piece (240 grit, then 400 to 600).\n2. **Bevel.** Take the sharp corner off both sides with an edge beveler, or with sandpaper held at an angle.\n3. **Dampen.** A fingertip of water or a little burnishing gum. Damp, not wet.\n4. **Rub.** Fast, light strokes with a wood slicker or a scrap of canvas until the edge darkens and turns glossy. Heat from friction does the work, not pressure.\n\nThis works on **vegetable-tanned** leather. Chrome-tanned leather doesn't burnish; its edges are painted or folded instead."],
    [/thickness|oz vs mm|oz\b/i, () => "Leather thickness is given in **millimetres** or in **ounces**. One ounce is 1/64 of an inch, about **0.4 mm**.\n\n| oz | mm | Typical use |\n|---|---|---|\n| 2–3 | 0.8–1.2 | Linings, wallet pockets, card holders |\n| 3–4 | 1.2–1.6 | Wallet outers, small pouches, watch straps (two layers) |\n| 5–6 | 2.0–2.4 | Bags, notebook covers, sheaths |\n| 8–10 | 3.2–4.0 | Belts, straps that carry weight |\n\nHides vary, so sellers give a range. When a pattern stacks layers, add them up: four layers of 1.2 mm is nearly 5 mm at the seam, which decides your chisel and thread size."],
    [/minimum toolkit|what.*tools/i, () => "The least you need for a first stitched project:\n\n- **A sharp knife** and spare blades\n- **A steel ruler**\n- **A cutting mat**\n- **A wing divider**, to mark the stitch line\n- **Stitching chisels**, one with 2 teeth and one with 4 to 6\n- **A mallet** that isn't steel\n- **Two blunt harness needles** and waxed thread\n- **Leather glue**\n\nYou already have the first four and the mallet. Sandpaper and a scrap of canvas stand in for an edge beveler and a burnishing tool until you want them."],
    [/where can i buy|near me|shop/i, () => "In the real app I'd search the web for suppliers that ship to the country in your settings and give you links with rough prices. The demo has no web search, and I won't invent shop names.\n\nWhat to look for in a first order:\n\n- **Vegetable-tanned shoulder or panel**, 1.2 to 1.6 mm, around an A4 sheet in size or a bag of offcuts\n- **Waxed polyester thread**, 0.55 mm, one spool\n- A supplier who sells **small cuts**, so you don't have to buy a whole side"],
  ];
  function answer(text, p, hadPhotos) {
    if (hadPhotos) return "I can't look at photos in the demo. In the real app I open the picture and tell you what I see: stitch spacing and tension, how the edges are finished, where a cut wandered, and what to change next time." + DEMO_NOTE;
    for (const [re, fn] of ANSWERS) if (re.test(text)) return fn(p) + DEMO_NOTE;
    return `The demo only has a handful of answers ready, and that question isn't one of them. Try the suggested questions under “New question”${p ? ", or the buttons inside a build guide step" : ""}.\n\nOn your own computer this is a real conversation: the Awlchemist reads the pattern's pages, knows your toolkit and level, searches the web for shops and tutorials, and gives feedback on photos of your work.`;
  }

  const chats = [];
  let chatSeq = 0;
  function chatReply(chat, form) {
    const text = String(form.get("text") || "");
    const files = form.getAll("photos").filter((f) => f && f.size);
    const names = files.map((f, i) => { const n = `demo-${Date.now()}-${i}`; photos.set(n, URL.createObjectURL(f)); return n; });
    const p = chat.pattern_id ? byId(chat.pattern_id) : null;
    const reply = answer(text, p, files.length > 0);
    chat.messages.push({ role: "user", text, sources: [], photos: names }, { role: "assistant", text: reply, sources: [], photos: [] });
    chat.updated_at = nowIso();
    const steps = [[500, { type: "status", text: p ? `Reading: ${p.id}.md…` : "Reading your library…" }]];
    const chunks = reply.match(/[\s\S]{1,14}(\s|$)/g) || [reply];
    chunks.forEach((c) => steps.push([28, { type: "text", text: c }]));
    steps.push([120, { type: "done", sources: [] }]);
    const enc = new TextEncoder();
    const stream = new ReadableStream({
      async start(ctrl) {
        for (const [ms, ev] of steps) { await sleep(ms); ctrl.enqueue(enc.encode(`data: ${JSON.stringify(ev)}\n\n`)); }
        ctrl.close();
      },
    });
    return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
  }

  /* ---------------------------------------------------------------- router */
  function need(id) {
    const p = byId(id);
    if (!p) throw new Http(404, "Pattern not found");
    return p;
  }
  function route(method, path, q, body) {
    let m;
    if (path === "/api/settings") {
      if (method === "PUT") for (const k of Object.keys(body || {})) if (k in settings && k !== "sources" && k !== "last_sync") settings[k] = body[k];
      return { ...settings, models: MODELS };
    }
    if (path === "/api/stats") return stats();
    if (path === "/api/patterns" && method === "GET") return listPatterns(q);
    if ((m = path.match(/^\/api\/patterns\/(\d+)$/))) {
      const p = need(m[1]);
      if (method === "PATCH") {
        for (const k of ["status", "notes", "title"]) if (body[k] !== undefined) p[k] = body[k];
        if (body.favorite !== undefined) p.favorite = body.favorite ? 1 : 0;
        if (body.progress !== undefined) p.progress = [...new Set(body.progress)].sort((a, b) => a - b);
        if (body.difficulty !== undefined) p.difficulty = body.difficulty || null;
      }
      return detailView(p);
    }
    if ((m = path.match(/^\/api\/patterns\/(\d+)\/markdown$/))) return { markdown: patternText(need(m[1])) };
    if ((m = path.match(/^\/api\/patterns\/(\d+)\/cover$/))) { need(m[1]).coverPage = +body.get("page"); return { ok: true }; }
    if ((m = path.match(/^\/api\/patterns\/(\d+)\/guide-job$/))) return runningJob(`guide-${m[1]}`) || {};
    if ((m = path.match(/^\/api\/patterns\/(\d+)\/guide$/))) return guideJob(need(m[1]));
    if ((m = path.match(/^\/api\/patterns\/(\d+)\/videos$/))) return videoJob(need(m[1]));
    if (path === "/api/videos") return {};
    if (path === "/api/sync") return syncJob();
    if (path === "/api/reindex") return indexJob();
    if ((m = path.match(/^\/api\/jobs\/(.+)$/))) {
      if (!jobs.has(m[1])) throw new Http(404, "Not found");
      return publicJob(jobs.get(m[1]));
    }
    if (path.startsWith("/api/import/")) throw DEMO_ONLY("import files or links");
    if (path === "/api/chats" && method === "GET") {
      const pid = q.get("pattern_id") ? +q.get("pattern_id") : null;
      return chats.filter((c) => c.pattern_id === pid).sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map(({ messages, ...c }) => c);
    }
    if (path === "/api/chats") {
      const chat = { id: ++chatSeq, pattern_id: body.pattern_id || null, title: body.title || "New question", created_at: nowIso(), updated_at: nowIso(), messages: [] };
      chats.push(chat);
      return { id: chat.id };
    }
    if ((m = path.match(/^\/api\/chats\/(\d+)(\/message)?$/))) {
      const i = chats.findIndex((c) => c.id === +m[1]);
      if (i < 0) throw new Http(404, "Chat not found");
      if (m[2]) return chatReply(chats[i], body);
      if (method === "DELETE") { chats.splice(i, 1); return { ok: true }; }
      return chats[i];
    }
    if (path === "/api/sources") {
      if (method === "POST") throw DEMO_ONLY("add pattern sources");
      return sourcesView();
    }
    if ((m = path.match(/^\/api\/sources\/(.+)$/)) && method === "DELETE") {
      const name = decodeURIComponent(m[1]);
      settings.sources = settings.sources.filter((s) => s.name !== name);
      let removed = 0;
      if (q.get("delete_files") === "true") {
        for (let i = patterns.length - 1; i >= 0; i--) if (patterns[i].source === name) { patterns.splice(i, 1); removed++; }
      }
      return { sources: sourcesView(), removed, kept: 0 };
    }
    if (path === "/api/claude/check") throw new Http(400, "There's no Claude Code behind the demo. In the real app this checks that it's installed and signed in.");
    throw new Http(404, `The demo doesn't have ${path}`);
  }

  async function demoFetch(url, init = {}) {
    const u = new URL(url, "http://demo.invalid");
    const method = (init.method || "GET").toUpperCase();
    let body = init.body;
    if (typeof body === "string") { try { body = JSON.parse(body); } catch { /* leave as text */ } }
    await sleep(40 + Math.random() * 80);
    try {
      const out = route(method, u.pathname, u.searchParams, body);
      if (out instanceof Response) return out;
      return new Response(JSON.stringify(out), { status: 200, headers: { "Content-Type": "application/json" } });
    } catch (e) {
      if (!(e instanceof Http)) console.error(e);
      return new Response(JSON.stringify({ detail: e.message }), { status: e.status || 500, headers: { "Content-Type": "application/json" } });
    }
  }

  window.AWLCHEMY_DEMO = { fetch: demoFetch, asset, svg: { cover: (id) => coverSvg(byId(id)), page: (id, n) => pageSvg(byId(id), n) } };

  /* ---------------------------------------------------------------- "this is a demo" bar */
  if (typeof document !== "undefined" && document.body) {
    const style = document.createElement("style");
    style.textContent = `
      body { padding-bottom: 56px; }
      .demo-bar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 60; background: #221c18; color: #f2efe8;
        display: flex; gap: 8px 18px; align-items: center; justify-content: center; flex-wrap: wrap; padding: 9px 16px; font-size: .9rem; }
      .demo-bar strong { color: #e9c98a; }
      .demo-bar a { color: #221c18; background: #c8955c; border-radius: 4px; padding: 5px 12px; font-weight: 700; text-decoration: none; white-space: nowrap; }
      .demo-bar a:hover { background: #d6a670; color: #221c18; }
      .bench-inner { max-height: calc(100vh - 164px); }
      .toast { bottom: 72px; }`;
    document.head.appendChild(style);
    const bar = document.createElement("div");
    bar.className = "demo-bar";
    bar.setAttribute("role", "note");
    bar.innerHTML = `<span><strong>Demo.</strong> Made-up patterns and pre-written answers; nothing is saved. The real app runs on your computer with your own PDFs.</span><a href="${REPO}">Get Awlchemy on GitHub</a>`;
    document.body.appendChild(bar);
  }
})();
