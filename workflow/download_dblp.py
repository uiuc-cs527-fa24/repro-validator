import typing
import asyncio
import rich
import itertools
import json
import yaml
import pathlib
import pydantic_core
import aiohttp
import lxml.etree
import repro_validator.util
import repro_validator.schema


async def main(
        ins_outs: list[tuple[pathlib.Path, pathlib.Path]],
        seed: int,
) -> None:
    async with aiohttp.ClientSession() as session:
        for result in rich.progress.track(asyncio.as_completed([
            main_one(session, input, output)
            for input, output in ins_outs
        ]), total=len(ins_outs)):
            article_group = await result
            print(article_group.venue, article_group.date.year)


async def main_one(
        session: aiohttp.ClientSession,
        input: pathlib.Path,
        output: pathlib.Path,
        seed: int = 0,
) -> repro_validator.schema.ArticleGroup:
    article_group = repro_validator.schema.ArticleGroup(**yaml.safe_load(input.read_text()))

    toc_page = repro_validator.util.pydantic_to_yarl(article_group.dblp_search).with_suffix(".xml")

    async with session.get(toc_page) as resp:
        if resp.status != 200:
            raise ValueError(
                f"{toc_page!s} returned {resp.status}: {await resp.text()}"
            )
        doc = lxml.etree.fromstring(await resp.text())

    # Handle include/exclude sessions
    assert article_group.extras.keys() <= {"exclude_sessions", "include_sessions", "exclude_articles"}
    exclude_sessions = article_group.extras.get("exclude_sessions")
    include_sessions = article_group.extras.get("include_sessions")
    all_dblpcites = []
    for header, dblpcites in split_iterator(
            doc.getchildren(),
            lambda elem: elem.tag in {"h1", "h2"}
    ):
        if exclude_sessions:
            if header is None or not any(
                session in (header.text or "")
                for session in exclude_sessions
            ):
                all_dblpcites.extend(dblpcites)
            else:
                print(article_group.venue, article_group.date.year, "excluding", header.text if header is not None else "")
        elif include_sessions:
            if header is not None and any(
                session in (header.text or "")
                for session in include_sessions
            ):
                all_dblpcites.extend(dblpcites)
            else:
                print(article_group.venue, article_group.date.year, "including", header.text if header is not None else "")
        else:
            # Default is to include everything
            all_dblpcites.extend(dblpcites)

    article_xmls = [
        elem
        for dblpcites in all_dblpcites
        for r in dblpcites.getchildren()
        for elem in r.getchildren()
        if elem.tag in {"inproceedings", "article"}
    ]

    articles = []
    exclude_articles = article_group.extras.get("exclude_articles", frozenset())
    for article_xml in article_xmls:
        dblp_url = pydantic_core.Url(
            "https://dblp.org/rec/" + article_xml.get("key")
        )
        if str(dblp_url) in exclude_articles:
            print(article_group.venue, article_group.date.year, "excluding article", str(dblp_url))
            continue
        electronic_edition_urls = [
            pydantic_core.Url(subelem.text)
            for subelem in article_xml.getchildren()
            if subelem.tag == "ee"
        ]
        doi_urls = [
            url
            for url in electronic_edition_urls
            if url.host == "doi.org"
        ]
        doi_url = doi_urls[0] if doi_urls else None
        other_article_urls = [
            url
            for url in electronic_edition_urls
            if url.host != "doi.org"
        ]
        authors = [
            repro_validator.schema.Author(
                name=subelem.text,
                dblp_pid_url=pydantic_core.Url("https://dblp.org/pid/" + subelem.get("pid")),
                orcid_url=pydantic_core.Url("https://orcid.org/" + subelem.get("orcid")) if subelem.get("orcid") else None,
            )
            for subelem in article_xml.getchildren()
            if subelem.tag == "author"
        ]
        articles.append(
            repro_validator.schema.Article(
                dblp_url=dblp_url,
                doi_url=doi_url,
                other_article_urls=other_article_urls,
                authors=authors,
            )
        )

    article_group.articles = repro_validator.util.deterministic_shuffle(
        seed,
        sorted(
            articles,
            key=lambda article: article.dblp_url,
        ),
    )
    output.write_text(yaml.dump(json.loads(article_group.model_dump_json())))

    return article_group


_T = typing.TypeVar("_T")


def split_iterator(
        it: typing.Iterator[_T],
        predicate: typing.Callable[[_T], bool],
) -> typing.Iterator[tuple[_T | None, list[_T]]]:
    header = None
    section: list[_T] = []
    for elem in it:
        if predicate(elem):
            yield (header, section)
            header = elem
            section = []
        else:
            section.append(elem)
    yield header, section


asyncio.run(main(
    [
        (pathlib.Path(input), pathlib.Path(output))
        for input, output in zip(snakemake.input, snakemake.output)
    ],
    seed=0,
))
