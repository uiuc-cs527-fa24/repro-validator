#!/usr/bin/env python
import pydantic
from typing_extensions import Annotated
import rich.console
import pathlib
import json
import yaml
import yarl
import aiohttp
import typer
import asyncio
from . import schema
from . import validator
from . import dockerfile
from . import mine_articles as mine_articles_mod


app = typer.Typer()
console = rich.console.Console()


@app.command()
def validate(
    path: Annotated[pathlib.Path, typer.Argument(help="Path to $bibcode.yaml")],
    use_archive_org: bool = False,
) -> None:
    async def async_validatation_successful() -> bool:
        async with aiohttp.ClientSession() as session:
            has_errors = False
            async for level, message in validator.validate_article_yaml(
                path, session, use_archive_org
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

    if not asyncio.run(async_validatation_successful()):
        raise typer.Exit(code=1)


@app.command()
def export_dockerfile(
    article_yaml: pathlib.Path,
) -> None:
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
        [
            *article.computational_status.source_search.build_attempt.build_directives,
            *article.computational_status.source_search.build_attempt.test_directives,
        ],
    )
    console.print(f"[green]{result!s}")
    console.print(f"[green]Run:\n    docker build {result.parent!s}\n")


def mine_articles(
    toc_page: str,
    destination: pathlib.Path,
    other_data: str = "{}",
) -> None:
    async def mine_articles_async() -> None:
        async with aiohttp.ClientSession() as aiohttp_client:
            article_group = await mine_articles_mod.mine_articles(
                aiohttp_client,
                yarl.URL(toc_page),
                json.loads(other_data),
            )
            destination.write_text(yaml.dump(article_group.dict()))

    asyncio.run(mine_articles_async())


if __name__ == "__main__":
    app()
