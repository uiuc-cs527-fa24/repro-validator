import pydantic_core
import typing
import yarl
import aiohttp
import xml.etree.ElementTree
import schema
import util


async def mine_articles(
    session: aiohttp.ClientSession,
    toc_page: yarl.URL,
    other_data: typing.Mapping[str, str],
) -> schema.ArticleGroup:
    if (
        toc_page.scheme != "https"
        or toc_page.host != "dblp.org"
        or not toc_page.path.startswith("/db/")
        and "." not in toc_page.path
    ):
        raise ValueError(
            f"{toc_page!s} does not smell like a toc page (https://dblp.org/db/conf/semweb/iswc2007)"
        )

    toc_page = toc_page.with_suffix(".xml")

    articles = []
    async with session.get(toc_page) as resp:
        if resp.status != 200:
            raise ValueError(
                f"{toc_page!s} returned {resp.status}: {await resp.text()}"
            )
        etree = xml.etree.ElementTree.parse(await resp.text())
        for elem in etree.findall("/bht/dblpcites/r/article"):
            articles.append(
                schema.Article(
                    dblp_url=pydantic_core.Url(elem.attrib["key"]),
                )
            )
    return schema.ArticleGroup(
        dblp_search=util.yarl_to_pydantic(toc_page),
        articles=articles,
        other_data=other_data,
    )
