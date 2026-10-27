from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import shutil
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
    ("Protocol", "protocol/"),
    ("Codecs", "codecs/"),
    ("Tolerance", "tolerance/"),
)
DOCS = {"protocol": "PROTOCOL.md", "codecs": "CODECS.md", "tolerance": "TOLERANCE.md"}
PAGES = {**{name: slug for slug, name in DOCS.items()}, "DATASETS.md": "datasets"}
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
    official = table((ROOT / "CODECS.md").read_text(), "## Official run")
    codecs = [plain(r["id"]) for r in official]
    reference = table((ROOT / "CODECS.md").read_text(), "## Reference")
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
