from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import re
import shutil
import statistics
import urllib.error
import urllib.request
from pathlib import Path

import markdown

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


KEYS = ("input", "compressed", "decode_ns")


def entry(rows: list[dict]) -> dict:
    """Sums of the measurements of ``rows``, one configuration on one or more samples."""
    return {
        "input": sum(int(r["input_bytes"]) for r in rows),
        "compressed": sum(int(r["compressed_bytes"]) for r in rows),
        "decode_ns": sum(int(r["decode_ns"]) for r in rows),
    }


def totals(rows: list[dict]) -> dict[str, dict]:
    """Totals of each configuration that completed every sample."""
    count = len({row["sample_id"] for row in rows})
    return {
        config: entry([r for r in rows if r["configuration"] == config])
        for config, total in aggregate(rows, count).items()
        if total.get("complete")
    }


def per_sample(rows: list[dict]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for row in rows:
        if row["fidelity_ok"]:
            out.setdefault(row["sample_id"], {})[row["configuration"]] = entry([row])
    return out


def summary(data: dict[str, dict]) -> dict[str, dict]:
    """Totals over every measured corpus, for configurations present in all of them."""
    measured = [corpus for corpus in data.values() if corpus]
    if not measured:
        return {}
    common = set.intersection(*(set(corpus) for corpus in measured))
    return {
        config: {key: sum(corpus[config][key] for corpus in measured) for key in KEYS}
        for config in sorted(common)
    }


# Images


def fetched(local: Path, path: str, key: str | None = None) -> Path | None:
    """``local`` when it was built here, or ``path`` fetched from Hugging Face
    and kept in the cache under ``key``."""
    if local.exists():
        return local
    cached = CACHE / (key or path)
    if not cached.exists():
        try:
            with urllib.request.urlopen(f"{HF}/{path}", timeout=60) as r:
                data = r.read()
        except (urllib.error.URLError, TimeoutError):
            return None
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
    return cached


def source_png(corpus: str, row: dict[str, str]) -> Path | None:
    """The preview of a sample: built locally, or fetched from Hugging Face."""
    if not row.get("png_path"):
        return None
    return fetched(
        ROOT / "corpora" / corpus / row["png_path"], f"{corpus}/{row['png_path']}"
    )


def usecase_png(folder: str, sample: str, name: str) -> Path | None:
    """A map of a use case sample: made locally by its ``run.py``, or fetched
    from Hugging Face.

    A new run of the use case writes new maps under the same names, so the
    cache keeps them by the digest of its ``results.csv``.
    """
    path = f"usecases/{folder}/png/{sample}/{name}.png"
    results = (ROOT / "usecases" / folder / "results.csv").read_bytes()
    run = hashlib.sha256(results).hexdigest()[:10]
    return fetched(ROOT / path, path, f"usecases/{folder}/{run}/{sample}/{name}.png")


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
    ("Protocol", "protocol/"),
    ("Codecs", "codecs/"),
    ("Use cases", "usecases/"),
    ("Tolerance", "tolerance/"),
)
DOCS = {"protocol": "PROTOCOL.md", "codecs": "CODECS.md", "tolerance": "TOLERANCE.md"}
PAGES = {
    **{name: slug for slug, name in DOCS.items()},
    "DATASETS.md": "datasets",
    "USECASE.md": "usecases",
}
GITHUB_ICON = (
    '<svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true"><path fill="currentColor" '
    'd="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49'
    "-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82"
    ".72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15"
    "-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2"
    "-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54"
    ' 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>'
)
HF_ICON = (
    '<svg viewBox="0 0 32 32" width="22" height="22" aria-hidden="true">'
    '<circle cx="16" cy="15" r="12" fill="#FFD21E"/>'
    '<circle cx="11.5" cy="12.5" r="1.6" fill="#3A3B45"/><circle cx="20.5" cy="12.5" r="1.6" fill="#3A3B45"/>'
    '<path d="M10.5 17.5c1.2 2.4 3.2 3.6 5.5 3.6s4.3-1.2 5.5-3.6" fill="none" stroke="#3A3B45" '
    'stroke-width="1.8" stroke-linecap="round"/>'
    '<path d="M4.5 22.5c1.5-1.8 3.5-2 4.6-.6l1.6 2.1c.7 1-.1 2.4-1.3 2.3l-3.4-.4c-1.4-.2-2.2-2.1-1.5-3.4z'
    'M27.5 22.5c-1.5-1.8-3.5-2-4.6-.6l-1.6 2.1c-.7 1 .1 2.4 1.3 2.3l3.4-.4c1.4-.2 2.2-2.1 1.5-3.4z" '
    'fill="#FF9D0B"/></svg>'
)


def layout(root: str, title: str, body: str, chart: dict | None = None) -> str:
    links = "".join(f'<a href="{root}{href}">{name}</a>' for name, href in NAV)
    links += (
        f'<a class="icon" href="{REPO}" title="GitHub" aria-label="GitHub">{GITHUB_ICON}</a>'
        f'<a class="icon" href="https://huggingface.co/datasets/{HF_DATASET}" title="Hugging Face" '
        f'aria-label="Hugging Face">{HF_ICON}</a>'
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


def chart_block(select: str = "", key: str = "all", caption: str = "") -> str:
    pick = f'<label class="pick">{select}</label>' if select else ""
    note = f'<p class="chart-note">{caption}</p>' if caption else ""
    return f"""<section class="results">
<div class="controls">
<div class="tabs" role="tablist" aria-label="Fidelity mode">
<button type="button" role="tab" aria-controls="panel-lossless" aria-selected="true">Lossless</button>
<button type="button" role="tab" aria-controls="panel-near" aria-selected="false">Near-lossless <span class="soon">soon</span></button>
<button type="button" role="tab" aria-controls="panel-lossy" aria-selected="false">Lossy <span class="soon">soon</span></button>
</div>
{pick}
</div>
<div class="panel" role="tabpanel" id="panel-lossless"><div class="chart" data-chart="{key}"{' data-select="corpus"' if select else ""}></div>{note}</div>
<div class="panel soonpanel" role="tabpanel" id="panel-near" hidden><p>Coming soon.</p></div>
<div class="panel soonpanel" role="tabpanel" id="panel-lossy" hidden><p>Coming soon.</p></div>
</section>"""


def ratio(entry: dict) -> float:
    return entry["input"] / entry["compressed"]


def speed(entry: dict) -> float:
    return entry["input"] / 1e6 / (entry["decode_ns"] / 1e9)


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


def document(name: str) -> str:
    """A Markdown document of the repository as HTML, with links to its pages."""
    out = markdown.markdown(
        (ROOT / name).read_text(),
        extensions=["tables", "fenced_code", "codehilite"],
        extension_configs={"codehilite": {"guess_lang": False}},
    )
    for other, slug in PAGES.items():
        out = out.replace(f'href="{other}"', f'href="../{slug}/"')
        out = out.replace(
            f"<code>{other}</code>", f'<a href="../{slug}/"><code>{other}</code></a>'
        )
    return f'<article class="doc">{out}</article>'


def build() -> None:
    for slug, name in DOCS.items():
        target = OUT / slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        title = (ROOT / name).read_text().splitlines()[0].lstrip("# ")
        target.write_text(
            layout("../", f"{title} · Earth Compress benchmark", document(name))
        )

    datasets = table((ROOT / "DATASETS.md").read_text(), "## Corpora")
    official = table((ROOT / "CODECS.md").read_text(), "## Lossless")
    codecs = [plain(r["id"]) for r in official]
    reference = table((ROOT / "CODECS.md").read_text(), "### Reference")
    style = {
        "groups": {plain(r["id"]): r["group"] for r in official},
        "reference": plain(reference[0]["id"]) if reference else None,
    }

    corpus_totals: dict[str, dict] = {}
    sample_counts: dict[str, int] = {}
    corpus_cards = []
    for row in datasets:
        cid = plain(row["corpus"])
        folder = ROOT / "corpora" / cid
        samples = manifest(folder)
        sample_counts[cid] = len(samples)
        rows = lossless_rows(folder)
        found = totals(rows)
        by_sample = per_sample(rows)
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
<h1>{html.escape(s["id"])}</h1>
<div class="chart" data-chart="{s["id"]}"></div>
<div class="sample">
<div class="figure">{f'<img src="../../../{large}" alt="Preview of {html.escape(s["id"])}">' if large else '<div class="noimg"></div>'}
{f'<p><a class="button" href="{download}">Download {html.escape(Path(s["npz_path"]).name)}</a></p>' if download else ""}</div>
<div><h2>Metadata</h2>
{metadata(s)}</div>
</div>
<p class="pager">{prev_link}{next_link}</p>"""
            target = OUT / "datasets" / cid / s["id"] / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            chart = {
                "data": {s["id"]: by_sample.get(s["id"], {})},
                "codecs": codecs,
                **style,
            }
            target.write_text(
                layout(
                    "../../../", f"{s['id']} · Earth Compress benchmark", body, chart
                )
            )

        spec = folder / "spec.md"
        blocks = spec.read_text().split("\n## ")[1:] if spec.exists() else []
        spec_html = "".join(
            f"<div><h3>{html.escape(b.split(chr(10), 1)[0])}</h3>"
            f"{markdown.markdown(b.split(chr(10), 1)[1], extensions=['tables'])}</div>"
            for b in blocks
        )
        body = f"""{crumbs("../../", ("Datasets", "datasets/"), (cid, None))}
<h1>{cid}</h1>
<p class="lead">{inline(row["contents"])}.</p>
<section class="spec">{spec_html}</section>
<p class="folder"><a href="{REPO}/tree/main/corpora/{cid}">Folder on GitHub</a></p>
{chart_block(key=cid)}
<section><h2>Samples</h2>{'<div class="grid">' + "".join(sample_cards) + "</div>" if sample_cards else '<p class="note">Not built yet.</p>'}</section>"""
        target = OUT / "datasets" / cid / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            layout(
                "../../",
                f"{cid} · Earth Compress benchmark",
                body,
                {"data": {cid: found}, "codecs": codecs, **style},
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
        **style,
    }
    grid = "".join(
        card("", href, image, cid, meta) for cid, href, image, meta in corpus_cards
    )
    intro = (
        '<div class="home-intro"><h1>Earth Compress benchmark</h1>'
        f"<p>Lossless compression results for {sum(sample_counts[cid] for cid in measured)} "
        f"samples across {len(measured)} corpora of imagery, environmental fields and embeddings.</p></div>"
    )
    caption = (
        "Each point is a configuration. The line marks the best observed trade-offs. "
        "All corpora pools sizes and decode times across samples, so larger corpora "
        "carry more weight. Only configurations completed on every corpus appear."
    )
    (OUT / "index.html").write_text(
        layout(
            "",
            "Earth Compress benchmark",
            f'{intro}{chart_block(select, caption=caption)}\n<section id="datasets"><h2>Datasets</h2><div class="grid">{grid}</div></section>',
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
            f'{crumbs("../", ("Datasets", None))}<h1>Datasets</h1><div class="grid">{grid}</div>'
            + document("DATASETS.md")
            .replace("<h1>Datasets</h1>", "", 1)
            .replace('class="doc"', 'class="doc wide"', 1),
        )
    )
    usecases()


# Use cases

IOU_FIGURE = """<svg class="explain" viewBox="0 0 760 236" role="img" aria-label="How delta_iou is computed from the detection and the plume mask">
<g transform="translate(0 0)">
<text class="h" x="0" y="16">Original</text>
<rect x="0" y="26" width="220" height="150" rx="6" fill="#3b3b3b"/>
<ellipse cx="104" cy="102" rx="70" ry="33" transform="rotate(-18 104 102)" fill="#f59e0b"/>
<rect x="34" y="146" width="6" height="6" fill="#f59e0b"/><rect x="186" y="50" width="6" height="6" fill="#f59e0b"/>
<ellipse cx="112" cy="100" rx="84" ry="40" transform="rotate(-18 112 100)" fill="none" stroke="#fff" stroke-width="2"/>
<text class="m" x="0" y="200">IoU = overlap / union</text>
<text class="m" x="0" y="220">    = 0.59</text>
</g>
<g transform="translate(244 0)">
<text x="0" y="104">compress,</text><text x="0" y="122">decode,</text><text x="0" y="140">detect</text>
<path d="M2 154 H58 M50 148 L58 154 L50 160" fill="none" stroke="#8aa09f" stroke-width="2"/>
</g>
<g transform="translate(316 0)">
<text class="h" x="0" y="16">Compressed copy</text>
<rect x="0" y="26" width="220" height="150" rx="6" fill="#3b3b3b"/>
<ellipse cx="104" cy="102" rx="70" ry="33" transform="rotate(-18 104 102)" fill="#38bdf8"/>
<ellipse cx="110" cy="104" rx="54" ry="24" transform="rotate(-18 110 104)" fill="#f59e0b"/>
<rect x="28" y="50" width="6" height="6" fill="#f43f5e"/><rect x="60" y="150" width="6" height="6" fill="#f43f5e"/>
<rect x="150" y="44" width="6" height="6" fill="#f43f5e"/><rect x="196" y="140" width="6" height="6" fill="#f43f5e"/>
<rect x="176" y="70" width="6" height="6" fill="#f43f5e"/><rect x="20" y="118" width="6" height="6" fill="#f43f5e"/>
<rect x="118" y="160" width="6" height="6" fill="#f43f5e"/><rect x="92" y="36" width="6" height="6" fill="#f43f5e"/>
<ellipse cx="112" cy="100" rx="84" ry="40" transform="rotate(-18 112 100)" fill="none" stroke="#fff" stroke-width="2"/>
<text class="m" x="0" y="200">IoU = overlap / union</text>
<text class="m" x="0" y="220">    = 0.45</text>
</g>
<g transform="translate(566 0)">
<text class="h" x="0" y="16">delta_iou</text>
<text class="m" x="0" y="44">= IoU copy - IoU original</text>
<text class="m" x="0" y="64">= 0.45 - 0.59 = -0.14</text>
<rect x="0" y="92" width="12" height="12" rx="2" fill="#f59e0b"/><text x="20" y="102">detected on both</text>
<rect x="0" y="116" width="12" height="12" rx="2" fill="#38bdf8"/><text x="20" y="126">lost</text>
<rect x="0" y="140" width="12" height="12" rx="2" fill="#f43f5e"/><text x="20" y="150">new false alarm</text>
<rect x="0" y="164" width="12" height="12" rx="2" fill="none" stroke="#8aa09f" stroke-width="2"/><text x="20" y="174">plume mask</text>
</g>
</svg>"""

STREAM_FIGURE = """<svg class="explain" viewBox="0 0 860 236" role="img" aria-label="How stream_f1 compares the stream network of the compressed copy with the original one">
<g transform="translate(0 0)" fill="none" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
<text class="h" x="0" y="16" stroke="none">Original</text>
<rect x="0" y="26" width="220" height="150" rx="6" fill="#3b3b3b" stroke="none"/>
<path d="M200 70 L150 92 L104 104 L60 132 L18 160" stroke="#f59e0b"/>
<path d="M150 92 L132 50" stroke="#f59e0b"/>
<path d="M104 104 L82 66 L64 44" stroke="#f59e0b"/>
<path d="M60 132 L96 156" stroke="#f59e0b"/>
</g>
<g transform="translate(244 0)">
<text x="0" y="104">compress,</text><text x="0" y="122">decode,</text><text x="0" y="140">route</text>
<path d="M2 154 H58 M50 148 L58 154 L50 160" fill="none" stroke="#8aa09f" stroke-width="2"/>
</g>
<g transform="translate(316 0)" fill="none" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
<text class="h" x="0" y="16" stroke="none">Compressed copy</text>
<rect x="0" y="26" width="220" height="150" rx="6" fill="#3b3b3b" stroke="none"/>
<path d="M104 104 L82 66 L64 44" stroke="#38bdf8"/>
<path d="M104 104 L150 140 L196 150" stroke="#f43f5e"/>
<path d="M200 70 L150 92 L104 104 L60 132 L18 160" stroke="#f59e0b"/>
<path d="M150 92 L132 50" stroke="#f59e0b"/>
<path d="M60 132 L96 156" stroke="#f59e0b"/>
</g>
<g transform="translate(566 0)">
<text class="h" x="0" y="16">stream_f1</text>
<text x="0" y="42">P, compressed stream cells within one</text>
<text x="0" y="58">cell of an original stream</text>
<text x="0" y="80">R, original stream cells within one</text>
<text x="0" y="96">cell of a compressed stream</text>
<text class="m" x="0" y="120">F1 = 2 P R / (P + R)</text>
<text class="m" x="0" y="138">   = 2 · 0.85 · 0.80 / 1.65 = 0.82</text>
<rect x="0" y="160" width="12" height="12" rx="2" fill="#f59e0b"/><text x="20" y="170">on both within one cell</text>
<rect x="0" y="184" width="12" height="12" rx="2" fill="#38bdf8"/><text x="20" y="194">lost</text>
<rect x="0" y="208" width="12" height="12" rx="2" fill="#f43f5e"/><text x="20" y="218">new</text>
</g>
</svg>"""


def change_figure(
    metric: str = "change_iou",
    name: str = "change map",
    found: tuple[str, str] = ("changed where 2017 and 2025", "have a cosine below 0.8"),
    again: tuple[str, str, str] = ("compress", "both years,", "map again"),
    both: str = "changed on both",
) -> str:
    """How ``metric`` compares the map of the compressed copy with the original
    one, on a grid of pixels."""
    original = {(3, 2), (4, 2), (5, 2), (2, 3), (3, 3), (4, 3), (5, 3), (6, 3)}
    original |= {(3, 4), (4, 4), (5, 4), (6, 4), (4, 5), (5, 5), (8, 1), (8, 2)}
    lost = {(2, 3), (6, 4), (8, 1)}
    new = {(1, 5), (7, 5), (9, 4), (6, 5)}

    def grid(cells: dict) -> str:
        out = []
        for row in range(7):
            for col in range(11):
                colour = cells.get((col, row), "#4a4a4a")
                out.append(
                    f'<rect x="{col * 20}" y="{26 + row * 21}" width="18" height="19" '
                    f'rx="2" fill="{colour}"/>'
                )
        return "".join(out)

    before = grid(dict.fromkeys(original, "#f59e0b"))
    after = grid(
        {
            **dict.fromkeys(original - lost, "#f59e0b"),
            **dict.fromkeys(lost, "#38bdf8"),
            **dict.fromkeys(new, "#f43f5e"),
        }
    )
    kept = len(original - lost)
    union = len(original | new)
    return f"""<svg class="explain" viewBox="0 0 760 236" role="img" aria-label="How {metric} compares the {name} of the compressed copy with the original one">
<g><text class="h" x="0" y="16">Original {name}</text>{before}
<text x="0" y="200">{found[0]}</text><text x="0" y="218">{found[1]}</text></g>
<g transform="translate(244 0)">
<text x="0" y="104">{again[0]}</text><text x="0" y="122">{again[1]}</text><text x="0" y="140">{again[2]}</text>
<path d="M2 154 H58 M50 148 L58 154 L50 160" fill="none" stroke="#8aa09f" stroke-width="2"/>
</g>
<g transform="translate(316 0)"><text class="h" x="0" y="16">Compressed copy</text>{after}</g>
<g transform="translate(566 0)">
<text class="h" x="0" y="16">{metric}</text>
<text class="m" x="0" y="44">= overlap / union</text>
<text class="m" x="0" y="64">= {kept} / {union} = {kept / union:.2f}</text>
<rect x="0" y="92" width="12" height="12" rx="2" fill="#f59e0b"/><text x="20" y="102">{both}</text>
<rect x="0" y="116" width="12" height="12" rx="2" fill="#38bdf8"/><text x="20" y="126">lost</text>
<rect x="0" y="140" width="12" height="12" rx="2" fill="#f43f5e"/><text x="20" y="150">new</text>
</g>
</svg>"""


USECASES = (
    {
        "title": "Methane plumes",
        "folder": "methane",
        "metric": "delta_iou",
        "caption": "The enhancement of methane-s2-05, with its plume mask outlined.",
        "figure": IOU_FIGURE,
        "group": "sensor",
        "groups": {"s2": "Sentinel-2", "l89": "Landsat 8/9"},
        "unit": "10⁻⁴ of reflectance",
        "short": "× 10⁻⁴",
        "card": "{sensor} · {plume_pixels} plume pixels",
        "original": "The original detection in orange over the enhancement, with the plume mask in white.",
        "maps": "Decoded detections",
        "keys": ("detected on both", "lost", "new"),
    },
    {
        "title": "Drainage networks",
        "folder": "drainage",
        "metric": "stream_f1",
        "caption": "The relief of cop-dem-glo30-00 with its stream network.",
        "figure": STREAM_FIGURE,
        "group": "regime",
        "groups": {},
        "unit": "metres",
        "short": "m",
        "card": "{site} · {regime}",
        "original": "The original stream network in orange over the relief.",
        "maps": "Decoded stream networks",
        "keys": ("on both within one cell", "lost", "new"),
    },
    {
        "title": "Change detection",
        "folder": "change-detection",
        "metric": "change_iou",
        "caption": "AlphaEarth over Ethiopia's GERD reservoir in 2025. Red marks pixels the detector flags as changed since 2017.",
        "figure": change_figure(),
        "group": None,
        "groups": {},
        "unit": "codes of the quantised embedding",
        "short": "codes",
        "card": "{site} · {change}",
        "original": "The original change map in orange over the 2025 embedding.",
        "maps": "Decoded change maps",
        "keys": ("changed on both", "lost", "new"),
    },
    {
        "title": "Clouds Decoded",
        "folder": "clouds-decoded",
        "metric": "cloud_iou",
        "caption": "Sentinel-2 over the Bay of Bengal on 21 November 2021, decoded from JPEG XL at distance 0.094.",
        "figure": change_figure(
            "cloud_iou",
            "cloud mask",
            ("cloud where Clouds Decoded", "finds it on the original"),
            ("compress", "the bands,", "mask again"),
            "cloud on both",
        ),
        "samples": 100,
        "run": (
            "git clone -b compressed-readers https://github.com/asterisk-labs/clouds-decoded\n"
            "pip install -e clouds-decoded imagecodecs\n"
            "clouds-decoded full-workflow jpegxl/&lt;product&gt;.SAFE \\\n"
            "    --compression-level d-0.33 --output-dir out/",
            "Clouds Decoded reads a compressed product at the level given by <code>--compression-level</code>.",
        ),
    },
)
HIDDEN_META = {"id", "npz_path", "asset", "asset_2017", "asset_2025", "nodata"}


def linked(text: str, root: str) -> str:
    """Links to other documents of the repository pointed at their pages."""
    for other, slug in PAGES.items():
        text = text.replace(f'href="{other}"', f'href="{root}{slug}/"')
        text = text.replace(
            f"<code>{other}</code>", f'<a href="{root}{slug}/"><code>{other}</code></a>'
        )
    return text


def ticks(low: float, high: float) -> list[float]:
    span = high - low
    step = (
        0.02 if span <= 0.12 else 0.05 if span <= 0.3 else 0.1 if span <= 0.6 else 0.2
    )
    count = round(span / step)
    return [round(low + k * step, 6) for k in range(count + 1)]


def run_it(folder: str, commands: tuple[str, str] | None = None) -> str:
    """How to run a use case, by its ``run.py`` unless ``commands`` and their
    note say otherwise."""
    code, note = commands or (
        f"git clone {REPO}\ncd benchmark\nuv run --extra corpus python usecases/{folder}/run.py",
        "<code>run.py</code> reads the samples, tries to fetch any missing files "
        "and writes <code>results.csv</code>.",
    )
    return f"""<div class="materials"><h3>Run it</h3>
<pre><code>{code}</code></pre>
<p class="note">{note}</p>
</div>"""


RATIO_TICKS = (0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000)
CODECS = {
    "quant-geozl-med-pivco-rms": ("GeoZL PIVCO", "#2e8c8c"),
    "quant-geozl-planar-pfor-rms": ("GeoZL PFOR", "#7a68c2"),
    "jpegxl-distance": ("JPEG XL", "#d0892a"),
}


def curve(rows: list[dict[str, str]], metric: str) -> list[dict]:
    """The points of one codec, one per error bound, over the given samples.

    The samples of one group have the same size, so the ratio over all of them
    is the harmonic mean of their ratios.
    """
    by: dict[float, list] = {}
    for r in rows:
        by.setdefault(float(r["rms_bound"]), []).append(r)
    return [
        {
            "bound": bound,
            "ratio": len(found) / sum(1 / float(r["compression_ratio"]) for r in found),
            "rmse": statistics.median(float(r["rmse"]) for r in found),
            "value": statistics.median(float(r[metric]) for r in found),
        }
        for bound, found in sorted(by.items())
    ]


def ratio_range(points: list[dict]) -> tuple[float, float]:
    low = min(p["ratio"] for p in points) * 0.9
    high = max(p["ratio"] for p in points) * 1.1
    return (
        max([t for t in RATIO_TICKS if t <= low], default=RATIO_TICKS[0]),
        min([t for t in RATIO_TICKS if t >= high], default=RATIO_TICKS[-1]),
    )


def metric_range(points: list[dict], top: float) -> tuple[float, float]:
    """From a round value below the worst point up to ``top``, its best value."""
    worst = min(min(p["value"] for p in points), top - 0.02)
    found = ticks(worst, top)
    step = found[1] - found[0]
    return max(math.floor((worst - top) / step - 1e-9) * step + top, top - 1), top


def scatter(title: str, series: list[tuple], xs, ys, metric: str, short: str) -> str:
    """Each codec at each error bound, its compression ratio against the metric,
    with the bound next to each point."""
    w, h, left, right, top, bottom = 460, 300, 50, 16, 34, 46
    (x0, x1), (low, high) = xs, ys

    def x(v: float) -> float:
        span = math.log10(x1) - math.log10(x0)
        return left + (math.log10(v) - math.log10(x0)) / span * (w - left - right)

    def y(v: float) -> float:
        v = min(max(v, low), high)
        return top + (high - v) / (high - low) * (h - top - bottom)

    out = [f'<text class="title" x="{left}" y="18">{html.escape(title)}</text>']
    for v in ticks(low, high):
        out.append(
            f'<line class="rule" x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
            f'<text class="tick" x="{left - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{v:.2f}</text>'
        )
    for t in RATIO_TICKS:
        if x0 <= t <= x1:
            out.append(
                f'<line class="rule" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top}" y2="{h - bottom}"/>'
                f'<text class="tick" x="{x(t):.1f}" y="{h - bottom + 16}" text-anchor="middle">{t:g}×</text>'
            )
    out.append(
        f'<text class="axis" x="{w - right}" y="{h - 6}" text-anchor="end">compression ratio →</text>'
        f'<text class="axis" x="{w - right}" y="18" text-anchor="end">↑ {metric}</text>'
    )
    for name, colour, points in series:
        path = " ".join(f"{x(p['ratio']):.1f},{y(p['value']):.1f}" for p in points)
        # Bounds that land on the same point, as JPEG XL falling back to lossless,
        # share one label.
        spots: dict[tuple, list] = {}
        for p in points:
            spots.setdefault((round(x(p["ratio"])), round(y(p["value"]))), []).append(p)
        marks = "".join(
            f'<circle cx="{x(p["ratio"]):.1f}" cy="{y(p["value"]):.1f}" r="4.5">'
            f"<title>{html.escape(name)} · RMSE ≤ {p['bound']:g} {short}, measured "
            f"{p['rmse']:.3g} · {p['ratio']:.1f}× · {metric} {p['value']:+.3f}</title></circle>"
            for p in points
        ) + "".join(
            f'<text class="label" x="{x(group[-1]["ratio"]) + 6:.1f}" '
            f'y="{y(group[-1]["value"]) - 7:.1f}">'
            f"{group[0]['bound']:g}{'–' + format(group[-1]['bound'], 'g') if len(group) > 1 else ''}"
            f"{' lossless' if all(p['rmse'] == 0 for p in group) else ''}</text>"
            for group in spots.values()
        )
        out.append(
            f'<g class="series" style="--c:{colour}"><polyline points="{path}"/>{marks}</g>'
        )
    return (
        f'<div class="uc-panel"><svg viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="{html.escape(title)}">{"".join(out)}</svg></div>'
    )


def results_pages(case: dict, lead: str, about: str) -> str:
    """The results page of a use case, and the page of each of its samples."""
    title, folder, metric = case["title"], case["folder"], case["metric"]
    header = f"""{crumbs("../../../", ("Use cases", "usecases/"), (title, f"usecases/{folder}/"), ("Results", None))}
<h1>{html.escape(title)}</h1>
<p class="lead">{inline(lead.strip())}</p>
<section class="measure"><h2>How it is measured</h2>{case["figure"]}<div class="doc">{about}</div></section>"""
    path = ROOT / "usecases" / folder / "results.csv"
    if not path.exists():
        return f"""{header}
<section class="results"><h2>Results</h2><p class="note">Coming soon.</p></section>"""
    group, short = case["group"], case["short"]
    top = 0.0 if metric.startswith("delta") else 1.0
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    measured = {r["id"] for r in rows}
    samples = [s for s in manifest(ROOT / "usecases" / folder) if s["id"] in measured]

    def label(row: dict[str, str]) -> str:
        return case["groups"].get(row[group], row[group]) if group else "All samples"

    def panels(subset: list[dict[str, str]], name: str | None) -> str:
        """One panel per group in ``subset`` with every codec, on shared axes."""
        groups = list(dict.fromkeys(label(r) for r in subset))
        curves = {
            g: [
                (codec_name, colour, curve(found, metric))
                for codec, (codec_name, colour) in CODECS.items()
                if (
                    found := [
                        r for r in subset if label(r) == g and r["codec"] == codec
                    ]
                )
            ]
            for g in groups
        }
        every = [
            p for found in curves.values() for _, _, points in found for p in points
        ]
        xs, ys = ratio_range(every), metric_range(every, top)
        return "".join(
            scatter(name or g, found, xs, ys, metric, short)
            for g, found in curves.items()
        )

    legend = "".join(
        f'<span style="--c:{colour}"><i></i>{html.escape(name)}</span>'
        for name, colour in CODECS.values()
    )
    keys = "".join(
        f'<span class="key k-{kind}">{html.escape(text)}</span>'
        for kind, text in zip(("kept", "lost", "new"), case["keys"], strict=True)
    )
    root = "../../../../"
    cards = []
    for k, s in enumerate(samples):
        sid = s["id"]
        source = usecase_png(folder, sid, "original")
        thumb = resized(source, f"img/usecases/{folder}/{sid}.webp", THUMB, True)
        large = resized(source, f"img/usecases/{folder}/{sid}-large.webp", LARGE, False)
        fields = {**s, **({group: label(s)} if group else {})}
        cards.append(
            card(
                "../../../",
                f"usecases/{folder}/results/{sid}/",
                thumb,
                sid,
                html.escape(case["card"].format(**fields)),
            )
        )
        found = [r for r in rows if r["id"] == sid]
        maps = []
        for codec, (name, _) in CODECS.items():
            mine = sorted(
                (r for r in found if r["codec"] == codec),
                key=lambda r: float(r["rms_bound"]),
            )
            figs = []
            for r in mine:
                image = resized(
                    usecase_png(folder, sid, r["configuration"]),
                    f"img/usecases/{folder}/{sid}/{r['configuration']}.webp",
                    LARGE,
                    False,
                )
                if image is None:
                    continue
                bound = f"{float(r['rms_bound']):g} {short}"
                rmse = float(r["rmse"])
                done = "lossless" if rmse == 0 else f"measured {rmse:.3g}"
                figs.append(
                    f'<figure><img src="{root}{image}" alt="{html.escape(name)} at {bound}">'
                    f"<figcaption><strong>RMSE ≤ {bound}</strong>, {done}<br>"
                    f"{float(r['compression_ratio']):.1f}× · {metric} "
                    f"{float(r[metric]):+.3f}</figcaption></figure>"
                )
            if figs:
                maps.append(
                    f'<h3>{html.escape(name)}</h3><div class="maps">{"".join(figs)}</div>'
                )
        prev_link = (
            f'<a href="../{samples[k - 1]["id"]}/">← {samples[k - 1]["id"]}</a>'
            if k
            else "<span></span>"
        )
        next_link = (
            f'<a href="../{samples[k + 1]["id"]}/">{samples[k + 1]["id"]} →</a>'
            if k + 1 < len(samples)
            else "<span></span>"
        )
        meta = "".join(
            f"<tr><th>{html.escape(key)}</th><td>{html.escape(value)}</td></tr>"
            for key, value in fields.items()
            if key not in HIDDEN_META and value
        )
        body = f"""{crumbs(root, ("Use cases", "usecases/"), (title, f"usecases/{folder}/"), ("Results", f"usecases/{folder}/results/"), (sid, None))}
<h1>{html.escape(sid)}</h1>
<div class="sample">
<div class="figure">{f'<img src="{root}{large}" alt="{html.escape(case["original"])}">' if large else '<div class="noimg"></div>'}
<p class="note">{html.escape(case["original"])}</p></div>
<div><h2>Sample</h2><table class="meta-table">{meta}</table></div>
</div>
<section class="results"><h2>Compression ratio and {metric}</h2>
<p class="note">Each point is a bound on the root-mean-square error, written next to it in {case["unit"]}, on this sample.</p>
<div class="legend uc-legend">{legend}</div><div class="uc-panels wide">{panels(found, sid)}</div></section>
<section class="decoded"><h2>{case["maps"]}</h2>
<p class="note">The result on the compressed copy at each error bound, in {case["unit"]}.{keys}</p>
{"".join(maps)}</section>
<p class="pager">{prev_link}{next_link}</p>"""
        target = OUT / "usecases" / folder / "results" / sid / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(layout(root, f"{sid} · Earth Compress benchmark", body))

    note = (
        f"Each point is a bound on the root-mean-square error, written next to it in "
        f"{case['unit']}, at the compression ratio over all the samples of the panel "
        f"and the median <code>{metric}</code>. Where JPEG XL finds no distance within "
        "the bound it stores the array losslessly, so those bounds share one point, "
        "marked lossless."
    )
    return f"""{header}
<section class="results"><h2>Compression ratio and {metric}</h2><p class="note">{note}</p>
<div class="legend uc-legend">{legend}</div><div class="uc-panels wide">{panels(rows, None)}</div></section>
<section><h2>Samples</h2><div class="grid">{"".join(cards)}</div></section>"""


def usecases() -> None:
    _, *parts = (ROOT / "USECASE.md").read_text().split("\n## ")
    sections = {p.split("\n", 1)[0]: p.split("\n", 1)[1] for p in parts}
    cards = []
    for case in USECASES:
        title, folder, metric = case["title"], case["folder"], case["metric"]
        lead, *blocks = sections[title].split("\n### ")
        blocks = {b.split("\n", 1)[0]: b.split("\n", 1)[1] for b in blocks}

        def md(text: str, root: str = "../../") -> str:
            return linked(markdown.markdown(text, extensions=["tables"]), root)

        path = ROOT / "usecases" / folder / "results.csv"
        if path.exists():
            with path.open(newline="") as stream:
                count = len({r["id"] for r in csv.DictReader(stream)})
        else:
            count = case["samples"]
        source = ROOT / "usecases" / folder / "preview.png"
        source = source if source.exists() else None
        thumb = resized(source, f"img/usecases/{folder}.webp", THUMB, True)
        large = resized(source, f"img/usecases/{folder}-large.webp", LARGE, False)
        # The picture fills the height of the text beside it, so both columns end
        # together.
        figure = (
            f'<div class="pic" role="img" aria-label="{html.escape(case["caption"])}" '
            f"style=\"background-image: url('../../{large}')\"></div>"
            if large
            else '<div class="noimg"></div>'
        )
        body = f"""{crumbs("../../", ("Use cases", "usecases/"), (title, None))}
<h1>{html.escape(title)}</h1>
<p class="lead">{inline(lead.strip())}</p>
<div class="sample usecase">
<div class="figure">{figure}<p class="note">{html.escape(case["caption"])}</p></div>
<div class="experiment"><h2>Experiment</h2>{md(blocks["Experiment"])}
{run_it(folder, case.get("run"))}
<p><a class="button primary" href="results/">Results</a></p></div>
</div>"""
        target = OUT / "usecases" / folder / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(layout("../../", f"{title} · Earth Compress benchmark", body))
        about = md(blocks["Metric"], "../../../") + (
            f"<h3>Compression</h3>{md(blocks['Compression'], '../../../')}"
        )
        target = OUT / "usecases" / folder / "results" / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            layout(
                "../../../",
                f"{title} results · Earth Compress benchmark",
                results_pages(case, lead, about),
            )
        )
        cards.append(
            card(
                "../",
                f"usecases/{folder}/",
                thumb,
                title,
                f"{count} samples · <code>{metric}</code>",
            )
        )
    (OUT / "usecases").mkdir(exist_ok=True)
    (OUT / "usecases" / "index.html").write_text(
        layout(
            "../",
            "Use cases · Earth Compress benchmark",
            f"{crumbs('../', ('Use cases', None))}<h1>Use cases</h1>"
            f'<div class="grid">{"".join(cards)}</div>',
        )
    )


def main() -> None:
    # Build next to the live site and swap it in at the end, so a page being
    # served is never missing while the site is rebuilt.
    global OUT
    final, OUT = OUT, OUT.with_name("dist.next")
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
    build()
    old = final.with_name("dist.old")
    if final.exists():
        final.rename(old)
    OUT.rename(final)
    shutil.rmtree(old, ignore_errors=True)
    print(f"wrote {final}")


if __name__ == "__main__":
    main()
