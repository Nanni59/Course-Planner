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

Returns service status and whether the required command-line tools are present.

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

## Hugging Face Setup

1. Create a new Hugging Face Space.
2. Choose Docker as the Space SDK.
3. Upload this folder's files: `Dockerfile`, `app.py`, `requirements.txt`.
4. Wait for the Space to build.
5. Test `/health`.

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
