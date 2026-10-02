// Review 1 deck for tia. Every figure here comes from a committed JSON under
// eval/results/ or from a command run in the repository — nothing is invented.
const pptxgen = require("pptxgenjs");

const INK = "17232F"; // deep slate, dominant on dark slides
const PAPER = "FFFFFF";
const LIGHT = "F3F5F7";
const MUTED = "62727F";
const RULE = "D8DEE4";
const ACCENT = "D1453B"; // signal: the miss, the danger
const GOOD = "2E7D62"; // caught / safe
const AMBER = "C07A1B"; // the cost of falling back

const H = "Cambria";
const B = "Calibri";
const M = "Courier New";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
pres.author = "Tanmay Singh";
pres.title = "tia — Final Review";

const W = 13.3;
const MARGIN = 0.7;

// ---------------------------------------------------------------- helpers
function titleSlide(s, text, kicker, dark) {
  if (kicker) {
    s.addText(kicker.toUpperCase(), {
      x: MARGIN, y: 0.42, w: 11.9, h: 0.28,
      fontFace: B, fontSize: 11, bold: true, charSpacing: 2,
      color: dark ? AMBER : MUTED, isTextBox: true, margin: 0,
    });
  }
  s.addText(text, {
    x: MARGIN, y: kicker ? 0.72 : 0.55, w: 11.9, h: 0.85,
    fontFace: H, fontSize: 34, bold: true,
    color: dark ? PAPER : INK, isTextBox: true, margin: 0,
  });
}

function note(s, text) {
  s.addNotes(text);
}

// A grid of small squares standing in for a test suite. The visual motif.
function testGrid(s, x, y, cols, rows, cell, gap, litIndexes, litColor, offColor) {
  const lit = new Set(litIndexes);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const i = r * cols + c;
      s.addShape(pres.ShapeType.rect, {
        x: x + c * (cell + gap), y: y + r * (cell + gap), w: cell, h: cell,
        fill: { color: lit.has(i) ? litColor : offColor },
        line: { width: 0 },
      });
    }
  }
}

function statCard(s, x, y, w, value, label, color, sub) {
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h: 1.72, rectRadius: 0.08,
    fill: { color: LIGHT }, line: { width: 0 },
  });
  s.addText(value, {
    x: x + 0.25, y: y + 0.18, w: w - 0.5, h: 0.72,
    fontFace: H, fontSize: 34, bold: true, color, isTextBox: true, margin: 0,
  });
  s.addText(label, {
    x: x + 0.25, y: y + 0.92, w: w - 0.5, h: 0.3,
    fontFace: B, fontSize: 12, bold: true, color: INK, isTextBox: true, margin: 0,
  });
  if (sub) {
    s.addText(sub, {
      x: x + 0.25, y: y + 1.22, w: w - 0.5, h: 0.4,
      fontFace: B, fontSize: 10, color: MUTED, isTextBox: true, margin: 0,
    });
  }
}

function table(s, x, y, w, headers, rows, colW, opts = {}) {
  const head = headers.map((h) => ({
    text: h,
    options: { bold: true, color: PAPER, fill: { color: INK }, fontSize: opts.fs || 11 },
  }));
  const body = rows.map((r) =>
    r.map((cell) => {
      if (typeof cell === "object") return { text: cell.text, options: { fontSize: opts.fs || 11, ...cell.options } };
      return { text: cell, options: { fontSize: opts.fs || 11, color: INK } };
    })
  );
  s.addTable([head, ...body], {
    x, y, w, colW,
    border: { type: "solid", color: RULE, pt: 0.5 },
    fontFace: B, valign: "middle",
    rowH: opts.rowH || 0.32,
    margin: 0.06,
  });
}

// ---------------------------------------------------------------- 1. title
{
  const s = pres.addSlide();
  s.background = { color: INK };
  s.addText("tia", {
    x: MARGIN, y: 1.9, w: 7.5, h: 1.5,
    fontFace: H, fontSize: 96, bold: true, color: PAPER, isTextBox: true, margin: 0,
  });
  s.addText("Selective test execution for CI pipelines", {
    x: MARGIN, y: 3.35, w: 8.2, h: 0.5,
    fontFace: H, fontSize: 24, color: "AFC0CE", isTextBox: true, margin: 0,
  });
  s.addText(
    "Zero missed defects across 211 injected into two real codebases, at up to 65.2% less test time.",
    { x: MARGIN, y: 3.95, w: 7.6, h: 0.8, fontFace: B, fontSize: 14, color: "8DA0B0", isTextBox: true, margin: 0 }
  );
  s.addText("FINAL REVIEW", {
    x: MARGIN, y: 5.35, w: 3.5, h: 0.3,
    fontFace: B, fontSize: 12, bold: true, charSpacing: 3, color: AMBER, isTextBox: true, margin: 0,
  });
  s.addText("Tanmay Singh  ·  B.Tech CSE  ·  VIT Bhopal", {
    x: MARGIN, y: 5.7, w: 6, h: 0.3,
    fontFace: B, fontSize: 12, color: "8DA0B0", isTextBox: true, margin: 0,
  });
  testGrid(s, 9.15, 1.9, 12, 12, 0.22, 0.09, [26, 27, 38, 51, 62, 63, 75], AMBER, "223141");
  s.addText("31 of 1,334 tests", {
    x: 9.15, y: 5.65, w: 3.4, h: 0.3,
    fontFace: M, fontSize: 11, color: "8DA0B0", isTextBox: true, margin: 0,
  });
  note(s, "A tool that runs only the tests a git change can affect, and runs everything whenever that cannot be established. The contribution is not speed — it is inspectable selection logic paired with a reproducible safety evaluation.");
}

// ---------------------------------------------------------------- 2. the claim
{
  const s = pres.addSlide();
  titleSlide(s, "What we are claiming, and what it rests on", "the result");
  statCard(s, MARGIN, 1.85, 3.8, "0 / 211", "missed defects", GOOD, "attrs at 200 mutants, scrapy at 30");
  statCard(s, 4.75, 1.85, 3.8, "65.2%", "less test time on scrapy", GOOD, "58.4% on attrs");
  statCard(s, 8.8, 1.85, 3.8, "29.6%", "of changes run everything", AMBER, "50.5% on attrs — the honest cost");

  table(
    s, MARGIN, 3.95, 11.9,
    ["", "attrs", "scrapy"],
    [
      ["Tests in the suite", "1,334", "4,371"],
      ["Baseline suite time", "3.93 s", "62.6 s"],
      ["Non-equivalent defects injected", "184", "27"],
      [{ text: "Misses", options: { bold: true } }, { text: "0", options: { bold: true, color: GOOD } }, { text: "0", options: { bold: true, color: GOOD } }],
      ["Fallback rate", "50.5%", "29.6%"],
      ["Net time reduction", "58.4%", "65.2%"],
      ["Selection precision, median", "55.2%", "9.8%"],
    ],
    [5.1, 3.4, 3.4], { rowH: 0.36 }
  );
  s.addText("Every figure traces to a committed JSON under eval/results/. `make reproduce` regenerates all of them from the pinned corpus.", {
    x: MARGIN, y: 6.35, w: 11.9, h: 0.5,
    fontFace: B, fontSize: 12, italic: true, color: MUTED, isTextBox: true, margin: 0,
  });
  note(s, "Lead with the miss count, not the speedup. Anyone can make tests run faster by skipping them.");
}

// ---------------------------------------------------------------- 3. positioning
{
  const s = pres.addSlide();
  titleSlide(s, "This idea exists. The evidence does not.", "positioning");
  table(
    s, MARGIN, 1.85, 11.9,
    ["Existing work", "What it does well", "Where ours differs"],
    [
      ["pytest-testmon", "Mature, integrates cleanly, solves selection effectively", { text: "Publishes no reproducible safety evaluation — adoption rests on trust", options: { color: ACCENT } }],
      ["Bazel, Nx", "Reliable at scale from an explicit build graph", { text: "Requires adopting an entire build system", options: { color: ACCENT } }],
      ["Launchable and similar", "Sophisticated selection from large historical datasets", { text: "Closed methodology; the logic cannot be inspected", options: { color: ACCENT } }],
      ["Academic RTS literature", "Decades of rigorous formal evaluation", { text: "Research prototypes, not tools practitioners install", options: { color: ACCENT } }],
    ],
    [2.6, 4.5, 4.8], { rowH: 0.62 }
  );
  s.addShape(pres.ShapeType.roundRect, {
    x: MARGIN, y: 5.15, w: 11.9, h: 1.3, rectRadius: 0.08,
    fill: { color: INK }, line: { width: 0 },
  });
  s.addText("Inspectable selection logic, plus published measurements anyone can replay — including the ones that went against us.", {
    x: MARGIN + 0.35, y: 5.42, w: 11.2, h: 0.85,
    fontFace: H, fontSize: 17, bold: true, color: PAPER, isTextBox: true, margin: 0,
  });
  note(s, "The differentiator is evidence, not capability. Show --explain and make reproduce.");
}

// ---------------------------------------------------------------- 4. architecture
{
  const s = pres.addSlide();
  titleSlide(s, "Watch once, then ask — plus a graph for what watching misses", "architecture");
  const phases = [
    { n: "1", x: MARGIN, title: "Learn, once",
      body: "The suite runs under coverage.py with dynamic contexts. For every source line we record which tests executed it, inverted into a line to test map in .tia/map.db, keyed to the commit it was built at.",
      foot: "attrs 10 s  ·  scrapy 92 s  ·  1.6-2.2x instrumented" },
    { n: "2", x: 4.75, title: "Select, every change",
      body: "git reports the changed lines. Each path is routed by 16 classifier rules. Where the map can be trusted, changed lines are looked up and covering tests unioned. Everything else falls back, with a reason code.",
      foot: "lookup p95 1.41 ms" },
    { n: "3", x: 8.8, title: "Import graph",
      body: "A line that ran at import time belongs to no test, so the map cannot resolve it. The static import graph names every module that transitively imports the changed file and selects their tests instead.",
      foot: "attrs 37 edges  ·  scrapy 599" },
  ];
  phases.forEach((p) => {
    s.addShape(pres.ShapeType.roundRect, { x: p.x, y: 1.85, w: 3.8, h: 4.0, rectRadius: 0.08, fill: { color: LIGHT }, line: { width: 0 } });
    s.addShape(pres.ShapeType.ellipse, { x: p.x + 0.3, y: 2.1, w: 0.5, h: 0.5, fill: { color: INK }, line: { width: 0 } });
    s.addText(p.n, { x: p.x + 0.3, y: 2.13, w: 0.5, h: 0.45, fontFace: H, fontSize: 18, bold: true, color: PAPER, align: "center", isTextBox: true, margin: 0 });
    s.addText(p.title, { x: p.x + 0.95, y: 2.15, w: 2.7, h: 0.4, fontFace: H, fontSize: 16, bold: true, color: INK, isTextBox: true, margin: 0 });
    s.addText(p.body, { x: p.x + 0.3, y: 2.8, w: 3.2, h: 2.4, fontFace: B, fontSize: 11.5, color: INK, lineSpacing: 17, isTextBox: true, margin: 0 });
    s.addText(p.foot, { x: p.x + 0.3, y: 5.3, w: 3.2, h: 0.4, fontFace: M, fontSize: 9.5, bold: true, color: GOOD, isTextBox: true, margin: 0 });
  });
  s.addText("The map records what actually executed; the graph records what the source says. Neither is complete — dynamic loading is invisible to both, and SAFETY.md says so.", {
    x: MARGIN, y: 6.05, w: 11.9, h: 0.6,
    fontFace: B, fontSize: 12.5, italic: true, color: MUTED, isTextBox: true, margin: 0,
  });
  note(s, "Phase 1 is amortised. Phase 3 is what makes Phase 2's safety rule affordable.");
}

// ---------------------------------------------------------------- 5. the guarantee
{
  const s = pres.addSlide();
  s.background = { color: INK };
  titleSlide(s, "The classifier is the guarantee", "safety by construction", true);
  s.addText("Selective where confident", { x: MARGIN, y: 1.75, w: 5.6, h: 0.35, fontFace: B, fontSize: 13, bold: true, color: GOOD, isTextBox: true, margin: 0 });
  s.addText(
    [
      { text: "SELECTED — source in a fresh map: chosen by line", options: { bullet: true, breakLine: true } },
      { text: "IMPORT_CLOSURE — import-time line: the modules that import it", options: { bullet: true, breakLine: true } },
      { text: "TEST_CHANGED — a changed test always runs, unasked", options: { bullet: true, breakLine: true } },
      { text: "CONFTEST_CHANGED — everything at or below that directory", options: { bullet: true, breakLine: true } },
      { text: "PACKAGE_INIT / INSERTION_NO_HISTORY / LINE_NOT_IN_MAP — widen to the file", options: { bullet: true } },
    ],
    { x: MARGIN, y: 2.15, w: 5.6, h: 2.2, fontFace: B, fontSize: 11.5, color: "CFDAE3", paraSpaceAfter: 6, isTextBox: true, margin: 0 }
  );
  s.addText("Exhaustive everywhere else", { x: 6.9, y: 1.75, w: 5.7, h: 0.35, fontFace: B, fontSize: 13, bold: true, color: AMBER, isTextBox: true, margin: 0 });
  s.addText(
    [
      { text: "CLOSURE_TOO_LARGE — the closure covers too much to be worth it", options: { bullet: true, breakLine: true } },
      { text: "IMPORT_TIME_LINE — import-time line and no graph to consult", options: { bullet: true, breakLine: true } },
      { text: "UNMAPPED_FILE · BUILD_CONFIG_CHANGED · DEPENDENCY_CHANGED", options: { bullet: true, breakLine: true } },
      { text: "NON_SOURCE_ASSET · USER_CONFIGURED · MAP_STALE · NO_MAP", options: { bullet: true, breakLine: true } },
      { text: "CLASSIFIER_ERROR — our own bug must never mean fewer tests", options: { bullet: true } },
    ],
    { x: 6.9, y: 2.15, w: 5.7, h: 2.2, fontFace: B, fontSize: 11.5, color: "CFDAE3", paraSpaceAfter: 6, isTextBox: true, margin: 0 }
  );
  s.addShape(pres.ShapeType.roundRect, { x: MARGIN, y: 4.6, w: 11.9, h: 1.0, rectRadius: 0.08, fill: { color: "223141" }, line: { width: 0 } });
  s.addText("9 of the 16 rules deliberately give up the speed benefit. That is the design, not a shortfall in it.", {
    x: MARGIN + 0.35, y: 4.8, w: 11.2, h: 0.6, fontFace: H, fontSize: 17, bold: true, color: PAPER, isTextBox: true, margin: 0,
  });
  s.addText("Silent misses are the only unacceptable failure. A fast tool that occasionally lets a defect through is worse than no tool, because it manufactures confidence. When in doubt, run everything — and record why.", {
    x: MARGIN, y: 5.8, w: 11.9, h: 0.8, fontFace: B, fontSize: 12.5, italic: true, color: "8DA0B0", isTextBox: true, margin: 0,
  });
  note(s, "Every decision carries a machine-readable reason code. That is what makes the logic inspectable and the fallback rate measurable.");
}

// ---------------------------------------------------------------- 6. the miss
{
  const s = pres.addSlide();
  s.background = { color: INK };
  titleSlide(s, "Our own harness found a real miss", "why the evaluation came first", true);
  s.addText(
    [
      { text: "First safety run on attrs: 1 miss in 46.", options: { color: PAPER, bold: true, breakLine: true, paraSpaceAfter: 10 } },
      { text: "A mutant forced a condition true in attr/_cmp.py:88. The full suite caught it — six failures. tia selected two tests, and neither was among them.", options: { color: "CFDAE3", breakLine: true, paraSpaceAfter: 10 } },
      { text: "Root cause: tests/test_cmp.py calls cmp_using() at module level, so line 88 runs during collection. Coverage attributes import-time execution to no test at all, so the six tests that depended on it never appeared as covering it.", options: { color: "CFDAE3" } },
    ],
    { x: MARGIN, y: 1.8, w: 6.5, h: 2.8, fontFace: B, fontSize: 13, lineSpacing: 20, isTextBox: true, margin: 0 }
  );
  s.addShape(pres.ShapeType.roundRect, { x: 7.55, y: 1.8, w: 5.05, h: 2.5, rectRadius: 0.06, fill: { color: "0E1721" }, line: { width: 0 } });
  s.addText(
    [
      { text: "$ tia explain src/attr/_cmp.py:88", options: { color: GOOD, breakLine: true } },
      { text: "", options: { breakLine: true } },
      { text: "2 tests executed this line:", options: { color: PAPER, breakLine: true } },
      { text: "  TestNotImplementedIsPropagated", options: { color: "9FB3C2", breakLine: true } },
      { text: "  TestTotalOrderingException", options: { color: "9FB3C2", breakLine: true } },
      { text: "", options: { breakLine: true } },
      { text: "6 tests actually failed.", options: { color: ACCENT, bold: true } },
    ],
    { x: 7.85, y: 2.0, w: 4.5, h: 2.1, fontFace: M, fontSize: 11, lineSpacing: 16, isTextBox: true, margin: 0 }
  );
  s.addShape(pres.ShapeType.roundRect, { x: MARGIN, y: 4.85, w: 11.9, h: 1.55, rectRadius: 0.08, fill: { color: "223141" }, line: { width: 0 } });
  s.addText("The fix, and what it cost", { x: MARGIN + 0.35, y: 5.0, w: 11.2, h: 0.32, fontFace: B, fontSize: 12, bold: true, color: AMBER, isTextBox: true, margin: 0 });
  s.addText("Any change touching an import-time line now falls back. Re-run at the same seed: 0 misses in 47 — and the fallback rate rose to 59.6%. The rule is correct and expensive, and that measurement is what made the import graph the next thing to build rather than a nice-to-have.", {
    x: MARGIN + 0.35, y: 5.33, w: 11.2, h: 1.0, fontFace: B, fontSize: 13, color: PAPER, lineSpacing: 19, isTextBox: true, margin: 0,
  });
  note(s, "Spend time here. A safety claim is only as good as the experiment that could have falsified it — and this one did, on its first run.");
}

// ---------------------------------------------------------------- 7. import graph A/B
{
  const s = pres.addSlide();
  titleSlide(s, "The import graph, measured against itself", "phase 2");
  s.addText("One map, one seed, one set of mutation sites per repository. The arms differ in exactly one variable: whether the import closure is consulted.", {
    x: MARGIN, y: 1.72, w: 11.9, h: 0.5, fontFace: B, fontSize: 13, color: MUTED, isTextBox: true, margin: 0,
  });
  table(
    s, MARGIN, 2.3, 11.9,
    ["", "attrs: no graph", "attrs: graph", "scrapy: no graph", "scrapy: graph"],
    [
      [{ text: "Misses", options: { bold: true } }, "0 / 184", { text: "0 / 184", options: { color: GOOD, bold: true } }, "0 / 27", { text: "0 / 27", options: { color: GOOD, bold: true } }],
      ["Fallback frequency", "52.7%", "50.5%", "59.3%", { text: "29.6%", options: { color: GOOD, bold: true } }],
      ["Net time reduction", "57.0%", "58.4%", "40.4%", { text: "65.2%", options: { color: GOOD, bold: true } }],
      ["Precision, median", "62.5%", "55.2%", "25.0%", "9.8%"],
    ],
    [3.1, 2.2, 2.2, 2.2, 2.2], { rowH: 0.42 }
  );
  s.addShape(pres.ShapeType.roundRect, { x: MARGIN, y: 4.5, w: 11.9, h: 1.9, rectRadius: 0.08, fill: { color: LIGHT }, line: { width: 0 } });
  s.addText("It helps where the suite is slow, and nowhere else.", {
    x: MARGIN + 0.35, y: 4.68, w: 11.2, h: 0.35, fontFace: H, fontSize: 16, bold: true, color: ACCENT, isTextBox: true, margin: 0,
  });
  s.addText("On scrapy, whose suite takes 52 seconds, the graph halves the fallback rate and lifts the saving from 40.4% to 65.2%. On attrs, whose suite takes 3.9 seconds, it is worth almost nothing: 58.4% against 57.0%, with the fallback rate barely moving.\n\nThe property that predicts the benefit is absolute suite duration, not test count and not closure size. A four-second suite has nothing left to give once pytest's own startup is paid — which is the same floor that makes parallelism slower than serial on flask.", {
    x: MARGIN + 0.35, y: 5.08, w: 11.2, h: 1.2, fontFace: B, fontSize: 12, color: INK, lineSpacing: 17, isTextBox: true, margin: 0,
  });
  note(s, "If asked why the result is modest on attrs: a four-second suite has nothing to give. That is a finding about where this technique pays, not a failure of it.");
}

// ---------------------------------------------------------------- 8. methodology
{
  const s = pres.addSlide();
  titleSlide(s, "Two ways our own measurements lied", "methodology");
  const cards = [
    { x: MARGIN, tag: "D-0013 · fault 1", head: "A before/after across a map rebuild is not a controlled comparison",
      body: "Mutation sites are sampled from the lines the map records as covered. Rebuilding the map shifts that set slightly — 508,939 rows against 508,929 on the same commit — so the same seed selects different mutants.",
      figure: "59.6% -> 51.1% ... of nothing", fig2: "the first comparison was invalid",
      fix: "--no-import-graph selects the arm at selection time, so both run on one map and one site list. The arm is recorded in the payload and the filename." },
    { x: 7.0, tag: "D-0013 · fault 2", head: "A hand-picked exclusion threshold changed the answer",
      body: "Net reduction was computed outside the harness, dropping runs slower than 800s to exclude a mutant that hangs the suite. When the timeout moved from 900s to 600s, that same mutant fell on the other side of the threshold.",
      figure: "46% became 11%", fig2: "the tool had not changed at all",
      fix: "net_reduction is computed inside the harness and excludes runs by exit code — a timeout measures a hang, not a suite. Recomputed, the published figure stands." },
  ];
  cards.forEach((c) => {
    s.addShape(pres.ShapeType.roundRect, { x: c.x, y: 1.8, w: 5.6, h: 4.5, rectRadius: 0.08, fill: { color: LIGHT }, line: { width: 0 } });
    s.addText(c.tag, { x: c.x + 0.35, y: 2.0, w: 3.5, h: 0.28, fontFace: M, fontSize: 10.5, bold: true, color: AMBER, isTextBox: true, margin: 0 });
    s.addText(c.head, { x: c.x + 0.35, y: 2.3, w: 4.95, h: 0.8, fontFace: H, fontSize: 15, bold: true, color: INK, isTextBox: true, margin: 0 });
    s.addText(c.body, { x: c.x + 0.35, y: 3.15, w: 4.95, h: 1.4, fontFace: B, fontSize: 12, color: INK, lineSpacing: 18, isTextBox: true, margin: 0 });
    s.addText(c.figure, { x: c.x + 0.35, y: 4.6, w: 4.95, h: 0.35, fontFace: M, fontSize: 14, bold: true, color: ACCENT, isTextBox: true, margin: 0 });
    s.addText(c.fig2, { x: c.x + 0.35, y: 4.95, w: 4.95, h: 0.3, fontFace: B, fontSize: 10, color: MUTED, isTextBox: true, margin: 0 });
    s.addText(c.fix, { x: c.x + 0.35, y: 5.3, w: 4.95, h: 0.9, fontFace: B, fontSize: 11, italic: true, color: GOOD, isTextBox: true, margin: 0 });
  });
  note(s, "A project whose contribution is reproducible measurement has to be hardest on its own measurements. Both faults are written up in DECISIONS with what now prevents them.");
}

// ---------------------------------------------------------------- 9. demo
{
  const s = pres.addSlide();
  s.background = { color: INK };
  titleSlide(s, "Inspectable, not merely fast", "live demo — tia select --explain", true);
  s.addShape(pres.ShapeType.roundRect, { x: MARGIN, y: 1.85, w: 11.9, h: 3.1, rectRadius: 0.06, fill: { color: "0E1721" }, line: { width: 0 } });
  s.addText(
    [
      { text: "$ tia select --explain", options: { color: GOOD, breakLine: true } },
      { text: "", options: { breakLine: true } },
      { text: "src/attr/_funcs.py line 377", options: { color: PAPER, bold: true, breakLine: true } },
      { text: "  -> SELECTED: project source in a fresh map; tests chosen by line", options: { color: AMBER, breakLine: true } },
      { text: "     tests/test_funcs.py::TestAsDict::test_dicts", options: { color: "9FB3C2", breakLine: true } },
      { text: "     tests/test_hooks.py::TestAsDictHook::test_asdict", options: { color: "9FB3C2", breakLine: true } },
      { text: "     ... and 29 more", options: { color: "6B808F", breakLine: true } },
      { text: "", options: { breakLine: true } },
      { text: "tia: selected 31 of 1,334 tests", options: { color: PAPER, bold: true } },
    ],
    { x: MARGIN + 0.3, y: 2.05, w: 11.3, h: 2.75, fontFace: M, fontSize: 12.5, lineSpacing: 17, isTextBox: true, margin: 0 }
  );
  s.addText("Every selected test traces to the line that pulled it in and the rule that allowed it. Then: edit requirements.txt, and the tool gives up the speed benefit on purpose.", {
    x: MARGIN, y: 5.15, w: 11.9, h: 0.6, fontFace: B, fontSize: 13.5, color: "AFC0CE", isTextBox: true, margin: 0,
  });
  s.addText("./scripts/demo.sh  —  11 seconds, no network, runs the full suite live as the comparison", {
    x: MARGIN, y: 5.85, w: 11.9, h: 0.4, fontFace: M, fontSize: 12, bold: true, color: AMBER, isTextBox: true, margin: 0,
  });
  note(s, "The demo runs on the real attrs checkout. Step 5 injects a defect and prints 31 failed on purpose — the full suite and the selection both catch it.");
}

// ---------------------------------------------------------------- 10. CI
{
  const s = pres.addSlide();
  titleSlide(s, "Running in a real pipeline — and what it caught", "ci integration");
  s.addText("The pipeline tests tia with tia: it builds a map at the base commit, selects for the pull request's actual diff, runs that through the pytest plugin, and still runs the full suite as a safety net. A pipeline that stops running the full suite before its miss rate is measured is the false confidence this project argues against.", {
    x: MARGIN, y: 1.75, w: 11.9, h: 0.95, fontFace: B, fontSize: 13, color: INK, lineSpacing: 19, isTextBox: true, margin: 0,
  });
  s.addShape(pres.ShapeType.roundRect, { x: MARGIN, y: 2.85, w: 11.9, h: 1.5, rectRadius: 0.06, fill: { color: "0E1721" }, line: { width: 0 } });
  s.addText(
    [
      { text: "tia: selected 0 of 115 tests", options: { color: ACCENT, bold: true, breakLine: true } },
      { text: "  -> SELECTED: project source present in a fresh map", options: { color: "9FB3C2", breakLine: true } },
      { text: "", options: { breakLine: true } },
      { text: "a confident verdict, and an empty selection", options: { color: AMBER } },
    ],
    { x: MARGIN + 0.3, y: 3.05, w: 11.3, h: 1.15, fontFace: M, fontSize: 12.5, lineSpacing: 17, isTextBox: true, margin: 0 }
  );
  s.addText("On its third run, the pipeline caught the tool reporting an empty selection as a confident answer.", {
    x: MARGIN, y: 4.55, w: 11.9, h: 0.35, fontFace: H, fontSize: 16, bold: true, color: ACCENT, isTextBox: true, margin: 0,
  });
  s.addText("The changed lines were continuation lines of a multi-line statement, which coverage attributes to the statement's first line — so the lookup found nothing and reported that as \"nothing needs to run\". The pytest plugin already refused to run zero tests, so it was a reporting fault rather than a miss, but anyone integrating against `tia select --format json` would have been told with confidence that no tests were needed. An empty lookup is ignorance, not proof: it now widens to the file under LINE_NOT_IN_MAP.", {
    x: MARGIN, y: 4.95, w: 11.9, h: 1.5, fontFace: B, fontSize: 12.5, color: INK, lineSpacing: 18, isTextBox: true, margin: 0,
  });
  note(s, "Third bug our own evaluation found. The pattern is the argument: build the measuring apparatus first and it keeps earning its place.");
}

// ---------------------------------------------------------------- 11. limits
{
  const s = pres.addSlide();
  s.background = { color: INK };
  titleSlide(s, "What we do not claim", "limitations", true);
  s.addText(
    [
      { text: "Complete certainty is not attainable in a dynamically typed language, and we do not claim it. Code loaded by name at run time, getattr dispatch, monkeypatching, entry points and plugin registries are invisible to the import graph — there is a test in the suite that pins exactly that, so the report cannot quietly drift.", options: { color: "CFDAE3", breakLine: true, paraSpaceAfter: 12 } },
      { text: "The line-level map partly compensates, because it records what actually executed rather than what the source appears to say. Neither mechanism is complete.", options: { color: "CFDAE3", breakLine: true, paraSpaceAfter: 12 } },
      { text: "What we claim instead is bounded, measured safety: 0 misses in 211 non-equivalent injected defects, on two real codebases, reproducible from the pinned corpus with one command.", options: { color: PAPER, bold: true } },
    ],
    { x: MARGIN, y: 1.8, w: 7.1, h: 3.4, fontFace: B, fontSize: 13, lineSpacing: 20, isTextBox: true, margin: 0 }
  );
  s.addShape(pres.ShapeType.roundRect, { x: 8.1, y: 1.8, w: 4.5, h: 3.5, rectRadius: 0.08, fill: { color: "223141" }, line: { width: 0 } });
  s.addText("Not yet measured", { x: 8.45, y: 2.0, w: 3.9, h: 0.3, fontFace: B, fontSize: 12, bold: true, color: AMBER, isTextBox: true, margin: 0 });
  s.addText(
    [
      { text: "Fallback frequency over real historical commits, rather than injected defects", options: { bullet: true, breakLine: true } },
      { text: "Safety beyond 200 mutants per repository", options: { bullet: true, breakLine: true } },
      { text: "A third codebase", options: { bullet: true, breakLine: true } },
      { text: "Whether 0.6 is the right closure limit — it is SPEC's suggestion, not a measured optimum", options: { bullet: true } },
    ],
    { x: 8.45, y: 2.4, w: 3.9, h: 2.7, fontFace: B, fontSize: 11, color: "CFDAE3", lineSpacing: 16, paraSpaceAfter: 7, isTextBox: true, margin: 0 }
  );
  s.addText("A negative or mixed result, properly measured, is a valid finding. We report the fallback rate as prominently as the speedup, and the two measurements that misled us before we caught them.", {
    x: MARGIN, y: 5.55, w: 11.9, h: 0.8, fontFace: H, fontSize: 15, bold: true, italic: true, color: PAPER, isTextBox: true, margin: 0,
  });
  note(s, "Say the limitations before the panel finds them. The import graph test that pins dynamic-import blindness is the strongest honesty signal in the repo.");
}

// ---------------------------------------------------------------- 12. close
{
  const s = pres.addSlide();
  titleSlide(s, "Where this stands", "deliverables");
  const cols = [
    { x: MARGIN, head: "Delivered", color: GOOD, items: [
      "Installable CLI and pytest plugin, end to end",
      "Line-level map, git diff, 16-rule classifier",
      "Import graph with closure limit (Phase 2)",
      "Evaluation harness: corpus, baselines, defect injection, precision",
      "Two real codebases, four A/B arms, every figure from committed JSON",
      "CI pipeline running tia on tia",
      "125 tests, mypy --strict, 27 commits",
    ] },
    { x: 4.85, head: "Evidence", color: INK, items: [
      "docs/SAFETY.md — what is guaranteed and what is not",
      "docs/DECISIONS.md — 13 dated decisions, each with a falsification condition",
      "eval/results/ — raw JSON for every published number",
      "make reproduce — regenerates the tables from the pinned corpus",
      "github.com/Tanmay-Singh-24/tia — public, CI green on 3.11 and 3.12",
    ] },
    { x: 9.0, head: "Next", color: ACCENT, items: [
      "Fallback frequency over sampled historical commits",
      "Sweep the closure limit against net reduction",
      "Third corpus repository (black, held in reserve)",
      "PyPI release as tia-select",
      "Incremental map updates, so a stale map need not mean the full suite",
    ] },
  ];
  cols.forEach((c) => {
    s.addText(c.head, { x: c.x, y: 1.8, w: 3.6, h: 0.35, fontFace: B, fontSize: 13, bold: true, color: c.color, isTextBox: true, margin: 0 });
    s.addText(
      c.items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i !== c.items.length - 1 } })),
      { x: c.x, y: 2.2, w: 3.6, h: 3.4, fontFace: B, fontSize: 11, color: INK, lineSpacing: 16, paraSpaceAfter: 8, isTextBox: true, margin: 0 }
    );
  });
  s.addShape(pres.ShapeType.roundRect, { x: MARGIN, y: 5.8, w: 11.9, h: 0.95, rectRadius: 0.08, fill: { color: INK }, line: { width: 0 } });
  s.addText("0 misses in 211 injected defects. 65.2% less test time on a 4,371-test suite. Four bugs found by our own evaluation — including one the import graph itself introduced.", {
    x: MARGIN + 0.35, y: 6.0, w: 11.2, h: 0.6, fontFace: H, fontSize: 15, bold: true, italic: true, color: PAPER, isTextBox: true, margin: 0,
  });
  note(s, "Close on the evaluation finding our own bugs. That is the argument for building the measuring apparatus before the tool.");
}

pres.writeFile({ fileName: process.argv[2] || "tia-review-2.pptx" }).then((f) => console.log("wrote", f));
