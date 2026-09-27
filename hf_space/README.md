---
title: Course Planner Manim Renderer
emoji: 🎬
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Course Planner — Manim Renderer (Hugging Face Space)

A small free server that turns a math/physics prompt into a rendered **Manim** MP4. Your
Course Planner site calls it from **Study Tools → Video Lesson**. The pipeline is two-pass:
Gemini first designs the lesson as a spec, then writes a full `MainScene` script from it;
render failures feed the error back for repair attempts (default 4, `MAX_REPAIRS`).

The MP4 is **intentionally silent** — there is no server-side TTS or audio mux. The scene's
subcaption timeline is returned as a structured `captions` array (`{text, start}`) and the
site renders closed captions and speaks each beat with the browser's own
`window.speechSynthesis` while the video plays.

## API

Renders are **non-blocking**: `POST /generate` starts a background job and returns
immediately; the site polls for progress and then streams the finished video.

- `GET /health` → `{"status": "ok", ...}` plus model info — the site pings this to
  wake/check the Space.
- `POST /generate` with body `{"prompt": "...", "subject": "...", "question": "...", "mode": "..."}`
  → `{"job_id": "..."}`. Only `prompt` is required. Returns `429` while another render is
  active (`MAX_ACTIVE_JOBS`, default 1) and `4xx` JSON errors for missing/oversized input.
- `GET /status/{job_id}` → `{"status", "progress", "result", "error"}`. On `"done"`,
  `result` is `{"video_url": "/video/<job_id>.mp4", "captions": [...], "filename"}`.
  If all repair attempts fail, `status` is `"error"` with the reason in `error`.
- `GET /video/{name}` → the silent MP4 (supports Range requests, so `<video>` can seek).
- `GET /diagnostics` → key/model configuration probe. **It spends Gemini quota — don't poll it.**

Jobs and their MP4s are kept in memory/tmp and cleaned up after ~1 hour; download a video if
you want to keep it.

Gemini keys are read from the **`GEMINI_API_KEY`** Space secret (plus optional
`GEMINI_API_KEY_2` / `_3` / `_4` — calls rotate across all configured keys, and a rate-limited
key advances to the next). **No key is stored in these files.**

---

## One-time setup (about 10–15 minutes, all free)

You'll do this once. None of it costs money — it uses Hugging Face's free CPU tier.

### 1. Create the Space
1. Go to **https://huggingface.co/new-space** (sign in / create a free account first).
2. **Space name:** anything, e.g. `course-planner-manim`.
3. **License:** leave default.
4. **Select the Space SDK:** choose **Docker** → **Blank**.
5. **Hardware:** leave it on the free **CPU basic**.
6. **Visibility:** Public is fine.
7. Click **Create Space**.

### 2. Add your Gemini key as a secret
1. In the new Space, open the **Settings** tab.
2. Scroll to **Variables and secrets** → click **New secret**.
3. **Name:** `GEMINI_API_KEY` (exactly).
4. **Value:** paste your free key from https://aistudio.google.com/app/apikey
5. Save. (A *secret*, not a *variable* — secrets are hidden and not shown in logs.)
6. Optional: add `GEMINI_API_KEY_2` / `_3` / `_4` the same way to spread quota across keys.

### 3. Upload these files
Upload the **contents of this `hf_space/` folder** to the Space (not the folder itself) — so the
Space's root has `Dockerfile`, `app.py`, `requirements.txt`, and `README.md` directly.

Easiest way (in the browser):
1. In the Space, open the **Files** tab → **+ Add file** → **Upload files**.
2. Drag in `Dockerfile`, `app.py`, `requirements.txt`, and this `README.md`.
3. Click **Commit changes to main**.

(If you prefer git, the Space page's **"Clone repository"** button shows the exact `git` commands.)

### 4. Wait for it to build
- The Space will show **"Building"** — the first build takes several minutes (it installs LaTeX).
- When it shows **"Running"**, click the **App** tab. You should see FastAPI's default page, and
  visiting `…/health` should show `{"status":"ok", ...}`.

### 5. Connect it to your site
1. Copy your Space's URL. It looks like `https://YOUR-NAME-course-planner-manim.hf.space`
   (the **"Embed this Space" / direct URL**, NOT the `huggingface.co/spaces/...` page URL).
2. In `index.html`, find the line:
   ```js
   const HF_SPACE_URL = "https://YOUR-SPACE.hf.space";
   ```
3. Replace the placeholder with your real URL (no trailing slash). Commit and deploy.
4. On the site, open **Study Tools → Video Lesson** and Generate.

---

## Notes & expectations (free tier)
- **Cold start:** the Space **sleeps after ~48h idle**. The first request wakes it (~30s). The
  site shows a "Waking up the renderer…" message and waits.
- **Speed:** CPU rendering is slow — a short clip takes roughly **2–5 minutes**. The site polls
  `/status/{job_id}` and shows live progress.
- **Storage is temporary:** finished MP4s are served from the Space for about an hour, then
  cleaned up with their job. Use the site's download button to keep one (the downloaded file is
  silent — narration is browser speech, not an audio track).
- If a render still fails after all repair attempts, `/status/{job_id}` reports
  `"status": "error"` and the site surfaces the message.

## Test it from your computer (optional)
```bash
curl https://YOUR-SPACE.hf.space/health
# -> {"status":"ok", ...}

curl -X POST https://YOUR-SPACE.hf.space/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"explain the dot product of two vectors","subject":"Linear Algebra"}'
# -> {"job_id":"<id>"}

curl https://YOUR-SPACE.hf.space/status/<id>
# poll until -> {"status":"done", ..., "result":{"video_url":"/video/<id>.mp4", ...}}

curl -o test.mp4 https://YOUR-SPACE.hf.space/video/<id>.mp4
```
