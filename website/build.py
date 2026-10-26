"""Build the benchmark website from the files of this repository.

Every sentence and number on the site comes from README.md, DATASETS.md,
CODECS.md, the corpus folders, and their ``results.csv``, so the site cannot
say something the repository does not. Previews come from the corpus folders
when they are built locally, and otherwise from the Hugging Face dataset.

    uv run --extra site python website/build.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import random
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

import markdown
import numpy as np

from earthcompress.runner import aggregate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "dist"
CACHE = ROOT / ".cache" / "site"
REPO = "https://github.com/earth-compress/benchmark"
HF_DATASET = "earth-compress/benchmark"
HF = f"https://huggingface.co/datasets/{HF_DATASET}/resolve/main"
THUMB = 192
LARGE = 768

# Invented values for designing the site before the official run. Never published.
EXAMPLE = {
    "zstd-c3": (1.55, 1200),
    "blosc-zstd3-bitshuffle": (1.75, 2400),
    "deflate-c6": (1.45, 350),
    "lzw": (1.25, 180),
    "hdiff-zstd9": (1.85, 900),
    "openzl-generic": (2.05, 650),
    "openzl-delta-fieldlz": (1.95, 1100),
    "openzl-delta-pivco": (2.1, 800),
    "geozl-planar-pfor": (2.2, 1700),
    "geozl-planar-pivco": (2.3, 1000),
}


# Reading the repository


def table(text: str, heading: str) -> list[dict[str, str]]:
    """The first Markdown table after ``heading``."""
    lines = []
    for line in text.split(heading, 1)[1].splitlines():
        if line.startswith("|"):
            lines.append(line)
        elif lines:
            break
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in lines
        if not set(line.replace("|", "").strip()) <= set("-: ")
    ]
    return [dict(zip(rows[0], row, strict=False)) for row in rows[1:]]


def inline(text: str) -> str:
    """Markdown inline code and emphasis, as HTML."""
    out = html.escape(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)


def plain(text: str) -> str:
    return text.replace("`", "")


def manifest(corpus: Path) -> list[dict[str, str]]:
    path = corpus / "manifest.csv"
    if not path.exists():
        return []
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def lossless_rows(corpus: Path) -> list[dict]:
    path = corpus / "results.csv"
    if not path.exists():
        return []
    with path.open(newline="") as stream:
        return [
            {**row, "fidelity_ok": row["fidelity_ok"] == "True"}
            for row in csv.DictReader(stream)
            if row["mode"] == "lossless"
        ]


def totals(rows: list[dict]) -> dict[str, dict]:
    """Totals of each configuration that completed every sample."""
    count = len({row["sample_id"] for row in rows})
    out = {}
    for config, total in aggregate(rows, count).items():
        if not total.get("complete"):
            continue
        selected = [r for r in rows if r["configuration"] == config]
        out[config] = {
            "input": sum(int(r["input_bytes"]) for r in selected),
            "compressed": sum(int(r["compressed_bytes"]) for r in selected),
            "decode_ns": sum(int(r["decode_ns"]) for r in selected),
        }
    return out


def per_sample(rows: list[dict]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for row in rows:
        if row["fidelity_ok"]:
            out.setdefault(row["sample_id"], {})[row["configuration"]] = {
                "input": int(row["input_bytes"]),
                "compressed": int(row["compressed_bytes"]),
                "decode_ns": int(row["decode_ns"]),
            }
    return out


def summary(data: dict[str, dict]) -> dict[str, dict]:
    """Totals over every measured corpus, for configurations present in all of them."""
    measured = [corpus for corpus in data.values() if corpus]
    if not measured:
        return {}
    common = set.intersection(*(set(corpus) for corpus in measured))
    keys = ("input", "compressed", "decode_ns")
    return {
        config: {key: sum(corpus[config][key] for corpus in measured) for key in keys}
        for config in sorted(common)
    }


def invented(seed: str, size: int, scale: tuple[float, float]) -> dict[str, dict]:
    rng = random.Random(seed)
    gain, speed = scale
    return {
        codec: {
            "input": size,
            "compressed": round(
                size / max(1.02, 1 + (ratio - 1) * gain * rng.uniform(0.9, 1.1))
            ),
            "decode_ns": round(size / (mb_s * speed * rng.uniform(0.85, 1.15)) * 1000),
        }
        for codec, (ratio, mb_s) in EXAMPLE.items()
    }


def corpus_scale(corpus: str) -> tuple[float, float]:
    rng = random.Random(corpus)
    return rng.uniform(0.7, 1.6), rng.uniform(0.6, 1.4)


# Images


def source_png(corpus: str, row: dict[str, str]) -> Path | None:
    """The preview of a sample: built locally, or fetched from Hugging Face."""
    if not row.get("png_path"):
        return None
    local = ROOT / "corpora" / corpus / row["png_path"]
    if local.exists():
        return local
    cached = CACHE / corpus / row["png_path"]
    if not cached.exists():
        try:
            with urllib.request.urlopen(
                f"{HF}/{corpus}/{row['png_path']}", timeout=60
            ) as r:
                data = r.read()
        except (urllib.error.URLError, TimeoutError):
            return None
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
    return cached


def resized(source: Path | None, target: str, side: int, square: bool) -> str | None:
    if source is None:
        return None
    from PIL import Image

    path = OUT / target
    path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = image.convert("RGB")
        if square:
            edge = min(image.size)
            left, top = (image.width - edge) // 2, (image.height - edge) // 2
            image = image.crop((left, top, left + edge, top + edge)).resize(
                (side, side), Image.LANCZOS
            )
        else:
            image.thumbnail((side, side), Image.LANCZOS)
        image.save(path, "WEBP", quality=82, method=6)
    return target


# Rendering

NAV = (
    ("Datasets", "datasets/"),
    ("Protocol", f"{REPO}/blob/main/PROTOCOL.md"),
    ("Codecs", f"{REPO}/blob/main/CODECS.md"),
    ("Tolerance", f"{REPO}/blob/main/TOLERANCE.md"),
    ("GitHub", REPO),
)


def layout(root: str, title: str, body: str, chart: dict | None = None) -> str:
    links = "".join(
        f'<a href="{href if href.startswith("http") else root + href}">{name}</a>'
        for name, href in NAV
    )
    data = (
        f'<script id="chart-data" type="application/json">{json.dumps(chart)}</script>'
        f'<script src="{root}chart.js?v={VERSION["chart.js"]}" defer></script>'
        if chart
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="icon" href="{root}earth-compress.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{root}style.css?v={VERSION["style.css"]}">
</head>
<body>
<header><div class="wrap bar">
<a class="brand" href="{root}"><img src="{root}earth-compress.svg" alt="Earth Compress" height="30"><span class="version">benchmark v1.0</span></a>
<nav>{links}</nav>
</div></header>
<main class="wrap">
{body}
</main>
<footer><div class="wrap"><p>Part of <a href="https://asterisk.coop/project-pages/earth-compress.html">Earth Compress</a>, funded by <a href="https://www.aria.org.uk/">ARIA</a> and led by the <a href="https://noc.ac.uk/">National Oceanography Centre</a> and <a href="https://asterisk.coop/">Asterisk Labs</a>. <a href="{REPO}/blob/main/LICENSE">Apache 2.0</a>.</p></div></footer>
{data}
</body>
</html>
"""


def picture(src: str | None, root: str, side: int) -> str:
    if src is None:
        return '<div class="noimg"></div>'
    return (
        f'<img src="{root}{src}" alt="" loading="lazy" width="{side}" height="{side}">'
    )


def crumbs(root: str, *parts: tuple[str, str | None]) -> str:
    items = [f'<a href="{root}">Benchmark</a>'] + [
        f'<a href="{root}{href}">{html.escape(name)}</a>'
        if href
        else f"<span>{html.escape(name)}</span>"
        for name, href in parts
    ]
    return f'<p class="crumbs">{" / ".join(items)}</p>'


def card(root: str, href: str, image: str | None, name: str, meta: str) -> str:
    return (
        f'<a class="card" href="{root}{href}">{picture(image, root, THUMB)}'
        f'<span class="cid">{html.escape(name)}</span><span class="meta">{meta}</span></a>'
    )


def chart_block(select: str = "", badge: str = "", key: str = "all") -> str:
    pick = f'<label class="pick">{badge}{select}</label>' if select or badge else ""
    return f"""<section class="results">
<div class="controls">
<div class="tabs" role="tablist" aria-label="Fidelity mode">
<button type="button" role="tab" aria-controls="panel-lossless" aria-selected="true">Lossless</button>
<button type="button" role="tab" aria-controls="panel-near" aria-selected="false">Near-lossless <span class="soon">soon</span></button>
<button type="button" role="tab" aria-controls="panel-lossy" aria-selected="false">Lossy <span class="soon">soon</span></button>
</div>
{pick}
</div>
<div class="panel" role="tabpanel" id="panel-lossless"><div class="chart" data-chart="{key}"{' data-select="corpus"' if select else ""}></div></div>
<div class="panel soonpanel" role="tabpanel" id="panel-near" hidden><p>Coming soon.</p></div>
<div class="panel soonpanel" role="tabpanel" id="panel-lossy" hidden><p>Coming soon.</p></div>
</section>"""


def ratio(entry: dict) -> float:
    return entry["input"] / entry["compressed"]


def speed(entry: dict) -> float:
    return entry["input"] / 1e6 / (entry["decode_ns"] / 1e9)


def results_table(entries: dict[str, dict], codecs: list[str], itemsize: int) -> str:
    rows = "".join(
        f"<tr><td><code>{c}</code></td><td>{ratio(entries[c]):.3f}</td>"
        f"<td>{entries[c]['compressed'] * 8 * itemsize / entries[c]['input']:.2f}</td>"
        f"<td>{speed(entries[c]):,.0f}</td></tr>"
        for c in codecs
        if c in entries
    )
    if not rows:
        return '<p class="note">No results yet.</p>'
    return (
        '<div class="scroll"><table class="numbers"><tr><th>configuration</th><th>ratio</th>'
        f"<th>bits per value</th><th>decode MB/s</th></tr>{rows}</table></div>"
    )


VERSION: dict[str, str] = {}

HIDDEN = {"npz_path", "png_path"}


def metadata(row: dict[str, str]) -> str:
    items = []
    for key, value in row.items():
        if key in HIDDEN or value == "":
            continue
        text = html.escape(value)
        if key == "asset":
            parts = value.split("|")
            text = "<br>".join(
                f'<a href="{html.escape(p)}">{html.escape(p)}</a>'
                if p.startswith("http")
                else f"<code>{html.escape(p)}</code>"
                for p in parts[:3]
            ) + (
                f"<br><span class='note'>and {len(parts) - 3} more</span>"
                if len(parts) > 3
                else ""
            )
        elif key == "bands" and value.count("|") > 8:
            parts = value.split("|")
            text = f"<code>{html.escape(parts[0])}</code> to <code>{html.escape(parts[-1])}</code>, {len(parts)} planes"
        elif len(value) > 80:
            text = f"<details><summary><code>{html.escape(value[:60])}…</code></summary><code class='long'>{text}</code></details>"
        else:
            text = (
                f"<code>{text}</code>"
                if key not in {"source", "site", "regime"}
                else text
            )
        items.append(f"<tr><th>{html.escape(key)}</th><td>{text}</td></tr>")
    return f'<table class="meta-table">{"".join(items)}</table>'


def build(use_example: bool) -> None:
    datasets = table((ROOT / "DATASETS.md").read_text(), "## Corpora")
    codecs = [
        plain(r["id"])
        for r in table((ROOT / "CODECS.md").read_text(), "## Official run")
    ]
    badge = '<span class="example">Example data</span>' if use_example else ""

    corpus_totals: dict[str, dict] = {}
    corpus_cards = []
    for row in datasets:
        cid = plain(row["corpus"])
        folder = ROOT / "corpora" / cid
        samples = manifest(folder)
        rows = lossless_rows(folder)
        found = totals(rows)
        by_sample = per_sample(rows)
        if use_example and samples:
            found = invented(cid, 100_000_000, corpus_scale(cid))
            gain, fast = corpus_scale(cid)
            by_sample = {
                s["id"]: invented(
                    s["id"],
                    4_000_000,
                    (gain * random.Random(s["id"]).uniform(0.85, 1.15), fast),
                )
                for s in samples
            }
        corpus_totals[cid] = found
        meta = f"{inline(row['shape'])} · {inline(row['dtype'])}"

        sample_cards = []
        first = None
        for i, s in enumerate(samples):
            src = source_png(cid, s)
            thumb = resized(src, f"img/{cid}/{s['id']}.webp", THUMB, True)
            large = resized(src, f"img/{cid}/{s['id']}-large.webp", LARGE, False)
            first = first or thumb
            when = s.get("datetime_start", "")[:10]
            sample_cards.append(
                card(
                    "../../",
                    f"datasets/{cid}/{s['id']}/",
                    thumb,
                    s["id"],
                    html.escape(" · ".join(x for x in (s.get("site", ""), when) if x)),
                )
            )
            prev_link = (
                f'<a href="../{samples[i - 1]["id"]}/">← {samples[i - 1]["id"]}</a>'
                if i
                else "<span></span>"
            )
            next_link = (
                f'<a href="../{samples[i + 1]["id"]}/">{samples[i + 1]["id"]} →</a>'
                if i + 1 < len(samples)
                else "<span></span>"
            )
            download = f"{HF}/{cid}/{s['npz_path']}" if s.get("npz_path") else ""
            body = f"""{crumbs("../../../", ("Datasets", "datasets/"), (cid, f"datasets/{cid}/"), (s["id"], None))}
<div class="sample">
<div class="figure">{f'<img src="../../../{large}" alt="Preview of {html.escape(s["id"])}">' if large else '<div class="noimg"></div>'}
{f'<p><a class="button" href="{download}">Download {html.escape(Path(s["npz_path"]).name)}</a></p>' if download else ""}</div>
<div><h1>{html.escape(s["id"])}</h1>
<h2>Results {badge}</h2>
{results_table(by_sample.get(s["id"], {}), codecs, np.dtype(s["dtype"]).itemsize)}
<h2>Metadata</h2>
{metadata(s)}</div>
</div>
<p class="pager">{prev_link}{next_link}</p>"""
            target = OUT / "datasets" / cid / s["id"] / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                layout("../../../", f"{s['id']} · Earth Compress benchmark", body)
            )

        spec = folder / "spec.md"
        spec_html = (
            markdown.markdown(spec.read_text().split("\n", 1)[1], extensions=["tables"])
            if spec.exists()
            else ""
        )
        body = f"""{crumbs("../../", ("Datasets", "datasets/"), (cid, None))}
<h1>{cid}</h1>
<p class="lead">{inline(row["contents"])}.</p>
<p class="facts"><span>{inline(row["shape"])}</span><span>{inline(row["dtype"])}</span><span>{inline(row["samples"])} samples</span><span>{inline(row["MB"])} MB</span><span>{inline(row["source"])}</span></p>
{chart_block(badge=badge, key=cid)}
<section><h2>Samples</h2>{'<div class="grid">' + "".join(sample_cards) + "</div>" if sample_cards else '<p class="note">Not built yet.</p>'}</section>
<section class="spec">{spec_html}<p><a href="{REPO}/tree/main/corpora/{cid}">Folder on GitHub</a></p></section>"""
        target = OUT / "datasets" / cid / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            layout(
                "../../",
                f"{cid} · Earth Compress benchmark",
                body,
                {"data": {cid: found}, "codecs": codecs},
            )
        )
        corpus_cards.append((cid, f"datasets/{cid}/", first, meta))

    measured = [cid for cid, found in corpus_totals.items() if found]
    options = "".join(f'<option value="{cid}">{cid}</option>' for cid in measured)
    select = f'<select id="corpus" aria-label="Corpus"><option value="all">All corpora</option>{options}</select>'
    chart = {
        "data": {
            "all": summary(corpus_totals),
            **{c: corpus_totals[c] for c in measured},
        },
        "codecs": codecs,
    }
    grid = "".join(
        card("", href, image, cid, meta) for cid, href, image, meta in corpus_cards
    )
    (OUT / "index.html").write_text(
        layout(
            "",
            "Earth Compress benchmark",
            f'{chart_block(select, badge)}\n<section id="datasets"><h2>Datasets</h2><div class="grid">{grid}</div></section>',
            chart,
        )
    )
    grid = "".join(
        card("../", href, image, cid, meta) for cid, href, image, meta in corpus_cards
    )
    (OUT / "datasets").mkdir(exist_ok=True)
    (OUT / "datasets" / "index.html").write_text(
        layout(
            "../",
            "Datasets · Earth Compress benchmark",
            f'{crumbs("../", ("Datasets", None))}<h1>Datasets</h1><div class="grid">{grid}</div>',
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--example", action="store_true", help="invented results, for design only"
    )
    args = parser.parse_args()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copy(
        ROOT / "docs" / "assets" / "earth-compress.svg", OUT / "earth-compress.svg"
    )
    for name in ("style.css", "chart.js"):
        content = (HERE / name).read_bytes()
        (OUT / name).write_bytes(content)
        VERSION[name] = hashlib.sha256(content).hexdigest()[:10]
    build(args.example)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
