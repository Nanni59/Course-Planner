---
title: Course Planner TikZ Renderer
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Course Planner TikZ Renderer

TikZ is a separate Hugging Face Docker Space for static textbook-style visuals.
It compiles constrained TikZ snippets into SVG or PNG for Course Planner study
tools.

## API

### `GET /health`

Returns service status, tool availability, and `catalog_available`,
`catalog_enabled`, and `elementary_available` so a missing template engine is visible.

### `POST /render`

Request:

```json
{
  "code": "\\draw[cp axis] (-3,0) -- (3,0) node[right] {$x$};",
  "format": "svg",
  "theme": "green",
  "target": "slide"
}
```

Response:

```json
{
  "ok": true,
  "format": "svg",
  "mime": "image/svg+xml",
  "svg": "<svg ...></svg>"
}
```

PNG requests return base64:

```json
{
  "ok": true,
  "format": "png",
  "mime": "image/png",
  "base64": "..."
}
```

Add `"layout": true` to also get a label-collision report for the rendered
picture (see Layout check below):

```json
"layout": {"labels": 9, "issues": [{"kind": "line-through-label", "labels": ["x = ?"], "ink": 30}]}
```

### `POST /generate`

Starts a background job. Supported, fully specified elementary setups (a named
right triangle with two given legs, a two-point coordinate midpoint problem,
an external circle tangent, a central/inscribed-angle circle theorem, a block
with four cardinal forces, and an explicitly bounded quadratic graph) use validated
numerical geometry without Gemini. Unsupported setups use the existing catalog
fit/parameter path, then reference-guided generation with one repair.

The circle-theorem renderer accepts one named central angle with a value from
20 to 160 degrees and one requested inscribed angle intercepting the same two
points. All three outer points must be stated to lie on the circumference and
the centre must be named. It always draws the smaller interior sectors. Reflex,
exterior, tangent/secant, or ambiguous multi-angle constructions use the verified
model-assisted path instead.

Quadratics accept standard-form `y = ax^2 + bx + c` with finite integer/decimal
coefficients, omitted terms, `x²` or `x^{2}`. Supply an explicit domain such as
`-3 <= x <= 3` (also LaTeX `\le`), `domain [-3,3]`, or `x-axis from -3 to 3`,
and `y-axis from -6 to 5`. Axis spans are limited to 40 units and absolute bounds
to 1000. No arbitrary expressions are evaluated. Conflicting repeated givens,
unsupported expressions or requested extra constructions fall back to the
existing verified model path. Quadratic diagrams show no solved-point labels.

Worksheet questions optionally carry `solutionSteps: string[]` alongside the
required `answer`. New answer keys render each step separately and then the final
answer; older answer-only worksheets remain supported. Feedback exports retain
these steps without sending them to the diagram backend. Network failures are
recorded as `model-network-error` events; a verifier outage remains a failure.

Worksheet drawing instructions belong in `visualDescription` in the frontend's
question data. The frontend sends them together with the question, never its answer.
An older `Diagram: Draw/Show/Plot/...` suffix is hidden in the student view but
retained in the generation request and feedback export.

Request:

```json
{
  "title": "Derivative as slope of a tangent",
  "brief": "Show a curve, a point on the curve, and a tangent line at that point.",
  "subject": "Calculus",
  "equation": "f'(a)",
  "format": "svg",
  "theme": "green",
  "target": "slide"
}
```

Response:

```json
{
  "job_id": "...",
  "status": "pending"
}
```

### `GET /status/{job_id}`

Poll until `status` is `completed` or `failed`. Completion includes `svg` (or
`base64` for PNG), `job_id`, `source`, and bounded per-job `diagnostics` with stages,
template IDs, model attempts, and available error details. Failure includes `error`
and the same diagnostic trail. No API keys or full request prompts are included.

So a failure can be reproduced from the trace alone, a `catalog-params` event
holds a catalog template's final parameter values. `render-error`, `layout`,
`readiness` (passed or failed), `semantic-rejection` and `catalog-render-error`
events for model-drawn code carry a `tikz` field with that attempt's drawing code
(whitespace collapsed, head and tail of long code, at most 2400 characters per
event and 6000 per job). `layout-alternative` events appear only for templates
with several label placements ("placement 2 of 5 collides", then "no clean
placement; kept placement ..." when none is clean). `readiness` events also name
the `model` that gave the verdict and whether it was sent the `picture`.

The worksheet's Report issue JSON preserves this information. It does not label
every failure as a rate limit. Custom TikZ readiness is checked by a Gemini call
that reads the drawing code and, on Gemini models, looks at a small rendered PNG
of it (Gemma models read the code alone; a request refused with the picture is
retried once without it). Values the question states may be labelled; only values
the student must find have to be a symbol or ?, and guide lines or tick labels that
locate an unknown point count as revealing it. An unavailable verifier never
counts as success. Template parameter failures do not render invented default
givens. `/render` returns that PNG as `preview_png` when asked with
`"preview": true`.

Every diagram gets this check, not only custom TikZ: catalog templates and the
exact (`elementary:`) renderers are checked the same way before they ship, and
their `readiness` events carry `path` (`catalog` or `elementary`). The check
also asks whether the diagram is drawn to its givens (the larger of two labelled
lengths drawn longer, in about their ratio; an angle looks like its label; each
given on the side or angle the question names). Its prompt carries a code check
of the label text: labels with a number the question does not state, and
measurements the question states that no label shows, passed on as leads for the
verifier to rule on. Verdicts come from Flash-class models only (never
Flash-Lite or Gemma, unless nothing else is configured). A catalog diagram that
fails gets one parameter refill with the reason, then goes to the
reference-guided path; with no verifier available it is blank. An exact
renderer's diagram that fails goes to the next path, and ships unchecked when no
verifier is available (its drawing uses no model).

Verdicts separate mathematics from looks: `FAIL` (wrong mathematics, not drawn to
its givens, a revealed answer, an unreadable label), `COSMETIC` (correct and safe,
but ticks, grid or label spacing are off) or `PASS`. A cosmetic model drawing gets
one repair; the repair ships if it is at least as good, otherwise the correct draft
does (`readiness-cosmetic` / `layout-choice` events). A catalog or exact diagram
judged cosmetic ships. Only a mathematical failure, or no verifier at all, leaves
a question blank. When the question sends the student to its graph ("the graph
below shows ..."), the sinusoid template draws the bare curve (no amplitude or
period arrows, no midline) with unit ticks and a grid, read from the described
maximum and minimum.

A model drawing gets up to three drafts, at most two of them judged by the
verifier (a draft and one repair after a verdict): a draft that does not compile
or breaks a code rule costs no verifier call, and no longer spends the repair.
The verifier's reply is read in its own words too ("Version B is READY." counts
as `PASS B`; it once blanked a diagram the verifier had passed).

A rational function the question gives (`f(x) = (2x^2 - 8)/(x^2 - x - 6)`,
`rac{3x^2 + 5x - 4}{x + 2}`) is drawn by the exact `rational_function` renderer,
with no model: vertical, horizontal or slant asymptotes found from the
polynomials, dashed and labelled `?`; holes as open circles; intercepts unmarked.
It declines inequalities, empty-grid requests, two different functions, and
functions with no line asymptote.

## Hugging Face Setup

1. Create a new Hugging Face Space.
2. Choose Docker as the Space SDK.
3. Upload this folder, including `Dockerfile`, `app.py`, `requirements.txt`,
   `templates.py`, and the complete `catalog/` directory.
4. Add `GEMINI_API_KEY` as a Space secret if you want server-side visual
   generation through `/generate`. Optional extra secrets:
   `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`, `GEMINI_API_KEY_4`. Free-tier
   quota belongs to the Google Cloud project, so extra keys only add quota
   when each comes from a different project (in AI Studio, create each key
   in a new project).
5. Optionally set `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS` as Space
   variables. The default model order is `gemini-3.8-flash`,
   `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`,
   `gemini-3-flash-preview`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`,
   `gemini-2.5-flash`, `gemini-2.5-flash-lite` (both announced to shut down in
   October 2026), then the hosted Gemma models `gemma-4-31b-it` and
   `gemma-4-26b-a4b-it`. Free-tier quota is counted per model as well as per
   project, so each model adds its own daily allowance; the Flash models allow
   few requests a day, the Flash-Lite and Gemma models far more. Gemma is asked
   without JSON mode, and a request Gemma refuses rests Gemma only. A Space
   variable replaces this list entirely.

### How keys and models are used

Each key slot paired with each model is a lane. A 429 quota response rests
only that lane, for Google's `retryDelay` (an hour for a per-day quota). A 503
"high demand" response rests that model on every key for 30 s, doubling while
it keeps failing (at most 5 minutes). A rejected key rests all of its lanes.
Requests go to the preferred model's least-used ready key, so parallel jobs
spread across keys. When every lane is resting, a call waits up to
`GEMINI_MAX_WAIT` seconds (default 60) for the first one to recover, then fails
closed. `/health` lists each lane's readiness and last outcome, without keys.
6. Wait for the Space to build.
7. Test `/health`.

The frontend can then use:

```js
const TIKZ_SPACE_URL = "https://yourname-tikz-renderer.hf.space";
```

## Layout check

Every catalog, exact and model-drawn diagram is checked in its rendered form
for labels that a line, curve or axis runs through, labels that overlap each
other, and labels covered by something drawn after them. The readiness
verifier looks at a small picture, which is no reliable way to find these.

How it works: the compiled document gets a second page with the same picture
and every node's text invisible (fills kept). Page 1 logs each node's corners
and inner sep (so rotated labels are exact), ink inside a label's text box on
page 2 is a line crossing it, white-backed tick labels correctly count as
clear, and `pdftotext` supplies the label text for reports. It costs one extra
page in the same pdflatex run and two small greyscale rasters (0.03-0.3 s).
If the instrumented compile fails, the diagram is compiled plainly and ships
without a report. `TIKZ_LAYOUT_CHECK=0` turns the check off.

What happens with a report:

- Model-drawn diagrams spend their one repair on the collisions (the prompt
  names each label). The draft and the repair then get one readiness verdict
  together (codes, pictures and each one's label report; the one with fewer
  collisions is version A, the repair on a tie), which names the version to
  ship ("PASS A" or "PASS B") or fails both. Separate verdicts once failed a
  label in the repair and passed the same label in its draft. A
  `layout-choice` event says when the draft shipped, including when the repair
  produced no usable drawing.
- Model code has hyphenated TikZ option names fixed before compiling
  (`line-width=` becomes `line width=`; TikZ read the typo as an arrow tip).
- A model's JSON reply has TeX backslashes restored before it is parsed: an
  unescaped `\tiny` came back as a tab and "iny", `\node` as a line break and
  "ode". `\b` and `\f` are always commands; `\t`, `\n`, `\r` only as known
  command names; an escape JSON does not define (`\draw`) is a command too.
- Catalog templates can list candidate label placements in
  `layout_alternatives` (TikZ fragments substituted for the skeleton's
  `@@ALT@@` slot, wherever it appears, preferred first). The renderer tries
  them in order only when the default collides, and keeps the first clean one
  (else the one with the fewest collisions). The model never sees them.
- Otherwise the report is recorded as a `layout` diagnostic.

`python tools/tikz_layout_check.py --variants` audits the whole catalog, the
exact renderers and a set of value variants with the real compiler, at the
worksheet scale-up the backend applies (1.22), and converts each chosen
placement to SVG, as worksheets ship it, to catch one that exceeds the size limit.

The wrapper defines two label macros templates use: `\cpanglelabel{vertex}{direction}{mark radius}{half gap}{text}`
puts an angle label on its direction past its mark by its measured extent and
clear of both sides of its gap (it leaves the label's inner and outer radius in
`\cplabelin` / `\cplabelout` for arcs drawn after it), and
`\cpsidelabel[margin]{P}{Q}{R}{fraction}{text}` puts a label beside segment PQ on
the side away from R by its measured extent. Both measure in picture units,
without inner sep, so the worksheet scale-up and the check agree.

Shapes follow the question's numbers, computed by the backend rather than the
model (the model's values are kept only when the question does not settle them):

- The general triangle is solved from its givens (SSS, SAS, SSA, or two
  angles). The largest angle goes on top so the base is the longest side, and
  every label comes from the question: givens with their values, the side or
  angle asked for with the brief's symbol (else its own letter or ?), and
  nothing on the rest. An angle is marked only when it is labelled.
- The right triangle draws its given angle at its size. An angle with the wall
  or the vertical is marked at the top.
- The two-object bearing legs are in proportion to their distances (or to the
  speeds when both travel for the same time). A leg shows a distance only when
  the question states it, else its speed or a symbol: speed times time is the
  student's step.
- A sinusoid's arrows carry the symbols A, P and midline whenever the question
  asks for its amplitude, period, midline, range, maximum or minimum.
- A sinusoid's A, B, C and D are read from its equation, with a cosine
  converted to the sine form the template plots. A diagram description that
  repeats the equation is fine; two different equations are left to the model.
- A definite integral takes its bounds and stated function from the question.
  When the question only says where the curve crosses the x-axis, a model curve
  that crosses elsewhere, or on the wrong side of the axis, is replaced by one
  that matches. Area below the axis is a darker grey than area above it (a
  hatch pattern made the SVG too large to ship).
- A related-rates circle and a boat crossing read their rates from the question.
- An inequality's number line (`number_line_blank`) carries ticks only, since
  the boundary circle and the arrow are the answer. The template is marked
  `always_fits`, so the model cannot veto it (it once did because the brief
  asked for the circle). A question that asks for a solution on a number line
  never falls back to a model drawing: blank beats the answer. The readiness
  rules fail a drawn solution even when the description asks for one.
- Labels show only numbers the question states (the strict rule). Params marked
  `stated_only` become ? on worksheets when they hold any other number: Venn
  region counts (13 from 18 - 5 was the answer to "only soccer") and tree
  branch probabilities (3/9 on a second draw). The optimization rectangles
  carry x and y only, with no constraint equation. The readiness rules fail
  a model drawing that labels such a value, and the worksheet writer is told
  not to ask for one.
- Two curves and the region between them (`area_between_curves`): both curves
  from the question with a legend, shading only between the crossings (pgfplots
  fillbetween), and no label or guide line at a crossing. The axes are drawn on
  top of the fill (`axis on top`; fillbetween's layer hid them), and the window
  leaves headroom above the curves.
- A tangent line's label spot is clamped to where the line runs inside the
  window (a spot outside it dropped the label).
- Model TikZ with a node group that opens math and never closes it
  (`{$6\text{ cm}}`) gets the missing `$` before compiling.
- An accumulation function F(x) = integral of f(t) from a to x uses the shaded
  integral with a t axis, the endpoint labelled x and F(x) inside the area.
- A label with maths but no $...$ in a text slot (`f(x) = 2^x`) is wrapped in
  math mode; the inverse template failed to compile on one. Plot expressions
  (no "=" or TeX command) stay bare.
- A linear system to solve graphically routes to the two-function template:
  both lines from the question, a legend, and no label at their crossing.
- The two-leg bearing legs are in proportion (the shorter at least 0.45 of the
  longer) and labelled beside themselves.
- Tick labels stay off marked points: at a piecewise break or a point of
  tangency just below the axis the tick label goes above it, a rational
  function has no tick at the window's edge (under the asymptote label), and a
  definite integral's tick label goes above the axis where the area is below
  it. A sinusoid's axis takes the question's variable, with ticks every pi for
  long periods.
- A number and unit in a math label (`5 m`) are set upright (`5\,\mathrm{m}`).

Catalog renders skip the semantic checks written for model drawings. The
template's structure is fixed; only its values are filled. Since 2026-09-28 no
drawing is rejected for raw arc paths or angle marks over 7mm in triangles or
vector diagrams (the picture check judges where a mark lands; these rules
blanked correct polar, unit-circle and coordinate diagrams), and a vertex label
written with its coordinates (`A(2,0,0)`) counts as that vertex.

Template params may be `local` (the model never sees them; overrides set them)
or `flag_of` another slot (1 when that label is non-empty, for marks drawn only
with their label). A label arriving with doubled backslashes (`4\\,\\mathrm`) is
repaired. The answer guard judges the value after "=": a stated rate such as
dr/dt = 3 cm/s stays, and a \frac, \sqrt or rate value the question does not
state becomes ?.

The "covered or cut off" test needs two characters on one text line before it
checks how much of its box a label's glyphs span, so a stacked one-digit
fraction such as 3/9 is not reported.

## Safety Model

The service does not accept full LaTeX documents from Gemini. It wraps a TikZ
snippet in a locked template and rejects commands that can read files, write
files, import packages, shell out, or externalize graphics.

Compilation uses:

```bash
pdflatex -interaction=nonstopmode -halt-on-error -no-shell-escape
```

Each render also has a timeout and output-size cap.

## Example TikZ

```tex
\begin{tikzpicture}
  \draw[cp axis] (-3,0) -- (3,0) node[right] {$x$};
  \draw[cp axis] (0,-1) -- (0,5) node[above] {$y$};
  \draw[cp line, domain=-2:2, samples=80] plot (\x, {\x*\x});
  \node[cp label] at (1.8,3.6) {$y=x^2$};
\end{tikzpicture}
```
