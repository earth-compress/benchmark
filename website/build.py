"""Build the benchmark website from the files of this repository.

Every sentence and number on the page comes from README.md, DATASETS.md,
CODECS.md, PROTOCOL.md, TOLERANCE.md, and the corpus folders, so the page
cannot say something the documents do not.

    uv run --extra site python website/build.py
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import shutil
from pathlib import Path

import markdown

from earthcompress.runner import aggregate

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "dist"
REPO = "https://github.com/earth-compress/benchmark"
THUMB = 192


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


def results(corpus: Path) -> dict[str, dict]:
    """Totals of each lossless configuration that completed every sample."""
    path = corpus / "results.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as stream:
        rows = [
            {**row, "fidelity_ok": row["fidelity_ok"] == "True"}
            for row in csv.DictReader(stream)
            if row["mode"] == "lossless"
        ]
    count = len({row["sample_id"] for row in rows})
    totals = {}
    for config, total in aggregate(rows, count).items():
        if not total.get("complete"):
            continue
        selected = [r for r in rows if r["configuration"] == config]
        totals[config] = {
            "input": sum(int(r["input_bytes"]) for r in selected),
            "compressed": sum(int(r["compressed_bytes"]) for r in selected),
            "decode_ns": sum(int(r["decode_ns"]) for r in selected),
        }
    return totals


# Invented values for designing the page before the official run. Never published.
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


def example(corpora: list[str]) -> dict[str, dict]:
    """Per-corpus totals invented from ``EXAMPLE``, varied by corpus."""
    import random

    data = {}
    for corpus in corpora:
        rng = random.Random(corpus)
        gain, speed = rng.uniform(0.7, 1.6), rng.uniform(0.6, 1.4)
        size = 100_000_000
        data[corpus] = {
            codec: {
                "input": size,
                "compressed": round(
                    size / max(1.02, 1 + (ratio - 1) * gain * rng.uniform(0.9, 1.1))
                ),
                "decode_ns": round(
                    size / (mb_s * speed * rng.uniform(0.85, 1.15)) * 1000
                ),
            }
            for codec, (ratio, mb_s) in EXAMPLE.items()
        }
    return data


def summary(data: dict[str, dict]) -> dict[str, dict]:
    """Totals over every corpus that has results, for configurations present in all of them."""
    measured = [corpus for corpus in data.values() if corpus]
    if not measured:
        return {}
    common = set.intersection(*(set(corpus) for corpus in measured))
    return {
        config: {
            key: sum(corpus[config][key] for corpus in measured)
            for key in ("input", "compressed", "decode_ns")
        }
        for config in sorted(common)
    }


def thumbnail(corpus: Path) -> str | None:
    pngs = sorted((corpus / "png").glob("*.png"))
    if not pngs:
        return None
    from PIL import Image

    target = OUT / "img" / f"{corpus.name}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(pngs[0]) as image:
        image = image.convert("RGB")
        side = min(image.size)
        left, top = (image.width - side) // 2, (image.height - side) // 2
        image.crop((left, top, left + side, top + side)).resize(
            (THUMB, THUMB), Image.LANCZOS
        ).save(target, optimize=True)
    return f"img/{corpus.name}.png"


def samples(corpus: Path) -> list[dict[str, str]]:
    path = corpus / "manifest.csv"
    if not path.exists():
        return []
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def page(use_example: bool = False) -> str:
    readme = (ROOT / "README.md").read_text()
    datasets = table((ROOT / "DATASETS.md").read_text(), "## Corpora")
    codecs = table((ROOT / "CODECS.md").read_text(), "## Official run")
    tagline = " ".join(readme.split("# benchmark", 1)[1].split("\n\n")[1].split())
    codec_ids = [plain(row["id"]) for row in codecs]

    data: dict[str, dict] = {}
    cards = []
    for row in datasets:
        cid = plain(row["corpus"])
        folder = ROOT / "corpora" / cid
        data[cid] = results(folder)
        image = thumbnail(folder) if folder.exists() else None
        spec = folder / "spec.md"
        spec_html = (
            markdown.markdown(spec.read_text().split("\n", 1)[1], extensions=["tables"])
            if spec.exists()
            else ""
        )
        listed = samples(folder)
        sample_rows = "".join(
            f"<tr><td><code>{html.escape(s['id'])}</code></td><td>{html.escape(s.get('site', ''))}</td>"
            f"<td><code>{html.escape(s['datetime_start'][:19])}</code></td><td><code>{html.escape(s['crs'][:20])}</code></td></tr>"
            for s in listed
        )
        picture = (
            f'<img src="{image}" alt="" loading="lazy" width="{THUMB}" height="{THUMB}">'
            if image
            else '<div class="noimg"></div>'
        )
        cards.append(
            f"""<details class="corpus" id="{cid}">
<summary>{picture}<span class="cid">{cid}</span><span class="meta">{inline(row["shape"])} · {inline(row["dtype"])}</span></summary>
<div class="detail">
<p>{inline(row["contents"])}. {inline(row["samples"])} samples, {inline(row["MB"])} MB. Source: {inline(row["source"])}.</p>
{spec_html}
{f'<div class="scroll"><table class="samples"><tr><th>sample</th><th>site</th><th>time</th><th>crs</th></tr>{sample_rows}</table></div>' if sample_rows else ""}
<p><a href="{REPO}/tree/main/corpora/{cid}">Folder on GitHub</a></p>
</div>
</details>"""
        )

    if use_example:
        data = example(list(data))
    measured = [cid for cid, found in data.items() if found]
    options = "".join(f'<option value="{cid}">{cid}</option>' for cid in measured)
    return TEMPLATE.format(
        tagline=html.escape(tagline),
        corpora=len(datasets),
        configurations=len(codec_ids),
        measured=len(measured),
        badge='<span class="example">Example data</span>' if use_example else "",
        options=options,
        cards="\n".join(cards),
        repo=REPO,
        data=json.dumps({"all": summary(data), **{cid: data[cid] for cid in measured}}),
        codecs=json.dumps(codec_ids),
    )


TEMPLATE = (Path(__file__).resolve().parent / "template.html").read_text()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--example", action="store_true", help="invented results, for design only"
    )
    args = parser.parse_args()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copy(ROOT / "docs" / "assets" / "earth-compress.svg", OUT / "earth-compress.svg")
    css = (Path(__file__).resolve().parent / "style.css").read_bytes()
    (OUT / "style.css").write_bytes(css)
    version = hashlib.sha256(css).hexdigest()[:10]
    (OUT / "index.html").write_text(
        page(args.example).replace('href="style.css"', f'href="style.css?v={version}"')
    )
    print(f"wrote {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
