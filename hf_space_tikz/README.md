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

### `POST /generate`

Starts a background job. Supported, fully specified elementary setups (a named
right triangle with two given legs, a two-point coordinate midpoint problem,
an external circle tangent, and a block with four cardinal forces) use validated
numerical geometry without Gemini. Unsupported setups use the existing catalog
fit/parameter path, then reference-guided generation with one repair.

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

The worksheet's Report issue JSON preserves this information. It does not label
every failure as a rate limit. Custom TikZ readiness is a source-code check, not an
image inspection; an unavailable verifier no longer counts as success. Template
parameter failures do not render invented default givens.

## Hugging Face Setup

1. Create a new Hugging Face Space.
2. Choose Docker as the Space SDK.
3. Upload this folder, including `Dockerfile`, `app.py`, `requirements.txt`,
   `templates.py`, and the complete `catalog/` directory.
4. Add `GEMINI_API_KEY` as a Space secret if you want server-side visual
   generation through `/generate`. Optional fallback secrets:
   `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`, `GEMINI_API_KEY_4`.
5. Optionally set `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS` as Space
   variables. The default model order is `gemini-3-flash-preview`,
   `gemini-3.5-flash`, then `gemini-2.5-flash`.
6. Wait for the Space to build.
7. Test `/health`.

The frontend can then use:

```js
const TIKZ_SPACE_URL = "https://yourname-tikz-renderer.hf.space";
```

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
