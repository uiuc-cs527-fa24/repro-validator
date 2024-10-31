import pydantic_core
import typing
import yarl
import aiohttp
import xml.etree.ElementTree
from . import util
from . import schema


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

# To do that, you need to write a script that turns DBLP results into list of bibcodes, preferably formatted according to my YAML schema (each bibcode should turn into YAML file with the bibcode as its name with 1 field; data-collection students will fill in the rest). I started writing one [here](https://github.com/uiuc-cs527-fa24/repro-validator/blob/main/repro_validator/mine_articles.py) but it is untested. We would also want a second script to:

# 1. Deterministically shuffle the article list. The proceedings of a conference like ASPLOS are ordered by session; if we sample in order, we only sample the first N / M sessions rather than some from every sessions. Different sessions may have different orientations to reproducibility. The shuffle should be deterministic (seeded RNG) so we can re-run and get the same order though.

# 2. Count how many articles have been "already done". Since I didn't begin with a recorded deterministic shuffle (I really should have), the "already done" articles are not necessarily the first k of the shuffled articles. They will be randomly scattered, so we should count them.

# 3. Select the not-already-done articles in order, until the already-done + selected-not-already-done reaches k% (parameter).

# 4. Do that ^ for every conference for every year of interest.

# Shuffle the results?

# The 2013 group is completely done. The 2018 group has a massive head start from MP2 and Progress 1 -- 4. However, if we mix in 2024 conferences and SE conferences from 2018 and 2024 now, we should be able to cover a good sample of them.
