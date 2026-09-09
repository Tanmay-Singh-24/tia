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
pres.title = "tia — Review 1";

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
    x: MARGIN, y: 2.0, w: 7.5, h: 1.5,
    fontFace: H, fontSize: 96, bold: true, color: PAPER, isTextBox: true, margin: 0,
  });
  s.addText("Selective test execution for CI pipelines", {
    x: MARGIN, y: 3.45, w: 8.2, h: 0.5,
    fontFace: H, fontSize: 24, color: "AFC0CE", isTextBox: true, margin: 0,
  });
  s.addText(
    "Run only the tests a change can affect — and run everything whenever that cannot be established.",
    { x: MARGIN, y: 4.05, w: 7.6, h: 0.7, fontFace: B, fontSize: 14, color: "8DA0B0", isTextBox: true, margin: 0 }
  );
  s.addText("REVIEW 1", {
    x: MARGIN, y: 5.35, w: 3, h: 0.3,
    fontFace: B, fontSize: 12, bold: true, charSpacing: 3, color: AMBER, isTextBox: true, margin: 0,
  });
  s.addText("Tanmay Singh  ·  B.Tech CSE  ·  VIT Bhopal", {
    x: MARGIN, y: 5.7, w: 6, h: 0.3,
    fontFace: B, fontSize: 12, color: "8DA0B0", isTextBox: true, margin: 0,
  });
  // motif: the suite, mostly unrun
  testGrid(s, 9.15, 2.0, 12, 12, 0.22, 0.09, [26, 27, 38, 51, 62, 63, 75], AMBER, "223141");
  s.addText("31 of 1,334 tests", {
    x: 9.15, y: 5.75, w: 3.4, h: 0.3,
    fontFace: M, fontSize: 11, color: "8DA0B0", isTextBox: true, margin: 0,
  });
  note(s, "tia: a command-line tool that runs only the tests a git change can affect. This is the Review 1 checkpoint: a working, measured, file- and line-level tool on two real codebases.");
}

// ---------------------------------------------------------------- 2. problem
{
  const s = pres.addSlide();
  titleSlide(s, "You change one line. Every test runs.", "the problem");
  s.addText(
    [
      { text: "A mature project accumulates thousands of automated checks. They run on every change, before it is allowed in.", options: { breakLine: true, paraSpaceAfter: 10 } },
      { text: "Change one line in a leaf function and perhaps thirty tests are connected to it. The rest examine the payment system, the export path, the CLI — areas the change cannot reach. They pass. They always pass. They ran anyway.", options: { breakLine: true, paraSpaceAfter: 10 } },
      { text: "Teams tolerate this because the alternative looks dangerous: skip the wrong test and a defect ships while the build reports success.", options: {} },
    ],
    { x: MARGIN, y: 1.85, w: 6.6, h: 2.9, fontFace: B, fontSize: 14, color: INK, lineSpacing: 22, isTextBox: true, margin: 0 }
  );
  s.addText("That is the actual gap: not speed, but speed with measured evidence of how safely it can be applied.", {
    x: MARGIN, y: 4.95, w: 6.6, h: 0.9,
    fontFace: H, fontSize: 16, bold: true, italic: true, color: ACCENT, isTextBox: true, margin: 0,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 7.9, y: 1.85, w: 4.7, h: 4.0, rectRadius: 0.08,
    fill: { color: LIGHT }, line: { width: 0 },
  });
  s.addText("attrs — one line changed", {
    x: 8.2, y: 2.05, w: 4.1, h: 0.3,
    fontFace: B, fontSize: 12, bold: true, color: INK, isTextBox: true, margin: 0,
  });
  testGrid(s, 8.2, 2.5, 14, 8, 0.24, 0.09, [16, 17, 30, 44, 58, 72, 86], ACCENT, "C9D3DA");
  s.addText("each square ≈ 12 tests · 31 of 1,334 selected", {
    x: 8.2, y: 5.15, w: 4.2, h: 0.28,
    fontFace: B, fontSize: 10, color: MUTED, isTextBox: true, margin: 0,
  });
  s.addText("3.93 s  →  0.82 s", {
    x: 8.2, y: 5.45, w: 4.2, h: 0.35,
    fontFace: M, fontSize: 16, bold: true, color: GOOD, isTextBox: true, margin: 0,
  });
  note(s, "Measured on the real attrs library at a pinned commit. 31 of 1,334 tests selected for a single-line change; 0.82s against a 3.93s serial baseline.");
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
    x: MARGIN, y: 5.15, w: 11.9, h: 1.25, rectRadius: 0.08,
    fill: { color: INK }, line: { width: 0 },
  });
  s.addText("Our contribution: inspectable selection logic paired with a published, replayable safety evaluation on real codebases.", {
    x: MARGIN + 0.35, y: 5.38, w: 11.2, h: 0.85,
    fontFace: H, fontSize: 17, bold: true, color: PAPER, isTextBox: true, margin: 0,
  });
  note(s, "Selective test execution is an established idea. What is scarce is an open tool whose logic can be read, paired with measurements anyone can reproduce.");
}

// ---------------------------------------------------------------- 4. how it works
{
  const s = pres.addSlide();
  titleSlide(s, "Two phases: watch once, then ask", "architecture");

  const phases = [
    {
      n: "1", x: MARGIN, title: "Learning — run once",
      body: "The full suite runs under coverage.py with dynamic contexts. For every source line we record which tests executed it, then invert that into a line → test map in .tia/map.db, keyed to the commit it was built at.",
      foot: "attrs: 10 s   ·   scrapy: 92 s",
    },
    {
      n: "2", x: 7.0, title: "Selection — every change",
      body: "git reports which lines changed. Each changed path is classified. Where the map can be trusted, the changed lines are looked up and the covering tests unioned. Everything else falls back to the full suite with a reason code.",
      foot: "median lookup 0.04 ms  ·  p95 1.41 ms",
    },
  ];
  phases.forEach((p) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: p.x, y: 1.85, w: 5.6, h: 3.5, rectRadius: 0.08,
      fill: { color: LIGHT }, line: { width: 0 },
    });
    s.addShape(pres.ShapeType.ellipse, {
      x: p.x + 0.32, y: 2.12, w: 0.55, h: 0.55,
      fill: { color: INK }, line: { width: 0 },
    });
    s.addText(p.n, {
      x: p.x + 0.32, y: 2.15, w: 0.55, h: 0.5,
      fontFace: H, fontSize: 20, bold: true, color: PAPER, align: "center", isTextBox: true, margin: 0,
    });
    s.addText(p.title, {
      x: p.x + 1.02, y: 2.18, w: 4.3, h: 0.4,
      fontFace: H, fontSize: 18, bold: true, color: INK, isTextBox: true, margin: 0,
    });
    s.addText(p.body, {
      x: p.x + 0.35, y: 2.95, w: 4.95, h: 1.75,
      fontFace: B, fontSize: 13, color: INK, lineSpacing: 20, isTextBox: true, margin: 0,
    });
    s.addText(p.foot, {
      x: p.x + 0.35, y: 4.72, w: 4.95, h: 0.32,
      fontFace: M, fontSize: 11, bold: true, color: GOOD, isTextBox: true, margin: 0,
    });
  });

  s.addText("The map records what actually executed, not what the source appears to say — which is why dynamic dispatch, fixtures and monkeypatching are partly covered where static analysis sees nothing.", {
    x: MARGIN, y: 5.62, w: 11.9, h: 0.8,
    fontFace: B, fontSize: 13, italic: true, color: MUTED, isTextBox: true, margin: 0,
  });
  note(s, "Phase 1 is amortised — built once and reused. Phase 2 runs on every change and is dominated by pytest's own startup, not by our lookup.");
}

// ---------------------------------------------------------------- 5. the guarantee
{
  const s = pres.addSlide();
  s.background = { color: INK };
  titleSlide(s, "The classifier is the guarantee", "safety by construction", true);

  s.addText("Selective where confident", {
    x: MARGIN, y: 1.75, w: 5.6, h: 0.35,
    fontFace: B, fontSize: 13, bold: true, color: GOOD, isTextBox: true, margin: 0,
  });
  s.addText(
    [
      { text: "SELECTED — source in a fresh map: chosen by line", options: { bullet: true, breakLine: true } },
      { text: "TEST_CHANGED — a changed test always runs, unasked", options: { bullet: true, breakLine: true } },
      { text: "CONFTEST_CHANGED — everything at or below that directory", options: { bullet: true, breakLine: true } },
      { text: "PACKAGE_INIT — the whole package, never by line", options: { bullet: true, breakLine: true } },
      { text: "INSERTION_NO_HISTORY — inserted lines widen to the file", options: { bullet: true } },
    ],
    { x: MARGIN, y: 2.15, w: 5.6, h: 2.1, fontFace: B, fontSize: 12, color: "CFDAE3", paraSpaceAfter: 6, isTextBox: true, margin: 0 }
  );

  s.addText("Exhaustive everywhere else", {
    x: 6.9, y: 1.75, w: 5.7, h: 0.35,
    fontFace: B, fontSize: 13, bold: true, color: AMBER, isTextBox: true, margin: 0,
  });
  s.addText(
    [
      { text: "UNMAPPED_FILE · BUILD_CONFIG_CHANGED", options: { bullet: true, breakLine: true } },
      { text: "DEPENDENCY_CHANGED · NON_SOURCE_ASSET", options: { bullet: true, breakLine: true } },
      { text: "IMPORT_TIME_LINE · USER_CONFIGURED", options: { bullet: true, breakLine: true } },
      { text: "MAP_STALE · NO_MAP · CLASSIFIER_ERROR", options: { bullet: true, breakLine: true } },
      { text: "Every one of these runs the entire suite", options: { bullet: false } },
    ],
    { x: 6.9, y: 2.15, w: 5.7, h: 2.1, fontFace: B, fontSize: 12, color: "CFDAE3", paraSpaceAfter: 6, isTextBox: true, margin: 0 }
  );

  s.addShape(pres.ShapeType.roundRect, {
    x: MARGIN, y: 4.5, w: 11.9, h: 1.05, rectRadius: 0.08,
    fill: { color: "223141" }, line: { width: 0 },
  });
  s.addText("9 of the 14 rules deliberately give up the speed benefit. That is the design, not a shortfall in it.", {
    x: MARGIN + 0.35, y: 4.72, w: 11.2, h: 0.6,
    fontFace: H, fontSize: 17, bold: true, color: PAPER, isTextBox: true, margin: 0,
  });
  s.addText("Silent misses are the only unacceptable failure. A fast tool that occasionally lets a defect through is worse than no tool, because it manufactures confidence. When in doubt, run everything — and say why.", {
    x: MARGIN, y: 5.75, w: 11.9, h: 0.8,
    fontFace: B, fontSize: 12.5, italic: true, color: "8DA0B0", isTextBox: true, margin: 0,
  });
  note(s, "This table is the whole safety argument. Every decision carries a machine-readable reason code, which is what makes the logic inspectable and the fallback rate measurable.");
}

// ---------------------------------------------------------------- 6. corpus
{
  const s = pres.addSlide();
  titleSlide(s, "The harness was built before the tool", "measurement first");
  s.addText("All six candidate repositories were cloned at pinned SHAs, installed and timed before anything was selected. Median of five runs after a warmup, one machine (Apple M4, 10 cores).", {
    x: MARGIN, y: 1.72, w: 11.9, h: 0.5,
    fontFace: B, fontSize: 13, color: MUTED, isTextBox: true, margin: 0,
  });
  table(
    s, MARGIN, 2.3, 11.9,
    ["Repository", "Tests", "Green", "-n auto", "Serial", "Outcome"],
    [
      [{ text: "scrapy", options: { bold: true } }, "5,000", "yes", "49.85 s", "204.85 s", { text: "CORPUS — primary", options: { color: GOOD, bold: true } }],
      [{ text: "attrs", options: { bold: true } }, "1,412", "yes", "2.30 s", "3.93 s", { text: "CORPUS — secondary", options: { color: GOOD, bold: true } }],
      ["httpx", "1,418", { text: "no", options: { color: ACCENT } }, { text: "deadlocks", options: { color: ACCENT } }, "5.17 s", { text: "rejected — hangs under xdist", options: { color: MUTED } }],
      ["rich", "981", { text: "no", options: { color: ACCENT } }, "3.06 s", "3.76 s", { text: "rejected — Pygments drift", options: { color: MUTED } }],
      ["black", "558", "yes", "6.48 s", "22.76 s", { text: "reserve for Review 2", options: { color: AMBER } }],
      ["flask", "494", "yes", "1.00 s", "0.66 s", { text: "rejected — too small", options: { color: MUTED } }],
    ],
    [2.2, 1.2, 1.0, 1.5, 1.5, 4.5], { rowH: 0.44 }
  );
  s.addText("scrapy is the only candidate whose runtime makes absolute savings meaningful; attrs is fast enough to run hundreds of mutants during development. Chosen for complementary reasons, not similar ones.", {
    x: MARGIN, y: 5.75, w: 11.9, h: 0.7,
    fontFace: B, fontSize: 13, italic: true, color: INK, isTextBox: true, margin: 0,
  });
  note(s, "Three of the six had moved their test dependencies since the proposal was written. `pip install -e .[tests]` exits 0 and installs nothing on a PEP 735 project — so 'prepared' now means pytest can actually collect the suite.");
}

// ---------------------------------------------------------------- 7. findings
{
  const s = pres.addSlide();
  titleSlide(s, "Two things the measurements contradicted", "evidence over assumption");

  const cards = [
    {
      x: MARGIN, tag: "D-0005", head: "“-n auto” is not automatically the optimised baseline",
      body: "The specification requires a parallel baseline so we cannot beat a handicapped one. On flask, parallel is 1.5× SLOWER than serial — ten worker processes cost more to start than the work they remove.",
      figure: "1.00 s  vs  0.66 s", figLabel: "flask: -n auto vs serial",
      fix: "Baseline is now the faster of the two modes per repo, and the report names which.",
    },
    {
      x: 7.0, tag: "D-0006", head: "Test count is a poor proxy for suite substance",
      body: "The corpus criterion was “1,000+ tests”. But black has 558 tests and a 22.8 s suite; attrs has 1,412 tests and a 3.9 s one. By test count black is disqualified; by the thing tia actually shortens it is six times the target.",
      figure: "558 → 22.8 s   ·   1,412 → 3.9 s", figLabel: "black vs attrs",
      fix: "Both criteria kept; each repo is described by which one it satisfies.",
    },
  ];
  cards.forEach((c) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: c.x, y: 1.8, w: 5.6, h: 4.45, rectRadius: 0.08,
      fill: { color: LIGHT }, line: { width: 0 },
    });
    s.addText(c.tag, {
      x: c.x + 0.35, y: 2.02, w: 2, h: 0.28,
      fontFace: M, fontSize: 11, bold: true, color: AMBER, isTextBox: true, margin: 0,
    });
    s.addText(c.head, {
      x: c.x + 0.35, y: 2.32, w: 4.95, h: 0.75,
      fontFace: H, fontSize: 16, bold: true, color: INK, isTextBox: true, margin: 0,
    });
    s.addText(c.body, {
      x: c.x + 0.35, y: 3.12, w: 4.95, h: 1.5,
      fontFace: B, fontSize: 12.5, color: INK, lineSpacing: 19, isTextBox: true, margin: 0,
    });
    s.addText(c.figure, {
      x: c.x + 0.35, y: 4.72, w: 4.95, h: 0.4,
      fontFace: M, fontSize: 15, bold: true, color: ACCENT, isTextBox: true, margin: 0,
    });
    s.addText(c.figLabel, {
      x: c.x + 0.35, y: 5.1, w: 4.95, h: 0.28,
      fontFace: B, fontSize: 10, color: MUTED, isTextBox: true, margin: 0,
    });
    s.addText(c.fix, {
      x: c.x + 0.35, y: 5.45, w: 4.95, h: 0.65,
      fontFace: B, fontSize: 11.5, italic: true, color: GOOD, isTextBox: true, margin: 0,
    });
  });
  note(s, "These two slides matter more than any speedup number, because they show the measurements were run and believed rather than assumed.");
}

// ---------------------------------------------------------------- 8. the map
{
  const s = pres.addSlide();
  titleSlide(s, "The map, and the scale question answered", "storage");
  table(
    s, MARGIN, 1.85, 7.4,
    ["", "attrs", "scrapy"],
    [
      ["Tests mapped", "1,334", "4,371"],
      ["Source files", "42", "328"],
      ["line → test rows", "508,939", { text: "1,723,636", options: { bold: true } }],
      ["Map size", "13.2 MB", { text: "47.5 MB", options: { bold: true } }],
      ["Instrumented suite", "2.2×", "1.63×"],
      ["Lookup p95", "—", { text: "1.41 ms", options: { bold: true, color: GOOD } }],
    ],
    [3.0, 2.2, 2.2], { rowH: 0.42 }
  );
  statCard(s, 8.4, 1.85, 4.2, "47.5 MB", "against a 500 MB budget", GOOD, "The reserve bitmap design stays on the shelf");
  statCard(s, 8.4, 3.72, 4.2, "1.41 ms", "p95 lookup, against 50 ms", GOOD, "Selection cost is irrelevant next to pytest startup");
  s.addText("“We measured it at X and it was acceptable, and here is the design we had ready if it had not been” is a stronger answer than an optimisation nobody needed.", {
    x: MARGIN, y: 5.7, w: 7.4, h: 0.9,
    fontFace: B, fontSize: 12.5, italic: true, color: MUTED, isTextBox: true, margin: 0,
  });
  note(s, "scrapy also settled the biggest flagged risk in the proposal: coverage contexts survive pytest-xdist and coverage combine, so the map can be built in parallel. The documented fallback to sequential construction was not needed.");
}

// ---------------------------------------------------------------- 9. demo
{
  const s = pres.addSlide();
  s.background = { color: INK };
  titleSlide(s, "Inspectable, not merely fast", "live demo — tia select --explain", true);
  s.addShape(pres.ShapeType.roundRect, {
    x: MARGIN, y: 1.85, w: 11.9, h: 3.15, rectRadius: 0.06,
    fill: { color: "0E1721" }, line: { width: 0 },
  });
  s.addText(
    [
      { text: "$ tia select --explain", options: { color: GOOD, breakLine: true } },
      { text: "", options: { breakLine: true } },
      { text: "src/attr/_funcs.py line 377", options: { color: PAPER, bold: true, breakLine: true } },
      { text: "  -> SELECTED: project source in a fresh map; tests chosen by line", options: { color: AMBER, breakLine: true } },
      { text: "     tests/test_funcs.py::TestAsDict::test_dicts", options: { color: "9FB3C2", breakLine: true } },
      { text: "     tests/test_funcs.py::TestAsDict::test_nested_lists", options: { color: "9FB3C2", breakLine: true } },
      { text: "     tests/test_hooks.py::TestAsDictHook::test_asdict", options: { color: "9FB3C2", breakLine: true } },
      { text: "     ... and 28 more", options: { color: "6B808F", breakLine: true } },
      { text: "", options: { breakLine: true } },
      { text: "tia: selected 31 of 1,334 tests", options: { color: PAPER, bold: true } },
    ],
    { x: MARGIN + 0.3, y: 2.05, w: 11.3, h: 2.8, fontFace: M, fontSize: 12.5, lineSpacing: 17, isTextBox: true, margin: 0 }
  );
  s.addText("Every selected test can be traced back to the line that pulled it in and the rule that allowed it. This is the differentiator: not that it is fast, but that you can check it.", {
    x: MARGIN, y: 5.2, w: 11.9, h: 0.8,
    fontFace: B, fontSize: 13.5, color: "AFC0CE", isTextBox: true, margin: 0,
  });
  s.addText("Then: edit requirements.txt → DEPENDENCY_CHANGED → full suite. The tool gives up the speed benefit on purpose.", {
    x: MARGIN, y: 5.95, w: 11.9, h: 0.5,
    fontFace: B, fontSize: 12.5, italic: true, color: AMBER, isTextBox: true, margin: 0,
  });
  note(s, "Demo runs on the real attrs checkout, needs no network, and the whole suite takes 3.9 seconds — so the full-suite comparison can be run live rather than quoted.");
}

// ---------------------------------------------------------------- 10. safety
{
  const s = pres.addSlide();
  titleSlide(s, "Safety validation: defects injected, one at a time", "the critical metric");
  s.addText("Each mutant is committed on a scratch branch so tia's ordinary git path runs. The full suite must fail — otherwise the mutant is equivalent and excluded. Then the selection runs. If it passes where the full suite failed, that is a miss.", {
    x: MARGIN, y: 1.7, w: 11.9, h: 0.55,
    fontFace: B, fontSize: 12.5, color: MUTED, isTextBox: true, margin: 0,
  });

  statCard(s, MARGIN, 2.35, 3.8, "0 / 47", "misses on attrs", GOOD, "50 mutants, seed 1234, 3 equivalent");
  statCard(s, 4.75, 2.35, 3.8, "0 / 14", "misses on scrapy", GOOD, "partial run of 17, recorded as incomplete");
  statCard(s, 8.8, 2.35, 3.8, "59.6%", "of attrs mutants fell back", AMBER, "50% on scrapy — all IMPORT_TIME_LINE");

  s.addChart(
    pres.ChartType.bar,
    [
      { name: "Full suite", labels: ["attrs", "scrapy"], values: [3.97, 45.95] },
      { name: "tia selection", labels: ["attrs", "scrapy"], values: [0.3, 2.62] },
    ],
    {
      x: MARGIN, y: 4.3, w: 7.3, h: 2.35,
      barDir: "col", showTitle: true, title: "Median wall clock, seconds",
      titleFontFace: B, titleFontSize: 12, titleColor: INK,
      chartColors: ["8FA3B0", GOOD],
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 10, dataLabelColor: INK,
      catAxisLabelColor: INK, valAxisLabelColor: MUTED,
      catAxisLabelFontFace: B, valAxisLabelFontFace: B,
      catAxisLabelFontSize: 11, valAxisLabelFontSize: 9,
      valGridLine: { color: RULE, size: 0.5 }, catGridLine: { style: "none" },
      showLegend: true, legendPos: "b", legendFontFace: B, legendFontSize: 10,
    }
  );

  s.addText("Read the two together", {
    x: 8.35, y: 4.35, w: 4.3, h: 0.32,
    fontFace: B, fontSize: 12, bold: true, color: INK, isTextBox: true, margin: 0,
  });
  s.addText("Zero misses is the result that matters. It is bought by giving up line-level selection on roughly 60% of changes — where tia is no faster than simply running everything. Both numbers are published; neither is an appendix.", {
    x: 8.35, y: 4.7, w: 4.3, h: 1.7,
    fontFace: B, fontSize: 12, color: INK, lineSpacing: 18, isTextBox: true, margin: 0,
  });
  note(s, "Two repositories, one run each, one of them partial. Not enough mutants to put a confidence interval on — that is Review 2 at 200+ per repository.");
}

// ---------------------------------------------------------------- 11. the miss
{
  const s = pres.addSlide();
  s.background = { color: INK };
  titleSlide(s, "The harness found a real miss", "and this is why it exists", true);

  s.addText(
    [
      { text: "First run on attrs: 1 miss in 46 non-equivalent mutants.", options: { color: PAPER, bold: true, breakLine: true, paraSpaceAfter: 10 } },
      { text: "The mutant forced `if ge is not None:` to `if True:` in src/attr/_cmp.py:88. The full suite caught it — six failures. tia selected two tests, and neither was among them.", options: { color: "CFDAE3", breakLine: true, paraSpaceAfter: 10 } },
      { text: "Root cause: tests/test_cmp.py calls cmp_using() at module level, so line 88 runs during collection. Coverage attributes import-time execution to no test at all. The six tests that depended on that line never appeared as covering it.", options: { color: "CFDAE3" } },
    ],
    { x: MARGIN, y: 1.8, w: 6.5, h: 2.9, fontFace: B, fontSize: 13, lineSpacing: 20, isTextBox: true, margin: 0 }
  );

  s.addShape(pres.ShapeType.roundRect, {
    x: 7.55, y: 1.8, w: 5.05, h: 2.55, rectRadius: 0.06,
    fill: { color: "0E1721" }, line: { width: 0 },
  });
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
    { x: 7.85, y: 2.0, w: 4.5, h: 2.2, fontFace: M, fontSize: 11, lineSpacing: 16, isTextBox: true, margin: 0 }
  );

  s.addShape(pres.ShapeType.roundRect, {
    x: MARGIN, y: 4.9, w: 11.9, h: 1.5, rectRadius: 0.08,
    fill: { color: "223141" }, line: { width: 0 },
  });
  s.addText("The fix, and the honesty it demands", {
    x: MARGIN + 0.35, y: 5.05, w: 11.2, h: 0.32,
    fontFace: B, fontSize: 12, bold: true, color: AMBER, isTextBox: true, margin: 0,
  });
  s.addText("The map now records import-time lines separately, and any change touching one falls back. Re-run at the same seed: 0 misses in 47 — and the fallback rate jumped to 59.6%. The rule is correct and expensive. We report both.", {
    x: MARGIN + 0.35, y: 5.38, w: 11.2, h: 0.9,
    fontFace: B, fontSize: 13, color: PAPER, lineSpacing: 19, isTextBox: true, margin: 0,
  });
  note(s, "This is the slide to spend time on. A safety claim is only as good as the experiment that could have falsified it — and this one did, on its first run.");
}

// ---------------------------------------------------------------- 12. honest cost
{
  const s = pres.addSlide();
  titleSlide(s, "The honest cost, and what fixes it", "fallback frequency");
  s.addText("Fallback is designed behaviour, so it is published as a headline result rather than hidden. On attrs, 28 of 47 mutants abandoned selection — every one of them for the same reason.", {
    x: MARGIN, y: 1.72, w: 11.9, h: 0.55,
    fontFace: B, fontSize: 13, color: MUTED, isTextBox: true, margin: 0,
  });

  s.addChart(
    pres.ChartType.doughnut,
    [{ name: "attrs mutants", labels: ["Line-level selection", "Fell back — IMPORT_TIME_LINE"], values: [19, 28] }],
    {
      x: MARGIN, y: 2.35, w: 5.2, h: 3.4,
      showTitle: true, title: "attrs: 47 non-equivalent mutants",
      titleFontFace: B, titleFontSize: 12, titleColor: INK,
      chartColors: [GOOD, AMBER], holeSize: 55,
      showLegend: true, legendPos: "b", legendFontFace: B, legendFontSize: 10,
      showValue: true, dataLabelFontSize: 11, dataLabelColor: "FFFFFF",
    }
  );

  s.addText("What it means", {
    x: 6.3, y: 2.4, w: 6.3, h: 0.32,
    fontFace: B, fontSize: 13, bold: true, color: INK, isTextBox: true, margin: 0,
  });
  s.addText(
    [
      { text: "On roughly 60% of changes to attrs, tia runs the whole suite — it is safe, and it is no faster than not using it.", options: { bullet: true, breakLine: true } },
      { text: "Every one of those fallbacks is IMPORT_TIME_LINE: a changed line that also ran during import, which coverage cannot attribute to any test.", options: { bullet: true, breakLine: true } },
      { text: "This is not a bug to hide. It is the measured price of the rule that removed our only known miss.", options: { bullet: true, breakLine: true } },
      { text: "It also reframes Phase 2: the import graph is not an enhancement, it is what makes the safe version worth running. It can name the modules that imported a file and select their tests, instead of surrendering to the full suite.", options: { bullet: true } },
    ],
    { x: 6.3, y: 2.8, w: 6.3, h: 3.3, fontFace: B, fontSize: 12.5, color: INK, lineSpacing: 19, paraSpaceAfter: 9, isTextBox: true, margin: 0 }
  );
  note(s, "A reviewer who asks 'did you get the 40-70% you targeted?' gets this slide: the distribution, the reason, and what we would do about it.");
}

// ---------------------------------------------------------------- 13. scope + next
{
  const s = pres.addSlide();
  titleSlide(s, "Where this stands", "review 1 close-out");

  const cols = [
    {
      x: MARGIN, head: "Delivered", color: GOOD,
      items: [
        "Installable CLI + pytest plugin, working end to end",
        "Map, git diff, safety classifier, line-level selection",
        "Evaluation harness: corpus, baselines, defect injection",
        "Two real codebases; every figure from committed JSON",
        "115 tests, mypy --strict clean, 13 commits",
        "SAFETY.md, 11 dated decision records, 6-minute demo",
      ],
    },
    {
      x: 4.85, head: "Explicitly out of scope", color: MUTED,
      items: [
        "Import graph for indirect dependencies (Phase 2)",
        "Third corpus repository",
        "PyPI publication",
        "CI pipeline integration demo",
        "Safety at 200+ mutants per repository",
        "Incremental map updates",
      ],
    },
    {
      x: 9.0, head: "Next, in priority order", color: ACCENT,
      items: [
        "Import graph — to cut the 60% fallback rate",
        "Safety at scale: 200+ mutants, both repos",
        "Fallback frequency over real historical commits",
        "Selection precision measurement",
        "Third repo (black) and PyPI packaging",
        "Reproducibility artefact: make reproduce",
      ],
    },
  ];
  cols.forEach((c) => {
    s.addText(c.head, {
      x: c.x, y: 1.8, w: 3.6, h: 0.35,
      fontFace: B, fontSize: 13, bold: true, color: c.color, isTextBox: true, margin: 0,
    });
    s.addText(
      c.items.map((t, i) => ({
        text: t,
        options: { bullet: true, breakLine: i !== c.items.length - 1 },
      })),
      { x: c.x, y: 2.2, w: 3.6, h: 3.3, fontFace: B, fontSize: 11.5, color: INK, lineSpacing: 17, paraSpaceAfter: 8, isTextBox: true, margin: 0 }
    );
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: MARGIN, y: 5.7, w: 11.9, h: 1.0, rectRadius: 0.08,
    fill: { color: INK }, line: { width: 0 },
  });
  s.addText("A negative or mixed result, properly measured, is a valid finding. We report 0 misses and a 60% fallback rate — and we say which one is the achievement and which is the bill.", {
    x: MARGIN + 0.35, y: 5.92, w: 11.2, h: 0.6,
    fontFace: H, fontSize: 15, bold: true, italic: true, color: PAPER, isTextBox: true, margin: 0,
  });
  note(s, "Say the out-of-scope list out loud before the panel finds it. Line-level precision exists; the import graph, the third repo and PyPI are Review 2.");
}

pres.writeFile({ fileName: process.argv[2] || "tia-review-1.pptx" }).then((f) => console.log("wrote", f));
