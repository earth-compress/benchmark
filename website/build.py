"""Build the benchmark website from the files of this repository.

Every sentence and number on the page comes from README.md, DATASETS.md,
CODECS.md, PROTOCOL.md, TOLERANCE.md, and the corpus folders, so the page
cannot say something the documents do not.

    uv run --extra site python website/build.py
"""

from __future__ import annotations

import csv
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
    path = corpus / "results.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as stream:
        rows = [
            {**row, "fidelity_ok": row["fidelity_ok"] == "True"}
            for row in csv.DictReader(stream)
        ]
    count = len({row["sample_id"] for row in rows})
    return {k: v for k, v in aggregate(rows, count).items() if v.get("complete")}


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


def page() -> str:
    readme = (ROOT / "README.md").read_text()
    datasets = table((ROOT / "DATASETS.md").read_text(), "## Corpora")
    codecs = table((ROOT / "CODECS.md").read_text(), "## Official run")
    reference = table((ROOT / "CODECS.md").read_text(), "## Reference")
    protocol_html = markdown.markdown(
        (ROOT / "PROTOCOL.md").read_text(), extensions=["tables", "fenced_code"]
    )
    tagline = " ".join(readme.split("# benchmark", 1)[1].split("\n\n")[1].split())
    modes = {
        plain(r["mode"]): r["what it guarantees"][:1].upper()
        + r["what it guarantees"][1:]
        + "."
        for r in table(readme, "# benchmark")
    }
    codec_ids = [plain(row["id"]) for row in codecs]

    data: dict[str, dict] = {}
    cards = []
    for row in datasets:
        cid = plain(row["corpus"])
        folder = ROOT / "corpora" / cid
        found = results(folder)
        data[cid] = {
            c: {
                "ratio": found[c]["compression_ratio"],
                "decode": found[c]["decode_MB_s"],
            }
            for c in codec_ids
            if c in found
        }
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

    head_cells = "".join(f"<th>{html.escape(c)}</th>" for c in codec_ids)
    body_rows = "".join(
        f'<tr><th><a href="#{plain(r["corpus"])}">{plain(r["corpus"])}</a></th>'
        + "".join(f'<td data-c="{c}"></td>' for c in codec_ids)
        + "</tr>"
        for r in datasets
    )
    codec_rows = "".join(
        f"<tr><td><code>{plain(r['id'])}</code></td><td>{inline(r['definition'])}</td><td>{inline(r['software'])}</td></tr>"
        for r in codecs + reference
    )
    measured = any(data[c] for c in data)

    return TEMPLATE.format(
        tagline=html.escape(tagline),
        lossless=inline(modes["lossless"]),
        near=inline(modes["near-lossless"]),
        lossy=inline(modes["lossy"]),
        corpora=len(datasets),
        configurations=len(codecs),
        head_cells=head_cells,
        body_rows=body_rows,
        status=""
        if measured
        else '<p class="status">Results appear here after the official run.</p>',
        cards="\n".join(cards),
        codec_rows=codec_rows,
        protocol=protocol_html,
        repo=REPO,
        data=json.dumps(data),
    )


TEMPLATE = (Path(__file__).resolve().parent / "template.html").read_text()


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for name in ("earth-compress.svg", "earth-compress-dark.svg"):
        shutil.copy(ROOT / "docs" / "assets" / name, OUT / name)
    shutil.copy(Path(__file__).resolve().parent / "style.css", OUT / "style.css")
    (OUT / "index.html").write_text(page())
    print(f"wrote {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
