"""Run broad TikZ visual-generation regression cases.

Default mode hits the same local HTTP API that the front end uses:

    python tools/tikz_visual_regression.py --backend http://127.0.0.1:7860

For quick code-level checks without a running backend:

    python tools/tikz_visual_regression.py --local-catalog

The output folder contains result JSON, SVG files, and an index.html contact
sheet that can be opened locally for visual inspection.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "tools" / "tikz_visual_regression_cases.json"
DEFAULT_OUT = ROOT / "tmp" / "tikz-visual-regression"


def _post_json(url: str, payload: dict[str, Any], timeout: float = 20) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, timeout: float = 20) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _case_payload(case: dict[str, Any]) -> dict[str, Any]:
    brief = str(case["brief"])
    return {
        "subject": case.get("subject", "General"),
        "title": case.get("question", brief),
        "brief": brief,
        "question": brief,
        "equation": case.get("equation", ""),
        "format": "svg",
        "theme": case.get("theme", "green"),
        "target": "worksheet",
    }


def _run_backend_case(base_url: str, case: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    started = time.time()
    payload = _case_payload(case)
    job = _post_json(base_url.rstrip("/") + "/generate", payload)
    job_id = job["job_id"]
    status_url = base_url.rstrip("/") + f"/status/{job_id}"
    last: dict[str, Any] = {"status": "pending", "svg": "", "error": ""}
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(0.8)
        last = _get_json(status_url)
        if last.get("status") in {"completed", "failed"}:
            break
    ok = last.get("status") == "completed" and bool(last.get("svg"))
    return {
        **case,
        "ok": ok,
        "mode": "backend",
        "job_id": job_id,
        "status": last.get("status", "timeout"),
        "svg": last.get("svg", ""),
        "svg_len": len(last.get("svg", "")),
        "error": last.get("error", ""),
        "elapsed_s": round(time.time() - started, 2),
    }


def _run_local_catalog_case(case: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "hf_space_tikz"))
    sys.path.insert(0, str(ROOT / "hf_space_tikz" / "catalog"))
    from hf_space_tikz.app import GenerateReq, _catalog_generate  # noqa: PLC0415

    req = GenerateReq(**_case_payload(case))
    result = _catalog_generate(req)
    ok = bool(result and result.get("svg"))
    status = "completed" if ok else "no_catalog_route_or_render_failed"
    if not ok and "divergent" in str(case.get("kind", "")):
        ok = True
        status = "ai_required_no_catalog_route"
    return {
        **case,
        "ok": ok,
        "mode": "local-catalog",
        "status": status,
        "customized": (result or {}).get("customized", ""),
        "caption": (result or {}).get("caption", ""),
        "svg": (result or {}).get("svg", ""),
        "svg_len": len((result or {}).get("svg", "")),
        "error": (result or {}).get("error", ""),
        "elapsed_s": round(time.time() - started, 2),
    }


def _write_outputs(results: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    compact: list[dict[str, Any]] = []
    for result in results:
        svg = result.pop("svg", "")
        svg_name = f"{result['id']}.svg"
        if svg:
            (out_dir / svg_name).write_text(svg, encoding="utf-8")
            result["svg_file"] = svg_name
        compact.append(result)
    (out_dir / "results.json").write_text(json.dumps(compact, indent=2), encoding="utf-8")

    cards = []
    for result in compact:
        status = "ok" if result.get("ok") else "bad"
        img = (
            f'<img src="{html.escape(result["svg_file"])}" alt="{html.escape(result["id"])}">'
            if result.get("svg_file")
            else '<div class="missing">No SVG</div>'
        )
        meta = " / ".join(
            html.escape(str(x))
            for x in [
                result.get("branch", ""),
                result.get("subject", ""),
                result.get("kind", ""),
                result.get("customized", "") or result.get("status", ""),
            ]
            if x
        )
        cards.append(
            f"""
<section class="card {status}">
  <div class="meta"><strong>{html.escape(result['id'])}</strong><span>{meta}</span></div>
  <p>{html.escape(result.get('brief', ''))}</p>
  {img}
  <small>{html.escape(result.get('error', ''))}</small>
</section>"""
        )
    page = f"""<!doctype html>
<meta charset="utf-8">
<title>TikZ Visual Regression</title>
<style>
body {{ margin: 0; font: 14px/1.35 system-ui, Segoe UI, Arial, sans-serif; background: #f5f6f3; color: #1f2729; }}
header {{ position: sticky; top: 0; background: #fff; border-bottom: 1px solid #d9dedb; padding: 14px 18px; z-index: 1; }}
h1 {{ margin: 0; font-size: 18px; }}
main {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 14px; padding: 14px; }}
.card {{ background: #fff; border: 1px solid #d9dedb; border-radius: 8px; padding: 12px; }}
.bad {{ border-color: #b84a4a; }}
.meta {{ display: flex; gap: 8px; flex-wrap: wrap; color: #526064; }}
p {{ min-height: 56px; margin: 8px 0 10px; }}
img {{ display: block; width: 100%; max-height: 340px; object-fit: contain; border: 1px solid #e2e5e1; background: white; }}
.missing {{ display: grid; place-items: center; height: 180px; border: 1px solid #e2e5e1; color: #8a3333; }}
small {{ color: #8a3333; overflow-wrap: anywhere; }}
</style>
<header><h1>TikZ Visual Regression: {len(compact)} Cases</h1></header>
<main>
{''.join(cards)}
</main>
"""
    (out_dir / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--backend", default=os.environ.get("TIKZ_BACKEND_URL", "http://127.0.0.1:7860"))
    parser.add_argument("--local-catalog", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--branch", default="", help="Only run cases whose branch contains this text.")
    parser.add_argument("--timeout-s", type=float, default=120)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.branch:
        needle = args.branch.lower()
        cases = [c for c in cases if needle in c.get("branch", "").lower()]
    if args.limit:
        cases = cases[: args.limit]

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.out / stamp
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index:02d}/{len(cases):02d}] {case['id']} ...", flush=True)
        try:
            result = _run_local_catalog_case(case) if args.local_catalog else _run_backend_case(args.backend, case, args.timeout_s)
        except (urllib.error.URLError, TimeoutError, RuntimeError, Exception) as exc:  # noqa: BLE001
            result = {**case, "ok": False, "status": "exception", "svg": "", "svg_len": 0, "error": str(exc)}
        results.append(result)
        print(f"    {result.get('status')} svg={result.get('svg_len', 0)} {result.get('customized', '')}", flush=True)

    _write_outputs(results, out_dir)
    failed = [r for r in results if not r.get("ok")]
    print(f"\nWrote {out_dir}")
    print(f"Passed {len(results) - len(failed)} / {len(results)}")
    if failed:
        print("Failures:")
        for item in failed:
            print(f"  - {item['id']}: {item.get('status')} {item.get('error', '')[:160]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
