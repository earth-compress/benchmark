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


def near_rows(corpus: Path) -> list[dict]:
    path = corpus / "results.csv"
    if not path.exists():
        return []
    with path.open(newline="") as stream:
        return [row for row in csv.DictReader(stream) if row["mode"] == "near-lossless"]


LEVELS = ("conservative", "matched", "aggressive", "recommended")


def base(configuration: str) -> str:
    return configuration.rsplit("-", 1)[0]


def near_totals(rows: list[dict]) -> dict[str, dict[str, dict]]:
    """Totals per budget level of each configuration that completed every sample,
    with the promises it broke on any of them."""
    count = len({row["sample_id"] for row in rows})
    out: dict[str, dict[str, dict]] = {}
    for level in LEVELS:
        chosen = [r for r in rows if r["budget_level"] == level]
        for config in sorted({r["configuration"] for r in chosen}):
            mine = [r for r in chosen if r["configuration"] == config]
            if len(mine) != count or any(r["status"] == "crash" for r in mine):
                continue
            broken = [
                promise
                for promise in ("bound", "sentinel", "zero")
                if any(float(r[f"{promise}_violations"] or 0) > 0 for r in mine)
            ]
            out.setdefault(level, {})[base(config)] = {**entry(mine), "broken": broken}
    return out


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


# Small icons for the four modes, drawn on one 16 px grid in the text colour.
MODE_ICONS = (
    (
        "Lossless",
        "lossless/",
        '<rect x="1.5" y="3.5" width="5" height="9" rx="1"/><rect x="9.5" y="3.5" width="5" height="9" rx="1"/>'
        '<path d="M7.6 7h.8M7.6 9h.8"/>',
    ),
    (
        "Near-lossless",
        "near-lossless/",
        '<rect x="1.5" y="3.5" width="13" height="9" rx="1"/><path d="M3.5 8h9" stroke-dasharray="1.5 1.5"/>'
        '<path d="M5 6.5v3M8 7.2v1.6M11 6.2v3.6"/>',
    ),
    (
        "Lossy",
        "lossy/",
        '<rect x="1.5" y="1.5" width="13" height="13" rx="1"/><path d="M8 1.5v13M1.5 8h13"/>'
        '<rect x="2.5" y="2.5" width="4.5" height="4.5" class="fill"/><rect x="9" y="9" width="4.5" height="4.5" class="fill"/>',
    ),
    (
        "Use cases",
        "usecases/",
        '<circle cx="7" cy="7" r="4.5"/><path d="M10.4 10.4 14.5 14.5"/><path d="M5 7.5l1.5 1.5L9.2 5.5"/>',
    ),
)


def mode_switch(root: str) -> str:
    items = "".join(
        f'<a href="{root}{href}" aria-label="{name}" data-label="{name}"><svg viewBox="0 0 16 16" aria-hidden="true">{icon}</svg></a>'
        for name, href, icon in MODE_ICONS
    )
    return f'<nav class="modes-switch" aria-label="Results">{items}</nav>'


def layout(
    root: str,
    title: str,
    body: str,
    chart: dict | None = None,
    script: str = "chart.js",
    nav: bool = True,
) -> str:
    links = (
        "".join(f'<a href="{root}{href}">{name}</a>' for name, href in NAV)
        if nav
        else ""
    )
    links += (
        f'<a class="icon" href="{REPO}" title="GitHub" aria-label="GitHub">{GITHUB_ICON}</a>'
        f'<a class="icon" href="https://huggingface.co/datasets/{HF_DATASET}" title="Hugging Face" '
        f'aria-label="Hugging Face">{HF_ICON}</a>'
    )
    header = (
        f'''<header><div class="wrap bar">
<a class="brand" href="{root}"><img src="{root}earth-compress.svg" alt="Earth Compress benchmark" height="30"></a>
{mode_switch(root)}
<nav>{links}</nav>
</div></header>'''
        if nav
        else ""
    )
    data = (
        f'<script id="chart-data" type="application/json">{json.dumps(chart)}</script>'
        f'<script src="{root}{script}?v={VERSION[script]}" defer></script>'
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
<body{"" if nav else ' class="home-page"'}>
{header}<main class="wrap">
{body}
</main>
<footer><div class="wrap"><p>Part of <a href="https://asterisk.coop/project-pages/earth-compress.html">Earth Compress</a>, funded by <a href="https://www.aria.org.uk/">ARIA</a> and led by the <a href="https://noc.ac.uk/">National Oceanography Centre</a> and <a href="https://asterisk.coop/">Asterisk Labs</a>. <a href="{REPO}/blob/main/LICENSE">Apache 2.0</a>.</p></div></footer>
{data}
<script>document.querySelectorAll(".modes-switch a").forEach(a => {{ if (location.pathname.startsWith(new URL(a.href).pathname)) a.setAttribute("aria-current", "page"); }});</script>
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


NEAR_NOTE = (
    "Each point shows a configuration at this budget level. "
    "The line shows the best observed trade-offs. "
    "The All corpora view pools size and decode time across samples for configurations "
    "completed on every corpus with results at this level. Broken promises are listed below."
)


NO_BUDGET = (
    '<div class="panel soonpanel" role="tabpanel" id="panel-near" hidden><p>This corpus '
    "has no error budget, so it runs in lossless mode only. See "
    '<a href="{root}tolerance/">Tolerance</a>.</p></div>'
)


def sample_links(
    cid: str,
    sid: str,
    exact: bool,
    near: bool,
    lossy: list[tuple[str, str, str]],
    uses: list[tuple[str, str]],
) -> str:
    """Buttons from a sample to every analysis that measured it."""
    root = "../../../"
    links = []
    if exact:
        links.append(("Lossless", f"{root}lossless/{cid}/{sid}/"))
    if near:
        links.append(("Near-lossless", f"{root}near-lossless/{cid}/{sid}/"))
    links += [
        (f"Lossy &middot; {title}", f"{root}lossy/{key}/{lid}/")
        for key, title, lid in lossy
    ]
    links += [
        (f"Use case &middot; {title}", f"{root}usecases/{folder}/results/{sid}/")
        for folder, title in uses
    ]
    if not links:
        return '<p class="note">This sample is not in any analysis yet.</p>'
    buttons = "".join(
        f'<a class="button" href="{href}">{name}</a>' for name, href in links
    )
    return f'<nav class="analyses" aria-label="Analyses of this sample"><span class="analyses-label">Results</span>{buttons}</nav>'


def usecase_scenes() -> dict[str, list[tuple[str, str]]]:
    """Which use cases measured a corpus sample, by sample id."""
    found: dict[str, list[tuple[str, str]]] = {}
    for case in USECASES:
        path = ROOT / "usecases" / case["folder"] / "results.csv"
        if not path.exists():
            continue
        with path.open(newline="") as stream:
            for sid in sorted(
                {r.get("sample_id") or r["id"] for r in csv.DictReader(stream)}
            ):
                found.setdefault(sid, []).append((case["folder"], case["title"]))
    return found


def lossy_scenes() -> dict[tuple[str, str], list[tuple[str, str, str]]]:
    """Which lossy cases measured each corpus sample, as (key, title, lossy id)."""
    found: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for case in LOSSY:
        with (ROOT / "lossy" / case["key"] / "results.csv").open(newline="") as stream:
            scenes = {r["sample_id"] for r in csv.DictReader(stream)}
        for s in manifest(ROOT / "corpora" / case["corpus"]):
            sid = s["id"].replace(*case["rename"]) if case["rename"] else s["id"]
            if sid in scenes:
                found.setdefault((case["corpus"], s["id"]), []).append(
                    (case["key"], case["title"], sid)
                )
    return found


def lossless_block(key: str, caption: str = "") -> str:
    note = f'<p class="chart-note">{caption}</p>' if caption else ""
    return f'<section class="results"><div class="chart" data-chart="{key}"></div>{note}</section>'


def near_block(key: str, levels: tuple[str, ...]) -> str:
    chosen = "matched" if "matched" in levels else (levels or ("",))[0]
    options = "".join(
        f'<option value="{level}"{" selected" if level == chosen else ""}>{level}</option>'
        for level in levels
    )
    return f"""<section class="results"><div class="pick near-pick"><select id="near-corpus" hidden><option value="{key}">{key}</option></select><select id="near-level" aria-label="Budget level">{options}</select></div>
<div class="chart" data-chart="near" data-set="near" data-select="near-corpus,near-level"></div><p class="chart-note">{NEAR_NOTE}</p></section>"""


def chart_block(
    select: str = "",
    key: str = "all",
    caption: str = "",
    near: str = "",
    budget: bool = True,
    root: str = "",
    levels: tuple[str, ...] = LEVELS,
) -> str:
    pick = f'<label class="pick">{select}</label>' if select else ""
    note = f'<p class="chart-note">{caption}</p>' if caption else ""
    chosen = "matched" if "matched" in levels else (levels or ("",))[0]
    levels = "".join(
        f'<option value="{level}"{" selected" if level == chosen else ""}>{level}</option>'
        for level in levels
    )
    corpus = (
        near.replace('id="corpus"', 'id="near-corpus"')
        if near
        else f'<select id="near-corpus" hidden><option value="{key}">{key}</option></select>'
    )
    near_panel = f"""<div class="panel" role="tabpanel" id="panel-near" hidden>
<div class="pick near-pick">{corpus}<select id="near-level" aria-label="Budget level">{levels}</select></div>
<div class="chart" data-chart="near" data-set="near" data-select="near-corpus,near-level"></div><p class="chart-note">{NEAR_NOTE}</p></div>"""
    if not budget:
        near_panel = NO_BUDGET.format(root=root)
    return f"""<section class="results">
<div class="controls">
<div class="tabs" role="tablist" aria-label="Fidelity mode">
<button type="button" role="tab" aria-controls="panel-lossless" aria-selected="true">Lossless</button>
<button type="button" role="tab" aria-controls="panel-near" aria-selected="false">Near-lossless</button>
</div>
{pick}
</div>
<div class="panel" role="tabpanel" id="panel-lossless"><div class="chart" data-chart="{key}"{' data-select="corpus"' if select else ""}></div>{note}</div>
{near_panel}
</section>"""


def families(corpora: Path) -> dict[str, str]:
    """The family of every near-lossless configuration, from the results."""
    out: dict[str, str] = {}
    for path in sorted(corpora.glob("*/results.csv")):
        for row in near_rows(path.parent):
            out[base(row["configuration"])] = row["family"]
    return out


def near_chart(
    by_corpus: dict[str, dict], groups: dict[str, str], pooled: bool = False
) -> dict:
    data = {
        f"{cid}|{level}": totals
        for cid, levels in by_corpus.items()
        for level, totals in levels.items()
    }
    if pooled:
        for level in LEVELS:
            here = {cid: levels.get(level, {}) for cid, levels in by_corpus.items()}
            pooled_totals = summary(here)
            for config, total in pooled_totals.items():
                total["broken"] = sorted(
                    {
                        b
                        for t in here.values()
                        if config in t
                        for b in t[config]["broken"]
                    }
                )
            data[f"all|{level}"] = pooled_totals
    return {"data": data, "codecs": sorted(groups), "groups": groups, "reference": None}


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
        page = document(name)
        if slug == "protocol":
            # How the lossy runs are measured belongs with the rest of the protocol.
            method = LOSSY_METHOD.split('<div class="doc">', 1)[1].rsplit(
                "</div></section>", 1
            )[0]
            page = page.replace(
                "</article>", f'<h2 id="lossy">Lossy</h2>{method}</article>'
            )
        target.write_text(layout("../", f"{title} · Earth Compress benchmark", page))

    datasets = table((ROOT / "DATASETS.md").read_text(), "## Corpora")
    lossless = table((ROOT / "CODECS.md").read_text(), "## Lossless")
    official = [row for row in lossless if row["group"] != "Reference"]
    codecs = [plain(r["id"]) for r in official]
    reference = next(
        (plain(row["id"]) for row in lossless if row["group"] == "Reference"), None
    )
    style = {
        "groups": {plain(r["id"]): r["group"] for r in official},
        "reference": reference,
    }

    near_families = families(ROOT / "corpora")
    corpus_totals: dict[str, dict] = {}
    near_totals_by: dict[str, dict] = {}
    sample_counts: dict[str, int] = {}
    corpus_cards = []
    lossy_by_sample = lossy_scenes()
    uses_by_sample = usecase_scenes()
    for row in datasets:
        cid = plain(row["corpus"])
        folder = ROOT / "corpora" / cid
        samples = manifest(folder)
        sample_counts[cid] = len(samples)
        rows = lossless_rows(folder)
        found = totals(rows)
        by_sample = per_sample(rows)
        corpus_totals[cid] = found
        mine = near_rows(folder)
        near = near_totals(mine)
        near_by_sample = {
            sid: near_totals([r for r in mine if r["sample_id"] == sid])
            for sid in {r["sample_id"] for r in mine}
        }
        near_totals_by[cid] = near
        levels = tuple(level for level in LEVELS if level in near)
        meta = f"{inline(row['shape'])} · {inline(row['dtype'])}"

        sample_cards = []
        exact_cards = []
        near_cards = []
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
<div class="sample">
<div class="figure">{f'<img src="../../../{large}" alt="Preview of {html.escape(s["id"])}">' if large else '<div class="noimg"></div>'}
{sample_links(cid, s["id"], s["id"] in by_sample, bool(near_by_sample.get(s["id"])), lossy_by_sample.get((cid, s["id"]), []), uses_by_sample.get(s["id"], []))}
{f'<p><a class="button" href="{download}">Download {html.escape(Path(s["npz_path"]).name)}</a></p>' if download else ""}</div>
<div><h2>Metadata</h2>
{metadata(s)}</div>
</div>
<p class="pager">{prev_link}{next_link}</p>"""
            target = OUT / "datasets" / cid / s["id"] / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                layout(
                    "../../../",
                    f"{s['id']} · Earth Compress benchmark",
                    body,
                )
            )
            where = html.escape(" · ".join(x for x in (s.get("site", ""), when) if x))
            figure = (
                f'<div class="figure"><img src="../../../{large}" alt="Preview of {html.escape(s["id"])}"></div>'
                if large
                else ""
            )
            for mode, title, cards, block, payload in (
                (
                    "lossless",
                    "Lossless",
                    exact_cards,
                    lossless_block(s["id"]),
                    {
                        "data": {s["id"]: by_sample.get(s["id"], {})},
                        "codecs": codecs,
                        **style,
                    },
                ),
                (
                    "near-lossless",
                    "Near-lossless",
                    near_cards,
                    near_block(s["id"], levels),
                    {
                        "data": {},
                        "codecs": codecs,
                        **style,
                        "near": near_chart(
                            {s["id"]: near_by_sample.get(s["id"], {})}, near_families
                        ),
                    },
                ),
            ):
                if mode == "near-lossless" and not near:
                    continue
                cards.append(
                    card("../../", f"{mode}/{cid}/{s['id']}/", thumb, s["id"], where)
                )
                page = f"""{crumbs("../../../", (title, f"{mode}/"), (cid, f"{mode}/{cid}/"), (s["id"], None))}
<h1>{html.escape(s["id"])}</h1>
<p class="lead">{where} &middot; <a href="../../../datasets/{cid}/{s["id"]}/">sample details</a></p>
{block}
{figure}
<p class="pager">{prev_link}{next_link}</p>"""
                out = OUT / mode / cid / s["id"] / "index.html"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(
                    layout(
                        "../../../",
                        f"{s['id']} {title.lower()} · Earth Compress benchmark",
                        page,
                        payload,
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
<p class="folder"><a href="../../lossless/{cid}/">Lossless results</a>{f' &middot; <a href="../../near-lossless/{cid}/">Near-lossless results</a>' if near else ""} &middot; <a href="{REPO}/tree/main/corpora/{cid}">Folder on GitHub</a></p>
<section><h2>Samples</h2>{'<div class="grid">' + "".join(sample_cards) + "</div>" if sample_cards else '<p class="note">Not built yet.</p>'}</section>"""
        target = OUT / "datasets" / cid / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            layout(
                "../../",
                f"{cid} · Earth Compress benchmark",
                body,
            )
        )
        for mode, title, cards, block, payload in (
            (
                "lossless",
                "Lossless",
                exact_cards,
                lossless_block(cid),
                {"data": {cid: found}, "codecs": codecs, **style},
            ),
            (
                "near-lossless",
                "Near-lossless",
                near_cards,
                near_block(cid, levels),
                {
                    "data": {},
                    "codecs": codecs,
                    **style,
                    "near": near_chart({cid: near}, near_families),
                },
            ),
        ):
            if mode == "near-lossless" and not near:
                continue
            page = f"""{crumbs("../../", (title, f"{mode}/"), (cid, None))}
<h1>{cid}</h1>
<p class="lead">{len(samples)} samples of <a href="../../datasets/{cid}/"><code>{cid}</code></a>, {inline(row["contents"])}.</p>
{block}
<section><h2>Samples</h2><div class="grid">{"".join(cards)}</div></section>"""
            out = OUT / mode / cid / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                layout(
                    "../../",
                    f"{cid} {title.lower()} · Earth Compress benchmark",
                    page,
                    payload,
                )
            )
        corpus_cards.append((cid, f"datasets/{cid}/", first, meta))

    measured = [cid for cid, found in corpus_totals.items() if found]
    options = "".join(f'<option value="{cid}">{cid}</option>' for cid in measured)
    select = f'<select id="corpus" aria-label="Corpus"><option value="all">All corpora</option>{options}</select>'
    budgeted = "".join(
        f'<option value="{cid}">{cid}</option>'
        for cid in measured
        if near_totals_by.get(cid)
    )
    near_select = f'<select id="corpus" aria-label="Corpus"><option value="all">All corpora</option>{budgeted}</select>'
    chart = {
        "data": {
            "all": summary(corpus_totals),
            **{c: corpus_totals[c] for c in measured},
        },
        "codecs": codecs,
        **style,
        "near": near_chart(near_totals_by, near_families, pooled=True),
    }
    grid = "".join(
        card("", href, image, cid, meta) for cid, href, image, meta in corpus_cards
    )
    samples = sum(sample_counts[cid] for cid in measured)
    budgeted = [cid for cid in measured if near_totals_by.get(cid)]
    budgeted_samples = sum(sample_counts[cid] for cid in budgeted)
    modes = (
        (
            "Lossless",
            "lossless/",
            "Decoded values match the input exactly.",
            f"{len(measured)} corpora &middot; {samples} samples",
        ),
        (
            "Near-lossless",
            "near-lossless/",
            "Each valid value has an error bound. Zeros and NoData must be preserved.",
            f"{len(budgeted)} corpora &middot; {budgeted_samples} samples",
        ),
        (
            "Lossy",
            "lossy/",
            "Compare georvq with other codecs by size, decode speed and measured error.",
            "Sentinel-2 &middot; AlphaEarth",
        ),
        (
            "Use cases",
            "usecases/",
            "Compare analyses before and after compression.",
            "methane &middot; drainage &middot; change &middot; clouds",
        ),
    )

    def large(cid: str, n: int = 0) -> tuple[str, str] | None:
        found = sorted((OUT / "img" / cid).glob(f"*-{n:02d}-large.webp"))
        return (found[0].relative_to(OUT).as_posix(), cid) if found else None

    def pick(prefer: list[str], pool: list[str]) -> list[tuple[str, str]]:
        chosen = [c for c in prefer if c in pool] + [c for c in pool if c not in prefer]
        return [x for x in (large(c) for c in chosen) if x][:4]

    exact = pick(
        ["s2-l1c-10m-4", "cop-dem-glo30", "era5-t2m-1h", "s1-grd-iw-2"], measured
    )
    shown = {cid for _, cid in exact}
    pictures = (
        exact,
        pick(
            ["imerg-pcp-12", "l8-oli-8", "emit-l2a-285", "era5-tcc-1h"],
            [c for c in budgeted if c not in shown],
        ),
        [
            x
            for x in (
                large("s2-l1c-10m-4", 1),
                large("alphaearth-v1-64", 0),
                large("s2-l1c-10m-4", 2),
                large("alphaearth-v1-64", 1),
            )
            if x
        ],
        [
            (f"img/usecases/{name}-large.webp", label)
            for name, label in (
                ("methane", "methane"),
                ("drainage", "drainage"),
                ("change-detection", "change detection"),
                ("clouds-decoded", "clouds"),
            )
        ],
    )

    def strip(images: list[tuple[str, str]], offset: int) -> str:
        frames = "".join(
            f'<span class="mode-frame" style="--i:{k};--o:{offset}">'
            f'<img src="{src}" alt="" loading="lazy"><span class="mode-tag">{html.escape(label)}</span></span>'
            for k, (src, label) in enumerate(images)
        )
        return f'<span class="mode-media" aria-hidden="true">{frames}</span>'

    entries = "".join(
        f'<a class="mode" href="{href}">{strip(pictures[i - 1], i)}<span class="mode-num">0{i}</span>'
        f'<span class="mode-name">{name}<span class="mode-arrow" aria-hidden="true">&rarr;</span></span>'
        f'<span class="mode-text">{text}</span><span class="mode-stat">{stat}</span></a>'
        for i, (name, href, text, stat) in enumerate(modes, 1)
    )
    intro = (
        '<div class="home-intro"><h1><img src="earth-compress.svg" alt="Earth Compress benchmark"></h1>'
        f"<p>Compression results for {samples} samples in {len(measured)} corpora of imagery, "
        "environmental fields and embeddings.</p></div>"
    )
    (OUT / "index.html").write_text(
        layout(
            "",
            "Earth Compress benchmark",
            f'<div class="home">{intro}<div class="modes-grid">{entries}</div></div>',
            nav=False,
        )
    )
    caption = (
        "Each point shows a codec configuration. "
        "The line connects the best observed trade-offs."
    )
    (OUT / "lossless").mkdir(exist_ok=True)
    (OUT / "lossless" / "index.html").write_text(
        layout(
            "../",
            "Lossless · Earth Compress benchmark",
            f"""{crumbs("../", ("Lossless", None))}
<h1>Lossless</h1>
<p class="lead">Lossless decodes reproduce the input values exactly.</p>
<section class="results"><div class="pick near-pick">{select}</div>
<div class="chart" data-chart="all" data-select="corpus"></div><p class="chart-note">{caption}</p></section>
<section><h2>Datasets</h2><div class="grid">{"".join(card("../", f"lossless/{cid}/", image, cid, meta) for cid, _, image, meta in corpus_cards if cid in measured)}</div></section>""",
            chart,
        )
    )
    levels = "".join(
        f'<option value="{level}"{" selected" if level == "matched" else ""}>{level}</option>'
        for level in LEVELS
    )
    (OUT / "near-lossless").mkdir(exist_ok=True)
    (OUT / "near-lossless" / "index.html").write_text(
        layout(
            "../",
            "Near-lossless · Earth Compress benchmark",
            f"""{crumbs("../", ("Near-lossless", None))}
<h1>Near-lossless</h1>
<p class="lead">Every valid value has an error bound. Zeros and NoData must be preserved. Available levels depend on the corpus. See <a href="../tolerance/">Tolerance</a>.</p>
<section class="results"><div class="pick near-pick">{near_select.replace('id="corpus"', 'id="near-corpus"')}<select id="near-level" aria-label="Budget level">{levels}</select></div>
<div class="chart" data-chart="near" data-set="near" data-select="near-corpus,near-level"></div><p class="chart-note">{NEAR_NOTE}</p></section>
<section><h2>Datasets</h2><div class="grid">{"".join(card("../", f"near-lossless/{cid}/", image, cid, meta) for cid, _, image, meta in corpus_cards if cid in budgeted)}</div></section>""",
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
    lossy_page()


# Lossy

LOSSY_CODECS = {
    "georvq-s2-v1": ("georvq", "#d6456b"),
    "georvq-ae-v2": ("georvq", "#d6456b"),
    "jpegxl-distance": ("JPEG XL", "#d0892a"),
    "jpeg2000-psnr": ("JPEG 2000", "#6d87a3"),
    "sperr-psnr": ("SPERR", "#7a68c2"),
    "sz3-l2norm": ("SZ3", "#8aa09f"),
    "quant-geozl-med-entropy-rms": ("quant + GeoZL", "#2e8c8c"),
    "quant-pco-rms": ("quant + PCO", "#a39b4a"),
}
LOSSY = (
    {
        "key": "s2",
        "title": "Sentinel-2 L1C",
        "georvq": "georvq-s2-v1",
        "corpus": "s2-l1c-10m-4",
        "rename": ("s2-l1c-10m-4", "s2-l1c"),
        "original": 89.3,
        "side": 504,
        "pixel": "10 m pixel",
        "metrics": {
            "rmse_10m": ("RMSE of the 10 m bands", "DN", "rms"),
            "rmse_20m": ("RMSE of the 20 m bands", "DN", "rms"),
            "rmse_60m": ("RMSE of the 60 m bands", "DN", "rms"),
            "rmse_all": ("RMSE of all 13 bands", "DN", "rms"),
        },
        "targets": ("rmse_10m", (20, 40, 100, 200), "{:g} DN"),
        "stops": (0.3, 0.5, 1, 2, 3, 6),
        "start": 1,
        "scale": "0 to 250 DN",
    },
    {
        "key": "alphaearth",
        "title": "AlphaEarth",
        "georvq": "georvq-ae-v2",
        "corpus": "alphaearth-v1-64",
        "rename": None,
        "original": 512,
        "side": 512,
        "pixel": "pixel",
        "metrics": {
            "cos_mean": ("mean 1 − cos", "", "mean"),
            "cos_p99": ("99th percentile of 1 − cos", "", "mean"),
            "rmse_codes": ("RMSE of the int8 codes", "codes", "rms"),
        },
        "targets": ("cos_mean", (0.002, 0.005, 0.01, 0.02), "{:g}"),
        "stops": (0.2, 0.5, 1, 2, 4, 8),
        "start": 0.5,
        "scale": "0 to 0.05",
    },
)


def lossy_curves(rows: list[dict], metrics: dict) -> dict[str, list[dict]]:
    """Each codec at each setting over every sample: the mean rate, and each
    metric pooled as its definition allows. The samples of one dataset have the
    same size, so a mean of squares is the square over all of them."""
    out: dict[str, list[dict]] = {}
    for codec in LOSSY_CODECS:
        mine = [r for r in rows if r["codec"] == codec]
        settings = list(dict.fromkeys(r["setting"] for r in mine))
        points = []
        for setting in settings:
            found = [r for r in mine if r["setting"] == setting]
            point = {
                "setting": setting,
                "bpp": statistics.mean(float(r["bits_per_pixel"]) for r in found),
                "encode_s": statistics.mean(float(r["encode_s"]) for r in found),
                "decode_s": statistics.mean(float(r["decode_s"]) for r in found),
            }
            for key, (_, _, pool) in metrics.items():
                values = [float(r[key]) for r in found]
                point[key] = (
                    math.sqrt(statistics.mean(v * v for v in values))
                    if pool == "rms"
                    else statistics.mean(values)
                )
            points.append(point)
        if points:
            out[codec] = sorted(points, key=lambda p: p["bpp"])
    return out


LOSSY_METHOD = f"""<section class="measure"><h2>How it is measured</h2><div class="doc">
<ul>
<li><a href="https://github.com/earth-compress/georvq">georvq</a> stores every depth in one file. A reader stops at the depth it needs. Size is the bit count of the bundle for that depth. Model weights are not counted.</li>
<li>The 50 Sentinel-2 scenes are cut to the 504 px footprint shared by the 10, 20 and 60 m grids. The comparison includes all 13 bands.</li>
<li>AlphaEarth uses 15 samples of 512 px. Error is the cosine distance of the dequantised embedding.</li>
<li>Compression ratio is raw array bytes over compressed bytes. Decode speed is single threaded on one CPU.</li>
<li>We have not checked whether these scenes were in georvq's training data.</li>
</ul>
<pre><code>git clone {REPO}
cd benchmark
uv run --extra learned python lossy/s2/run.py
uv run --extra learned python lossy/alphaearth/run.py
uv run --extra learned python lossy/views.py</code></pre>
</div></section>"""


def lossy_panel(case: dict, scene: str, viewer: str = "") -> str:
    """The charts of one scene, or of every scene with ``all``, with the viewer
    when given."""
    options = "".join(
        f'<option value="{key}">{html.escape(name)}</option>'
        for key, (name, _, _) in case["metrics"].items()
    )
    return f"""<section class="results"><div class="panel lossy" data-set="{case["key"]}" data-scene="{scene}">
<div class="pick near-pick"><select class="metric" aria-label="Error">{options}</select></div>
<div class="lossy-charts"><div class="chart speed"></div><div class="chart rd"></div></div>
<p class="chart-note">Each point shows a codec setting. Lines connect settings of the same codec. The georvq settings on a line come from one file.</p>
{viewer}
</div></section>"""


def lossy_viewer(case: dict, sample: str) -> str:
    modes = ("image", "error") + (
        ("similarity",) if case["key"] == "alphaearth" else ()
    )
    return f"""<div class="viewer" data-sample="{sample}">
<h3>Compare decodes</h3>
<div class="viewer-controls">
<label class="rate">Rate <input type="range" min="0" max="{len(case["stops"]) - 1}" step="1"><output></output></label>
<select class="other" aria-label="Codec on the right"></select>
<div class="modes" role="group" aria-label="View">{"".join(f'<button type="button" data-mode="{m}">{m}</button>' for m in modes)}</div>
</div>
<div class="viewer-body">
<div class="stage"><canvas class="right"></canvas><canvas class="left"></canvas><div class="handle"><span></span></div><div class="target" hidden></div>
<p class="side left"></p><p class="side right"></p></div>
<div class="viewer-side">
<p class="mode-note note"></p>
<h4>One georvq file</h4>
<div class="onefile"><div class="bar"></div><p class="note"></p></div>
{'<h4>Detail after decoding</h4><div class="chart spectrum"></div>' if case["key"] == "s2" else ""}
</div>
</div>
</div>"""


def lossy_site(corpus_rows: dict[str, dict], sid: str) -> str:
    return corpus_rows.get(sid, {}).get("site", sid).replace("-", " ").title()


def lossy_payload(
    case: dict,
    rows: list[dict],
    scenes: list[str],
    codecs: list[str],
    samples: dict,
    corpus_rows: dict[str, dict],
    only: str | None,
    base: str,
) -> dict:
    metrics = list(case["metrics"])
    return {
        case["key"]: {
            "columns": ["scene", "codec", "setting", "bpp", "decode_s", *metrics],
            "rows": [
                [
                    scenes.index(r["sample_id"]),
                    codecs.index(r["codec"]),
                    r["setting"],
                    round(float(r["bits_per_pixel"]), 5),
                    round(float(r["decode_s"]), 5),
                    *(float(f"{float(r[m]):.5g}") for m in metrics),
                ]
                for r in rows
                if r["codec"] in codecs and only in (None, r["sample_id"])
            ],
            "scenes": [[sid, lossy_site(corpus_rows, sid)] for sid in scenes],
            "original": case["original"],
            "input": case["original"] * case["side"] ** 2 / 8,
            "metrics": {k: list(v) for k, v in case["metrics"].items()},
            "codecs": {c: list(LOSSY_CODECS[c]) for c in codecs},
            "georvq": case["georvq"],
            "stops": case["stops"],
            "start": case["start"],
            "samples": {only: samples[only]} if only in samples else {},
            "base": base,
        }
    }


def lossy_page() -> None:
    dataset_cards = []
    for case in LOSSY:
        key = case["key"]
        folder = ROOT / "lossy" / key
        with (folder / "results.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        curves = lossy_curves(rows, case["metrics"])
        corpus_rows = {}
        for s in manifest(ROOT / "corpora" / case["corpus"]):
            sid = s["id"].replace(*case["rename"]) if case["rename"] else s["id"]
            corpus_rows[sid] = s
        samples = {}
        for path in sorted((folder / "views").glob("*/sample.json")):
            sid = path.parent.name
            shutil.copytree(path.parent, OUT / "lossy" / key / sid)
            samples[sid] = json.loads(path.read_text())
        scenes = sorted({r["sample_id"] for r in rows})
        codecs = [c for c in LOSSY_CODECS if c in curves]

        cards = []
        first = None
        for i, sid in enumerate(scenes):
            source = folder / "views" / sid / "original.webp"
            thumb = resized(
                source if source.exists() else None,
                f"img/lossy/{key}/{sid}.webp",
                THUMB,
                True,
            )
            first = first or thumb
            cards.append(
                card(
                    "../../",
                    f"lossy/{key}/{sid}/",
                    thumb,
                    sid,
                    html.escape(lossy_site(corpus_rows, sid)),
                )
            )
            prev_link = (
                f'<a href="../{scenes[i - 1]}/">← {scenes[i - 1]}</a>'
                if i
                else "<span></span>"
            )
            next_link = (
                f'<a href="../{scenes[i + 1]}/">{scenes[i + 1]} →</a>'
                if i + 1 < len(scenes)
                else "<span></span>"
            )
            body = f"""{crumbs("../../../", ("Lossy", "lossy/"), (case["title"], f"lossy/{key}/"), (sid, None))}
<h1>{html.escape(sid)}</h1>
<p class="lead">{html.escape(lossy_site(corpus_rows, sid))}</p>
{lossy_panel(case, str(i), lossy_viewer(case, sid) if sid in samples else "")}
<p class="pager">{prev_link}{next_link}</p>"""
            target = OUT / "lossy" / key / sid / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                layout(
                    "../../../",
                    f"{sid} · Earth Compress benchmark",
                    body,
                    lossy_payload(
                        case, rows, scenes, codecs, samples, corpus_rows, sid, "../"
                    ),
                    script="lossy.js",
                )
            )

        body = f"""{crumbs("../../", ("Lossy", "lossy/"), (case["title"], None))}
<h1>{case["title"]}</h1>
<p class="lead">{len(scenes)} samples of <a href="../../datasets/{case["corpus"]}/"><code>{case["corpus"]}</code></a>.</p>
{lossy_panel(case, "all")}
<section><h2>Samples</h2><div class="grid">{"".join(cards)}</div></section>"""
        target = OUT / "lossy" / key / "index.html"
        target.write_text(
            layout(
                "../../",
                f"{case['title']} lossy · Earth Compress benchmark",
                body,
                lossy_payload(
                    case, rows, scenes, codecs, samples, corpus_rows, None, ""
                ),
                script="lossy.js",
            )
        )
        dataset_cards.append(
            card(
                "../",
                f"lossy/{key}/",
                first,
                case["title"],
                f"{len(scenes)} samples · <code>{case['georvq']}</code>",
            )
        )

    body = f"""{crumbs("../", ("Lossy", None))}
<h1>Lossy</h1>
<p class="lead">Compare the learned codec georvq with the benchmark's lossy configurations.</p>
<section><div class="grid">{"".join(dataset_cards)}</div></section>"""
    (OUT / "lossy" / "index.html").write_text(
        layout("../", "Lossy · Earth Compress benchmark", body)
    )


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
    title: str = "Compressed copy",
    original_title: str | None = None,
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
<g><text class="h" x="0" y="16">{original_title or f"Original {name}"}</text>{before}
<text x="0" y="200">{found[0]}</text><text x="0" y="218">{found[1]}</text></g>
<g transform="translate(244 0)">
<text x="0" y="104">{again[0]}</text><text x="0" y="122">{again[1]}</text><text x="0" y="140">{again[2]}</text>
<path d="M2 154 H58 M50 148 L58 154 L50 160" fill="none" stroke="#8aa09f" stroke-width="2"/>
</g>
<g transform="translate(316 0)"><text class="h" x="0" y="16">{title}</text>{after}</g>
<g transform="translate(566 0)">
<text class="h" x="0" y="16">{metric}</text>
<text class="m" x="0" y="44">= overlap / union</text>
<text class="m" x="0" y="64">= {kept} / {union} = {kept / union:.2f}</text>
<rect x="0" y="92" width="12" height="12" rx="2" fill="#f59e0b"/><text x="20" y="102">{both}</text>
<rect x="0" y="116" width="12" height="12" rx="2" fill="#38bdf8"/><text x="20" y="126">lost</text>
<rect x="0" y="140" width="12" height="12" rx="2" fill="#f43f5e"/><text x="20" y="150">new</text>
</g>
</svg>"""


def cell(x: float, y: float, text: str, fill: str, ink: str = "#fff") -> str:
    """One labelled pixel of a schematic."""
    return (
        f'<rect x="{x}" y="{y}" width="40" height="32" rx="2" fill="{fill}"/>'
        f'<text class="m" x="{x + 20}" y="{y + 20}" text-anchor="middle" '
        f'style="fill:{ink}">{text}</text>'
    )


def hatch(name: str) -> str:
    """The pattern of pixels that a metric leaves out."""
    return (
        f'<defs><pattern id="{name}" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><rect width="6" height="6" fill="#e3eaea"/>'
        '<rect width="2" height="6" fill="#8aa09f"/></pattern></defs>'
    )


def changed(change: float) -> tuple[str, str]:
    """The fill and text colours of a change in height, as on the maps."""
    if change == 0:
        return "#f7f7f7", "#143031"
    if abs(change) < 1.5:
        return ("#92c5de", "#143031") if change < 0 else ("#f4a582", "#143031")
    return ("#2166ac", "#fff") if change < 0 else ("#b2182b", "#fff")


def arrow(*words: str) -> str:
    lines = "".join(
        f'<text x="0" y="{104 + 18 * k}">{word}</text>' for k, word in enumerate(words)
    )
    return (
        f'<g transform="translate(244 0)">{lines}<path d="M2 154 H58 M50 148 L58 154 '
        'L50 160" fill="none" stroke="#8aa09f" stroke-width="2"/></g>'
    )


def height_figure() -> str:
    """How the height metrics compare two grids of made-up heights, in km."""
    original = (
        (2, 2, 3, None, None),
        (3, 8, 9, 9, None),
        (3, 9, 10, 10, 9),
        (None, 8, 9, 9, 8),
    )
    copy = (
        (2, 2, 3, None, 2),
        (3, 7, 8, 8, None),
        (4, 8, 9, 8, 8),
        (None, 8, 8, None, 7),
    )
    before, after, changes = [], [], []
    out = "url(#height-out)"
    for r, (row0, row1) in enumerate(zip(original, copy, strict=True)):
        for c, (a, b) in enumerate(zip(row0, row1, strict=True)):
            x, y = c * 42, 26 + r * 36
            if a is None or b is None:
                before.append(cell(x, y, "" if a is None else a, out, "#143031"))
                after.append(cell(x, y, "" if b is None else b, out, "#143031"))
            else:
                before.append(cell(x, y, a, "#143031"))
                after.append(cell(x, y, b, *changed(b - a)))
                changes.append(b - a)
    mae = sum(abs(d) for d in changes) / len(changes)
    bias = sum(changes) / len(changes)
    return f"""<svg class="explain" viewBox="0 0 800 236" role="img" aria-label="How the cloud top height metrics compare the heights from compressed data with those from the original data">
{hatch("height-out")}
<g><text class="h" x="0" y="16">From original data</text>{"".join(before)}
<text x="0" y="192">Heights in km. Clouds Decoded gives no height for some</text>
<text x="0" y="208">cloudy pixels, and which ones can change with compression.</text></g>
{arrow("compress,", "decode,", "run CD")}
<g transform="translate(316 0)"><text class="h" x="0" y="16">From compressed data</text>{"".join(after)}</g>
<g transform="translate(566 0)">
<text class="m" x="0" y="20">2. cth_mae  = mean(|change|)</text>
<text class="m" x="0" y="38">            = {mae:.2f} km</text>
<text class="m" x="0" y="62">3. cth_bias = mean(change)</text>
<text class="m" x="0" y="80">            = {bias:+.2f} km</text>
<rect x="0" y="102" width="12" height="12" rx="2" fill="#b2182b"/><text x="20" y="112">higher than the original</text>
<rect x="0" y="124" width="12" height="12" rx="2" fill="#2166ac"/><text x="20" y="134">lower than the original</text>
<rect x="0" y="146" width="12" height="12" rx="2" fill="#f7f7f7" stroke="#8aa09f"/><text x="20" y="156">unchanged</text>
<rect x="0" y="168" width="12" height="12" rx="2" fill="{out}"/><text x="20" y="178">left out: no height in both</text>
</g>
</svg>"""


def tau_figure() -> str:
    """How the median relative error treats thin and thick cloud alike."""
    original = (0.5, 1, 2, 5, 10, 20, 50, 80)
    copy = (0.6, 1.1, 2.2, 5.1, 10.5, 21, 49, 82)
    errors = [abs(b / a - 1) for a, b in zip(original, copy, strict=True)]
    ordered = sorted(errors)
    median = (ordered[3] + ordered[4]) / 2
    x = [k * 44 for k in range(8)]
    tops = "".join(cell(x[k], 26, f"{v:g}", "#143031") for k, v in enumerate(original))
    lows = "".join(cell(x[k], 72, f"{v:g}", "#143031") for k, v in enumerate(copy))
    errs = "".join(
        f'<text class="m" x="{x[k] + 20}" y="126" text-anchor="middle">{100 * e:.0f}%</text>'
        for k, e in enumerate(errors)
    )
    return f"""<svg class="explain" viewBox="0 0 800 190" role="img" aria-label="How tau_median_rel_error compares the optical thickness of the compressed copy with the original one">
<g transform="translate(112 0)">{tops}{lows}{errs}
<text x="0" y="164">Only pixels with τ above 0 from both are used.</text></g>
<text class="h" x="0" y="46">Original τ</text><text class="h" x="0" y="92">Compressed τ</text><text x="0" y="126">relative change</text>
<g transform="translate(484 0)">
<text class="h" x="0" y="16">4. tau_median_rel_error</text>
<text class="m" x="0" y="44">= median(|compressed / original − 1|)</text>
<text class="m" x="0" y="64">= {100 * median:.1f}%</text>
</g>
</svg>"""


def radius_figure() -> str:
    """Which pixels the ice radius metrics use, and how the error is computed."""
    original = (
        ("ice", 30),
        ("ice", 28),
        ("ice", 35),
        ("ice", 40),
        ("mix", None),
        ("liq", None),
    )
    copy = (
        ("ice", 32),
        ("ice", 27),
        ("ice", 35),
        ("liq", None),
        ("ice", 31),
        ("liq", None),
    )
    kept = [
        abs(b[1] - a[1])
        for a, b in zip(original, copy, strict=True)
        if a[0] == "ice" and b[0] == "ice"
    ]
    out = "url(#radius-out)"
    top, low, marks = [], [], []
    for k, (a, b) in enumerate(zip(original, copy, strict=True)):
        x = k * 44
        used = a[0] == "ice" and b[0] == "ice"
        fill = "#7dd3fc" if used else out
        top.append(cell(x, 26, a[1] if a[1] else a[0], fill, "#143031"))
        low.append(cell(x, 72, b[1] if b[1] else b[0], fill, "#143031"))
        marks.append(
            f'<text x="{x + 20}" y="126" text-anchor="middle">{"used" if used else "out"}</text>'
        )
    return f"""<svg class="explain" viewBox="0 0 800 190" role="img" aria-label="How re_ice_mae picks the ice pixels and compares their radius">
{hatch("radius-out")}
<g transform="translate(112 0)">{"".join(top)}{"".join(low)}{"".join(marks)}
<text x="0" y="164">A pixel counts if its ice/liquid ratio is above 0.6 in the original and above 0.5 in compressed.</text>
<text x="0" y="182">Products with fewer than 1000 such pixels have no value.</text></g>
<text class="h" x="0" y="46">Original rₑ</text><text class="h" x="0" y="92">Compressed rₑ</text>
<g transform="translate(484 0)">
<text class="h" x="0" y="16">5. re_ice_mae</text>
<text class="m" x="0" y="44">= mean(|compressed − original|)</text>
<text class="m" x="0" y="64">= ({" + ".join(str(k) for k in kept)}) / {len(kept)} = {sum(kept) / len(kept):.2f} µm</text>
<rect x="0" y="86" width="12" height="12" rx="2" fill="#7dd3fc"/><text x="20" y="96">ice in both: used</text>
<rect x="0" y="108" width="12" height="12" rx="2" fill="{out}"/><text x="20" y="118">left out: flipped or not ice in the original</text>
</g>
</svg>"""


def texture_figure() -> str:
    """How the texture ratio compares the steps between neighbouring pixels."""
    original = (30, 31, 30, 32, 31, 30, 31, 32)
    copy = (30, 33, 29, 34, 30, 31, 34, 30)
    ramp = ("#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725")
    """Viridis from the smallest value, 29, to the largest, 34."""

    def steps(values: tuple) -> list[int]:
        return [abs(b - a) for a, b in zip(values, values[1:], strict=False)]

    a, b = steps(original), steps(copy)

    def row(values: tuple, gaps: list[int], y: int) -> str:
        cells = "".join(
            cell(k * 44, y, v, ramp[v - 29], "#143031" if v >= 33 else "#fff")
            for k, v in enumerate(values)
        )
        marks = "".join(
            f'<text class="m" x="{42 + k * 44}" y="{y + 50}" text-anchor="middle">{g}</text>'
            for k, g in enumerate(gaps)
        )
        return cells + marks

    return f"""<svg class="explain" viewBox="0 0 800 190" role="img" aria-label="How re_ice_texture compares the steps between neighbouring pixels">
<g transform="translate(112 0)">{row(original, a, 12)}{row(copy, b, 88)}</g>
<text class="h" x="0" y="32">Original rₑ</text><text x="0" y="62">steps</text>
<text class="h" x="0" y="108">Compressed rₑ</text><text x="0" y="138">steps</text>
<text x="0" y="180">Colour shows the value. Neighbours are taken along rows and columns, on the same ice pixels as metric 5.</text>
<g transform="translate(484 0)">
<text class="h" x="0" y="16">6. re_ice_texture</text>
<text class="m" x="0" y="44">= mean(compressed steps)</text>
<text class="m" x="0" y="60">  / mean(original steps)</text>
<text class="m" x="0" y="80">= {sum(b) / len(b):.2f} / {sum(a) / len(a):.2f} = {sum(b) / sum(a):.2f}</text>
<text x="0" y="106">1 means no change, above 1 rougher,</text>
<text x="0" y="124">below 1 smoother.</text>
</g>
</svg>"""


HEIGHT_LEGEND = """<svg class="explain" style="max-width:420px" viewBox="0 0 420 58" role="img" aria-label="Colour scale of the change in cloud top height, from 3 km lower in blue to 3 km higher in red">
<defs><linearGradient id="height-change">
<stop offset="0" stop-color="#053061"/><stop offset="0.1" stop-color="#2166ac"/><stop offset="0.2" stop-color="#4393c3"/><stop offset="0.3" stop-color="#92c5de"/><stop offset="0.4" stop-color="#d1e5f0"/><stop offset="0.5" stop-color="#f7f7f7"/><stop offset="0.6" stop-color="#fddbc7"/><stop offset="0.7" stop-color="#f4a582"/><stop offset="0.8" stop-color="#d6604d"/><stop offset="0.9" stop-color="#b2182b"/><stop offset="1" stop-color="#67001f"/>
</linearGradient></defs>
<rect x="0" y="0" width="420" height="14" rx="2" fill="url(#height-change)"/>
<text x="0" y="32">3 km lower</text><text x="210" y="32" text-anchor="middle">unchanged</text><text x="420" y="32" text-anchor="end">3 km higher</text>
<text x="0" y="52">Grey: no height in both. Changes beyond 3 km are drawn at the end of the scale.</text>
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
        "figure": "",
        "explained": {
            ("cloud_iou",): change_figure(
                "cloud_iou",
                "cloud mask",
                ("cloud where Clouds Decoded", "finds it"),
                ("compress,", "decode,", "mask again"),
                "cloud on both",
                "From compressed data",
                "From original data",
            ),
            ("cth_mae", "cth_bias"): height_figure(),
            ("tau_median_rel_error",): tau_figure(),
            ("re_ice_mae",): radius_figure(),
            ("re_ice_texture",): texture_figure(),
        },
        "samples": 100,
        "group": None,
        "groups": {},
        "unit": "",
        "short": "",
        "card": "{date} · {satellite} · cloud {cloud_fraction}",
        "original": "The scene in true colour.",
        "maps": "Change in cloud mask",
        "keys": ("cloud on both", "lost", "new"),
        "levels": True,
        "thumbnail": "rgb",
        "heading": "cloud mask and property retrievals",
        "codecs": {
            "jpegxl": ("JPEG XL", "#d0892a"),
            "georvq": ("georvq", "#c0456a"),
            "sz3": ("SZ3", "#2e8c8c"),
        },
        "metrics": {
            "cloud_iou": ("1. Cloud mask IoU", 1.0),
            "cth_mae": ("2. Cloud top height MAE (m)", 0.0),
            "cth_bias": ("3. Cloud top height bias (m)", 0.0),
            "tau_median_rel_error": (
                "4. Optical thickness median relative error (%)",
                0.0,
            ),
            "re_ice_mae": ("5. Ice effective radius MAE (µm)", 0.0),
            "re_ice_texture": ("6. Ice effective radius texture ratio", 1.0),
        },
        "more_maps": (
            "-cth",
            "cth_mae",
            "Change in cloud top height",
            HEIGHT_LEGEND,
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


def free_axis(points: list[dict], best: float) -> tuple[tuple[float, float], list]:
    """A round range and its rules, for a metric with no fixed scale."""
    values = [p["value"] for p in points] + [best]
    wanted = (max(values) - min(values)) / 4 or 1
    power = 10 ** math.floor(math.log10(wanted))
    step = min(k * power for k in (1, 2, 5, 10) if k * power >= wanted)
    low = math.floor(min(values) / step) * step
    high = math.ceil(max(values) / step) * step
    if low == high:
        low, high = (low - step, high) if best else (low, high + step)
    return (low, high), [low + k * step for k in range(round((high - low) / step) + 1)]


def scatter(
    title: str,
    series: list[tuple],
    xs,
    ys,
    metric: str,
    short: str,
    rules: list | None = None,
    bound: str = "RMSE ≤ ",
) -> str:
    """Each codec at each error bound, its compression ratio against the metric,
    with the bound next to each point."""
    w, h, left, right, top, bottom = 460, 300, 50, 16, 34, 46
    measured = "measured" if rules is None else "RMSE"
    (x0, x1), (low, high) = xs, ys

    def x(v: float) -> float:
        span = math.log10(x1) - math.log10(x0)
        return left + (math.log10(v) - math.log10(x0)) / span * (w - left - right)

    def y(v: float) -> float:
        v = min(max(v, low), high)
        return top + (high - v) / (high - low) * (h - top - bottom)

    out = [f'<text class="title" x="{left}" y="18">{html.escape(title)}</text>']
    for v in rules or ticks(low, high):
        text = f"{v:g}" if rules else f"{v:.2f}"
        out.append(
            f'<line class="rule" x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
            f'<text class="tick" x="{left - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{text}</text>'
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
            f"<title>{html.escape(name)} · {bound}{p['bound']:g}{' ' + short if short else ''}, {measured} "
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
    codecs = case.get("codecs", CODECS)
    levels = case.get("levels", False)
    heading = case.get("heading", metric)
    points = (
        "Each point is one level of a codec, with the number of the level next to it"
        if levels
        else "Each point is a bound on the root-mean-square error, written next to "
        f"it in {case['unit']}"
    )
    where = "at each level" if levels else f"at each error bound, in {case['unit']}"
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    measured = {r["id"] for r in rows}
    samples = [s for s in manifest(ROOT / "usecases" / folder) if s["id"] in measured]

    def label(row: dict[str, str]) -> str:
        return case["groups"].get(row[group], row[group]) if group else "All samples"

    def panels(subset: list[dict[str, str]], name: str | None) -> str:
        """A panel for each group, or for each metric where a case has several."""
        if "metrics" not in case:
            return group_panels(subset, name, metric)
        return "".join(
            group_panels([r for r in subset if r[column]], title, column, best)
            for column, (title, best) in case["metrics"].items()
            if any(r[column] for r in subset)
        )

    def group_panels(
        subset: list[dict[str, str]],
        name: str | None,
        column: str,
        best: float | None = None,
    ) -> str:
        """One panel per group in ``subset`` with every codec, on shared axes."""
        groups = list(dict.fromkeys(label(r) for r in subset))
        curves = {
            g: [
                (codec_name, colour, curve(found, column))
                for codec, (codec_name, colour) in codecs.items()
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
        xs, ys, rules = ratio_range(every), metric_range(every, top), None
        if best is not None:
            ys, rules = free_axis(every, best)
        return "".join(
            scatter(
                name or g,
                found,
                xs,
                ys,
                column,
                short,
                rules,
                "level " if levels else "RMSE ≤ ",
            )
            for g, found in curves.items()
        )

    legend = "".join(
        f'<span style="--c:{colour}"><i></i>{html.escape(name)}</span>'
        for name, colour in codecs.values()
    )
    keys = "".join(
        f'<span class="key k-{kind}">{html.escape(text)}</span>'
        for kind, text in zip(("kept", "lost", "new"), case["keys"], strict=True)
    )
    root = "../../../../"

    def gallery(sid: str, found: list[dict], suffix: str, column: str) -> str:
        """The maps of one sample for every codec, with ``column`` under each."""
        maps = []
        for codec, (name, _) in codecs.items():
            mine = sorted(
                (r for r in found if r["codec"] == codec),
                key=lambda r: float(r["rms_bound"]),
            )
            figs = []
            for r in mine:
                config = r["configuration"]
                image = resized(
                    usecase_png(folder, sid, f"{config}{suffix}"),
                    f"img/usecases/{folder}/{sid}/{config}{suffix}.webp",
                    LARGE,
                    False,
                )
                if image is None:
                    continue
                bound = f"{float(r['rms_bound']):g} {short}"
                rmse = float(r["rmse"])
                done = "lossless" if rmse == 0 else f"measured {rmse:.3g}"
                point = config if levels else f"RMSE ≤ {bound}"
                done = f"RMSE {rmse:.3g}" if levels else done
                figs.append(
                    f'<figure><img src="{root}{image}" alt="{html.escape(name)} at {point}">'
                    f"<figcaption><strong>{point}</strong>, {done}<br>"
                    f"{float(r['compression_ratio']):.1f}× · {column} "
                    f"{float(r[column]):+.3f}</figcaption></figure>"
                )
            if figs:
                maps.append(
                    f'<h3>{html.escape(name)}</h3><div class="maps">{"".join(figs)}</div>'
                )
        return "".join(maps)

    def map_section(name: str, intro: str, body: str) -> str:
        """The maps of one sample, closed until asked for where a case has several."""
        if levels:
            return (
                f'<details class="decoded map-section"><summary><h2>{html.escape(name)}</h2>'
                f"</summary>{intro}{body}</details>"
            )
        return f'<section class="decoded"><h2>{name}</h2>\n{intro}\n{body}</section>'

    cards = []
    for k, s in enumerate(samples):
        sid = s["id"]
        source = usecase_png(folder, sid, case.get("thumbnail", "original"))
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

        more = ""
        if "more_maps" in case:
            suffix, column, more_title, legend_svg = case["more_maps"]
            more = map_section(
                more_title, legend_svg, gallery(sid, found, suffix, column)
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
<section class="results"><h2>Compression ratio and {heading}</h2>
<p class="note">{points}, on this sample.</p>
<div class="legend uc-legend">{legend}</div><div class="uc-panels wide">{panels(found, sid)}</div></section>
{map_section(case["maps"], f'<p class="note">The result {"from compressed data" if levels else "on the compressed copy"} {where}.{keys}</p>', gallery(sid, found, "", metric))}{more}
<p class="pager">{prev_link}{next_link}</p>"""
        target = OUT / "usecases" / folder / "results" / sid / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(layout(root, f"{sid} · Earth Compress benchmark", body))

    note = f"{points}, at the compression ratio over all the samples of the panel " + (
        "and the median of the metric. These codecs are not set to a root-mean-square "
        "error limit, so a point has no bound to compare with the other use cases."
        if levels
        else f"and the median <code>{metric}</code>. Where JPEG XL finds no distance "
        "within the bound it stores the array losslessly, so those bounds share one "
        "point, marked lossless."
    )
    return f"""{header}
<section class="results"><h2>Compression ratio and {heading}</h2><p class="note">{note}</p>
<div class="legend uc-legend">{legend}</div><div class="uc-panels wide">{panels(rows, None)}</div></section>
<section><h2>Samples</h2><div class="grid">{"".join(cards)}</div></section>"""


def explained_rows(text: str, figures: dict[tuple, str]) -> str:
    """The metric table of ``text``, each group of rows opening on its figure.

    ``text`` starts with a blank line and then the table.
    """
    rows = {plain(row["metric"]): row for row in table(text, "\n")}

    def line(row: dict[str, str]) -> str:
        return (
            f'<span class="metric-line"><span>{html.escape(row[""])}</span>'
            f"<span>{inline(row['metric'])}</span><span>{inline(row['meaning'])}</span>"
            f"<span>{inline(row['no change'])}</span></span>"
        )

    groups = "".join(
        f'<details class="metric-row"><summary>{"".join(line(rows[m]) for m in metrics)}'
        f"</summary>{figure}</details>"
        for metrics, figure in figures.items()
    )
    return (
        '<div class="metric-table"><div class="metric-line metric-head"><span></span>'
        f"<span>metric</span><span>meaning</span><span>no change</span></div>{groups}</div>"
    )


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
<p><a class="button primary" href="results/">Results</a></p></div>
</div>"""
        target = OUT / "usecases" / folder / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(layout("../../", f"{title} · Earth Compress benchmark", body))
        metric_text = blocks["Metric"]
        if "explained" in case:
            case = {**case, "figure": explained_rows(metric_text, case["explained"])}
            metric_text = "\n".join(
                line for line in metric_text.splitlines() if not line.startswith("|")
            )
        about = md(metric_text, "../../../") + (
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
                f"{count} samples · "
                + (
                    f"{len(case['metrics'])} metrics"
                    if "metrics" in case
                    else f"<code>{metric}</code>"
                ),
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
    for name in ("style.css", "chart.js", "lossy.js"):
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
