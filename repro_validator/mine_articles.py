import json
import yaml
import pathlib
import pydantic_core
import aiohttp
import xml.etree.ElementTree
from . import util
from . import schema


async def mine_articles(
    session: aiohttp.ClientSession,
    article_group_path: pathlib.Path,
    seed: int,
) -> schema.ArticleGroup:
    article_group = schema.ArticleGroup(**yaml.safe_load(article_group_path.read_text()))

    if not article_group.articles:
        toc_page = util.pydantic_to_yarl(article_group.dblp_search)
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
            etree = xml.etree.ElementTree.fromstring(await resp.text())
            print(etree.tag)
            for elem in etree.findall("./dblpcites/r/article") + etree.findall("./dblpcites/r/inproceedings"):
                articles.append(
                    schema.Article(
                        dblp_url=pydantic_core.Url(
                            "https://dblp.org/rec/" + elem.attrib["key"],
                        ),
                    )
                )
        article_group.articles = articles

    article_group.articles = util.deterministic_shuffle(
        seed,
        sorted(
            article_group.articles,
            key=lambda article: article.dblp_url,
        ),
    )
    article_group_path.write_text(yaml.dump(json.loads(article_group.model_dump_json())))
    return article_group


def separate_in_completed_articles(
        article_group: schema.ArticleGroup,
        completed_bibcodes: frozenset[str],
) -> tuple[list[schema.Article], list[schema.Article]]:
    def article_to_id(article: schema.Article) -> str:
        return util.pydantic_to_yarl(article.dblp_url).with_suffix("").parts[-1]
    completed = [
        article
        for article in article_group.articles
        if article_to_id(article) in completed_bibcodes
    ]
    incomplete = [
        article
        for article in article_group.articles
        if article_to_id(article) not in completed_bibcodes
    ]
    return completed, incomplete


def prioritize_articles(
    article_groups: list[tuple[schema.ArticleGroup, list[schema.Article], list[schema.Article]]],
) -> list[tuple[float, list[tuple[schema.ArticleGroup, list[schema.Article]]]]]:
    """Sorts incompleted articles from each article group such that we get 1% of all groups, then 2% of all groups, etc.
    """
    prioritized_sequence = []
    for i in range(0, 100, 1):
        priorities_for_i = []
        for article_group, completed, incomplete in article_groups:
            total = len(article_group.articles)
            assert total == len(completed) + len(incomplete)
            old_todo = max((i - 1) * total // 100 - len(completed), 0)
            todo = i * total // 100 - len(completed)
            if todo > 0:
                priorities_for_i.append((article_group, incomplete[old_todo:todo]))
        prioritized_sequence.append((i / 100, priorities_for_i))
    return prioritized_sequence
