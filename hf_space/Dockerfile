# Course Planner — Manim renderer (Hugging Face Docker Space)
# Installs the SAME pinned Manim + LaTeX stack as tools/manim_video_tool.ipynb,
# plus a small FastAPI server (app.py). Runs on the free CPU tier.
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp \
    XDG_CACHE_HOME=/tmp

# System deps: Cairo/Pango (Manim rendering), ffmpeg (video), and a LaTeX subset
# (so MathTex / equations render — not just plain shapes).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config \
        libcairo2-dev libpango1.0-dev ffmpeg dvisvgm \
        texlive texlive-latex-extra texlive-fonts-extra \
        texlive-latex-recommended texlive-science tipa \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Narration is no longer synthesised on the server: the rendered MP4 is intentionally silent
# and the browser speaks the returned `captions` timeline via window.speechSynthesis. No
# Kokoro model is baked in (that removed a ~340 MB build-time download).

COPY app.py .

# Hugging Face Spaces serve the app on port 7860 by default.
EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
