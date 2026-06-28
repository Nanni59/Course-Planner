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
Course Planner site calls it for STEM / Science video lessons when you choose the "Manim video"
option. The same render-and-repair loop as `tools/manim_video_tool.ipynb`, but on demand.

It exposes two endpoints:

- `GET /health` → `{"status": "ok"}` — the site uses this to check the Space is awake.
- `POST /generate` with body `{"prompt": "...", "subject": "..."}` → returns the rendered MP4
  (or a JSON error if all 3 repair attempts fail).

The Gemini key is read from the **`GEMINI_API_KEY`** environment variable. **No key is stored
in these files.**

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
  visiting `…/health` should show `{"status":"ok"}`.

### 5. Connect it to your site
1. Copy your Space's URL. It looks like `https://YOUR-NAME-course-planner-manim.hf.space`
   (the **"Embed this Space" / direct URL**, NOT the `huggingface.co/spaces/...` page URL).
2. In `index.html`, find the line:
   ```js
   const HF_SPACE_URL = "https://YOUR-SPACE.hf.space";
   ```
3. Replace the placeholder with your real URL (no trailing slash). Commit and deploy.
4. On the site, open **Study Tools → Video Lesson**, pick **Subject = STEM or Science**, and the
   **"Manim video"** option appears. Choose it and Generate.

---

## Notes & expectations (free tier)
- **Cold start:** the Space **sleeps after ~48h idle**. The first request wakes it (~30s). The
  site shows a "Waking up the renderer…" message and waits.
- **Speed:** CPU rendering is slow — a short clip takes roughly **2–5 minutes**.
- **Storage is temporary:** the MP4 is streamed back in the response and not kept on the Space.
  To keep a video permanently, download it and add it to the repo's `videos/` folder (then run
  `python update_manifest.py`) — it'll appear in the site's **Video Library**.
- If a render fails after 3 repair attempts, `/generate` returns a JSON error and the site falls
  back to the instant animated-slides lesson.

## Test it from your computer (optional)
```bash
curl https://YOUR-SPACE.hf.space/health
# -> {"status":"ok"}

curl -X POST https://YOUR-SPACE.hf.space/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"explain the dot product of two vectors","subject":"Linear Algebra"}' \
  --output test.mp4
# -> saves test.mp4 if it worked
```
