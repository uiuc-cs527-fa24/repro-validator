#!/usr/bin/env python
import pandas
import pydantic
from typing_extensions import Annotated
import typing
import asyncio
import subprocess
import os
import pathlib
import yaml
import rich.console
import rich.traceback
import aiohttp
import typer
import ssl as libssl
import certifi
from . import schema
from . import validator
from . import dockerfile
from . import mine_articles as mine_articles_mod


app = typer.Typer()
console = rich.console.Console()
ssl = libssl.create_default_context(cafile=certifi.where())


@app.command()
def validate(
    path: Annotated[pathlib.Path, typer.Argument(help="Path to $bibcode.yaml")],
    use_archive_org: bool = False,
    offline: bool = False,
) -> None:
    rich.traceback.install(show_locals=False)

    async def async_validation_successful() -> bool:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=ssl)
        ) as session:
            has_errors = False
            async for level, message in validator.validate_article_yaml(
                path, session, use_archive_org, offline
            ):
                if level == validator.Level.fatal_error:
                    console.print(f"[red]Fatal error: {rich.markup.escape(message)}")
                    has_errors = True
                elif level == validator.Level.error:
                    console.print(f"[red]Error: {rich.markup.escape(message)}")
                    has_errors = True
                elif level == validator.Level.possible_error:
                    console.print(
                        f"[yellow]Possible error: {rich.markup.escape(message)}"
                    )
            return not has_errors

    if not asyncio.run(async_validation_successful()):
        raise typer.Exit(code=1)
    else:
        console.print(f"[green]All good {path!s}")


@app.command()
def export_dockerfile(
    article_yaml: pathlib.Path,
    build: bool = False,
) -> None:
    rich.traceback.install(show_locals=False)
    try:
        article_yaml_text = article_yaml.read_text()
    except Exception as exc:
        console.print(f"[red]Could not red {article_yaml!s}")
        console.print(exc)
        raise typer.Exit(code=1)
    try:
        article_dict = yaml.safe_load(article_yaml_text)
    except yaml.YAMLError as exc:
        console.print(f"[red]{article_yaml!s} does not YAML")
        console.print(exc)
        raise typer.Exit(code=1)

    try:
        article = schema.Article(**article_dict)
    except pydantic.ValidationError as exc:
        console.print(f"[red]{article_dict!r} is not Article")
        console.print(exc)
        raise typer.Exit(code=1)

    if not isinstance(article.computational_status, schema.ComputationalArticle):
        console.print("[red]Not a computational article")
        raise typer.Exit(code=1)

    if not isinstance(article.computational_status.source_search, schema.SourceFound):
        console.print("[red]Source not found")
        raise typer.Exit(code=1)

    if article.computational_status.source_search.build_attempt is None:
        console.print("[red]No build attempt")
        raise typer.Exit(code=1)

    result = dockerfile.to_dockerfile(
        article_yaml.resolve().parent,
        article.computational_status.source_search.build_attempt.base_image,
        [
            *article.computational_status.source_search.build_attempt.build_directives,
            *article.computational_status.source_search.build_attempt.test_directives,
        ],
    )
    if os.environ.get("CHOWN"):
        uid = int(os.environ["UID"]) if "UID" in os.environ else -1
        gid = int(os.environ["GID"]) if "GID" in os.environ else -1
        os.chown(result.parent, uid, gid)
        os.chown(result, uid, gid)
    console.print(f"[green]{result!s}")
    if not build:
        console.print(f"[green]Run:\n\n  docker build {result.parent!s}\n")
    else:
        subprocess.run(
            ["docker", "build", str(result.parent)],
        )


@app.command()
def mine_articles(
    article_groups_dir: pathlib.Path,
    completed_bibcodes: pathlib.Path,
    destination: pathlib.Path,
    seed: int = 0,
) -> None:
    async def mine_articles_async() -> None:
        completed_articles = frozenset(pandas.read_csv(
            completed_bibcodes,
        )["Bibcode"])
        with rich.progress.Progress() as progress:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl)
            ) as aiohttp_client:
                article_group_paths = list(article_groups_dir.iterdir())
                article_group_reqs = progress.track(
                    asyncio.as_completed([
                        mine_articles_mod.mine_articles(
                            aiohttp_client,
                            article_group_path,
                            seed,
                        )
                        for article_group_path in article_group_paths
                    ]),
                    total=len(article_group_paths)
                )
                article_groups = []
                for article_group_req in article_group_reqs:
                    article_group = await article_group_req
                    completed, incomplete = mine_articles_mod.separate_in_completed_articles(article_group, completed_articles)
                    article_groups.append((article_group, completed, incomplete))

        prioritized_articles = mine_articles_mod.prioritize_articles(article_groups)
        pandas.DataFrame.from_records([
            {
                "URL": str(article.dblp_url),
                "Netid": "",
                "Type": "3",
                "level": level,
            }
            for level, series in prioritized_articles
            for article_group, articles in series
            for article in articles
        ]).to_csv(destination, index=False)

    asyncio.run(mine_articles_async())


if __name__ == "__main__":
    app()
