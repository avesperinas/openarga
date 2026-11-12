#!/usr/bin/env python3

from __future__ import annotations

import argparse
import gzip
import json
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COOKIE = "__Host-arga_session"
ASSET = re.compile(
    r'<script[^>]*type="module"[^>]*src="([^"]+)"'
    r'|<link[^>]*rel="(?:modulepreload|stylesheet)"[^>]*href="([^"]+)"'
)


def gzipped(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), compresslevel=9))


def initial_assets(dist: Path) -> list[Path]:
    html = (dist / "index.html").read_text()
    found = []
    for script, link in ASSET.findall(html):
        url = (script or link).split("?")[0]
        base = "/" + url.strip("/").split("/")[0] + "/"
        found.append(dist / url.removeprefix(base))
    return [path for path in found if path.exists()]


def bundles() -> list[dict]:
    rows = []
    for dist in sorted(ROOT.glob("modules/*/ui/dist")):
        app = dist.parts[-3]
        assets = initial_assets(dist)
        js = [path for path in assets if path.suffix == ".js"]
        css = [path for path in assets if path.suffix == ".css"]
        everything = list(dist.rglob("*.js"))
        rows.append(
            {
                "app": app,
                "js_initial_gz": sum(gzipped(path) for path in js),
                "css_initial_gz": sum(gzipped(path) for path in css),
                "js_total_gz": sum(gzipped(path) for path in everything),
                "chunks": len(everything),
            }
        )
    return rows


def session(cookie: str | None) -> dict[str, str]:
    return {"cookie": f"{COOKIE}={cookie}"} if cookie else {}


def read_json(url: str, cookie: str | None):
    request = urllib.request.Request(url, headers=session(cookie))
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def ttfb(url: str, cookie: str | None) -> tuple[float, int, str]:
    request = urllib.request.Request(url, headers=session(cookie))
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            elapsed = time.perf_counter() - started
            response.read()
            return elapsed, response.status, response.headers.get("server-timing", "")
    except urllib.error.HTTPError as error:
        return time.perf_counter() - started, error.code, error.headers.get("server-timing", "")


def parse_timing(value: str) -> dict[str, float]:
    parts = {}
    for metric in value.split(","):
        name, _, rest = metric.strip().partition(";")
        found = re.search(r"dur=([0-9.]+)", rest)
        if name and found:
            parts[name] = float(found.group(1))
    return parts


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(share * (len(ordered) - 1)))]


def targets(base: str, cookie: str | None) -> list[tuple[str, str]]:
    found = [("portada", f"{base}/")]
    for module in read_json(f"{base}/api/kernel/modules", cookie):
        if module.get("enabled") and module.get("view"):
            found.append((f"{module['id']} (app)", f"{base}{module['view'].rstrip('/')}/"))
    for entry in read_json(f"{base}/api/kernel/ui/widgets", cookie):
        found.append((f"{entry['source']}/{entry['id']}", f"{base}{entry['endpoint']}"))
    return found


def times(base: str, cookie: str | None, runs: int) -> list[dict]:
    rows = []
    for name, url in targets(base, cookie):
        seconds, timings, statuses = [], [], set()
        for _ in range(runs):
            elapsed, status, timing = ttfb(url, cookie)
            seconds.append(elapsed * 1000)
            timings.append(parse_timing(timing))
            statuses.add(status)
        rows.append(
            {
                "what": name,
                "status": ",".join(str(status) for status in sorted(statuses)),
                "p50": statistics.median(seconds),
                "p95": percentile(seconds, 0.95),
                **{
                    part: statistics.median(t[part] for t in timings if part in t)
                    for part in ("db", "app", "gw")
                    if any(part in t for t in timings)
                },
            }
        )
    return rows


def table(rows: list[dict], columns: list[str]) -> str:
    def cell(value) -> str:
        return f"{value:.0f}" if isinstance(value, float) else str(value)

    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        lines.append("| " + " | ".join(cell(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure response times of a running OpenArga.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("what", choices=["bundles", "times"])
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--cookie", help="el valor de la cookie de sesión del navegador")
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()

    if args.what == "bundles":
        rows = bundles()
        if not rows:
            print("No hay nada construido: `pnpm -r build` antes.", file=sys.stderr)
            return 1
        for row in rows:
            for key in ("js_initial_gz", "css_initial_gz", "js_total_gz"):
                row[key] = f"{row[key] / 1024:.0f} KB"
        print(table(rows, ["app", "js_initial_gz", "css_initial_gz", "js_total_gz", "chunks"]))
        return 0

    if not args.cookie:
        print("Sin --cookie el gateway contesta 401 a todo lo que tiene datos.", file=sys.stderr)
        return 1
    rows = times(args.base.rstrip("/"), args.cookie, args.runs)
    print(table(rows, ["what", "status", "p50", "p95", "db", "app", "gw"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
