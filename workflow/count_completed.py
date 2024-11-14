import collections
import typing
import rich.progress
import yaml
import polars
import tabulate
import pathlib
from repro_validator.schema import ArticleGroup, Article


if typing.TYPE_CHECKING:
    from snakemake.script import snakemake


article_groups = [
    ArticleGroup(**yaml.safe_load(pathlib.Path(article_group).read_text()))
    for article_group in rich.progress.track(snakemake.input.article_groups, description="article_groups")
]
bibcode_to_url = dict(polars.read_csv(snakemake.input.bibcode_to_url).select("bibcode", "url").rows())
doi_to_url = dict(polars.read_csv(snakemake.input.bibcode_to_url).select("doi", "url").rows())
old_to_new = dict(polars.read_csv(snakemake.input.old_to_new_bibcodes).select("old", "new").rows())


cp_ignored: list[str] = [
    bibcode_to_url.get(old_to_new.get(bibcode, bibcode), bibcode)
    for bibcode in polars.read_csv(snakemake.input.cp_bibcodes).filter(
            polars.col("backed_by_code").not_().or_(polars.col("needs_specialized_hardware").str.contains("True")).or_(polars.col("has_source").not_())
    )["bibcode"]
]
mp2: list[str] = [
    bibcode_to_url.get(old_to_new.get(bibcode, bibcode), bibcode)
    for bibcode in polars.read_csv(snakemake.input.mp2_bibcodes)["bibcode"]
]
qu: list[str] = [
    bibcode_to_url.get(old_to_new.get(bibcode, bibcode), bibcode)
    for bibcode in polars.read_csv(snakemake.input.queue_bibcodes).filter(polars.col("netid").str.len_chars() > 0)["bibcode"]
]
jingyud: list[str] = [
    doi_to_url[doi]
    for doi in [
            "/".join(["https://doi.org", *doi_url.split("/")[-2:]])
            for doi_url in polars.read_csv(snakemake.input.jingyud_data)["article_link"]
    ]
    if doi in doi_to_url
]

completed_urls = collections.Counter([*cp_ignored, *mp2, *qu, *jingyud])
completed_urls_set = completed_urls.keys()

venues = {
    article_group.venue
    for article_group in article_groups
}
years = [2012, 2018, 2024]


lines = []
table = [
    ["Venue", *[str(year) for year in years]],
]
n_incomplete = 4
article_completions = []
for venue in venues:
    main_row = [venue] + [""] * len(years)
    incomplete_bibcodes_rows = [
        [""] * (len(years) + 1)
        for _ in range(n_incomplete)
    ]
    blank_row = [""] * (n_incomplete + 1)
    for year_idx, year in enumerate(years):
        for article_group in article_groups:
            if article_group.venue == venue and year - 1 <= article_group.date.year <= year + 1:
                urls = [
                    str(article.dblp_url)
                    for article in article_group.articles
                ]
                completed = [
                    article
                    for article in article_group.articles
                    if str(article.dblp_url) in completed_urls_set
                ]
                incomplete = [
                    article
                    for article in article_group.articles
                    if str(article.dblp_url) not in completed_urls_set
                ]
                article_completions.append((article_group, completed, incomplete))
                main_row[year_idx + 1] = f"{len(completed) / len(article_group.articles) * 100:.2f}% of {len(article_group.articles)}"
                for incomplete_idx in range(n_incomplete):
                    if incomplete_idx < len(incomplete):
                        incomplete_bibcodes_rows[incomplete_idx][year_idx + 1] = (incomplete[incomplete_idx].dblp_url.path or "").replace("/rec/", "")
                break
    table.append(main_row)
    table.append(blank_row)
    table.extend(incomplete_bibcodes_rows)
    table.append(blank_row)

lines.append(tabulate.tabulate(table))

lines.append("")

expected_urls = {
    str(article.dblp_url)
    for article_group in article_groups
    for article in article_group.articles
}

lines.append(f"# {len(completed_urls_set - expected_urls)} unnecessarily done")
for url in completed_urls_set - expected_urls:
    lines.append(url)
lines.append("")

for url, count in completed_urls.most_common():
    if count == 1:
        break
    else:
        lines.append(f"{count} x {url}")

pathlib.Path(snakemake.output.report).write_text("\n".join(lines))

prioritized_sequence = []
for i in range(0, 100, 1):
    priorities_for_i = []
    for article_group, completed, incomplete in article_completions:
        total = len(article_group.articles)
        assert total == len(completed) + len(incomplete)
        old_todo = max((i - 1) * total // 100 - len(completed), 0)
        todo = i * total // 100 - len(completed)
        if todo > 0:
            priorities_for_i.append((article_group, incomplete[old_todo:todo]))
    prioritized_sequence.append((i / 100, priorities_for_i))


polars.from_records([
    {
        "dblp_url": str(article.dblp_url),
        "netid": "",
        "type": "3",
        "frac": f"{int(frac * 100)}",
        "venue": article_group.venue,
        "year": article_group.date.year,
    }
    for frac, article_group_articles in prioritized_sequence
    for article_group, articles in article_group_articles
    for article in articles
]).write_csv(snakemake.output.output_queue)
