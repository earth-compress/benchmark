"""Command line entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .codecs import configurations_for
from .codecs.base import CodecConfiguration
from .contract import Mode
from .runner import run_benchmark

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Benchmark compression codecs on an EarthCompress corpus.",
)

DEFAULT_CORPORA_ROOT = Path("corpora")


def _select(
    corpus: Path,
    codec_ids: list[str] | None,
    modes: list[Mode] | None,
) -> tuple[CodecConfiguration, ...]:
    """Resolve the configurations measurable on this corpus."""
    available = configurations_for(corpus.name)

    if codec_ids:
        by_id = {config.id: config for config in available}
        requested = tuple(dict.fromkeys(codec_ids))
        unknown = sorted(set(requested) - by_id.keys())
        if unknown:
            raise typer.BadParameter(
                f"not available on {corpus.name}: {', '.join(unknown)}",
                param_hint="--codec",
            )
        available = tuple(by_id[name] for name in requested)

    if modes:
        wanted = set(modes)
        available = tuple(config for config in available if config.mode in wanted)
        if not available:
            raise typer.BadParameter(
                "no configuration matches the selected modes", param_hint="--mode"
            )
    return available


def _discover(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        raise ValueError(f"no corpora found in {root}")
    corpora = tuple(
        path.resolve()
        for path in sorted(root.iterdir())
        if path.is_dir()
        and (path / "manifest.csv").is_file()
        and (path / "npz").is_dir()
    )
    if not corpora:
        raise ValueError(f"no corpora found in {root}")
    return corpora


@app.command()
def benchmark(
    corpus: Annotated[
        Path | None,
        typer.Argument(
            help="Corpus directory, usually corpora/<corpus-id>.",
            exists=True,
            file_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ] = None,
    all_corpora: Annotated[
        bool, typer.Option("--all", help="Run every corpus under ./corpora.")
    ] = False,
    codec: Annotated[
        list[str] | None,
        typer.Option(
            "--codec", metavar="ID", help="Run one configuration; repeatable."
        ),
    ] = None,
    mode: Annotated[
        list[Mode] | None,
        typer.Option("--mode", help="Keep only this fidelity mode; repeatable."),
    ] = None,
    rounds: Annotated[int, typer.Option(min=1, help="Number of timed rounds.")] = 5,
    min_seconds: Annotated[
        float, typer.Option(min=0.0, help="Minimum duration of each timed round.")
    ] = 1.0,
    limit: Annotated[
        int | None, typer.Option(min=1, help="Run only the first N samples.")
    ] = None,
    list_codecs: Annotated[
        bool, typer.Option("--list-codecs", help="List configurations and exit.")
    ] = False,
    version: Annotated[
        bool, typer.Option("--version", help="Show the installed version and exit.")
    ] = False,
) -> None:
    """Run every selected configuration on every sample in CORPUS."""
    if version:
        typer.echo(f"earthcompress {__version__}")
        return

    if corpus is not None and all_corpora:
        raise typer.BadParameter(
            "CORPUS and --all cannot be used together", param_hint="CORPUS"
        )
    if corpus is None and not all_corpora:
        raise typer.BadParameter("a corpus directory is required", param_hint="CORPUS")

    if all_corpora:
        try:
            corpora = _discover(Path.cwd() / DEFAULT_CORPORA_ROOT)
        except (OSError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
    else:
        assert corpus is not None
        corpora = (corpus,)

    if list_codecs:
        for current in corpora:
            typer.echo(f"{current.name}")
            for config in _select(current, codec, mode):
                budget = config.budget
                detail = "" if budget is None else f"  {budget.kind} tau={budget.tau:g}"
                typer.echo(f"  {config.id}\t{config.mode}{detail}")
        return

    all_ok = True
    for index, current in enumerate(corpora, start=1):
        if len(corpora) > 1:
            typer.echo(f"\n=== {current.name} ({index}/{len(corpora)}) ===")
        try:
            ok = run_benchmark(
                current,
                _select(current, codec, mode),
                rounds=rounds,
                min_seconds=min_seconds,
                limit=limit,
            )
        except (OSError, ValueError) as error:
            if len(corpora) == 1:
                typer.echo(f"Error: {error}", err=True)
                raise typer.Exit(1) from error
            typer.echo(f"{current.name}: FAILED: {error}", err=True)
            all_ok = False
        else:
            all_ok = ok and all_ok

    if not all_ok:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
