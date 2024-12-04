import typing
import yaml
import pathlib
import polars
import rich.progress
from repro_validator.schema import ArticleGroup


if typing.TYPE_CHECKING:
    snakemake = typing.Any


# Parse our articles
article_groups = [
    ArticleGroup(**yaml.safe_load(pathlib.Path(article_group).read_text()))
    for article_group in rich.progress.track(snakemake.input.article_groups, description="article_groups")
]
article_groups_2012 = [
    article_group
    for article_group in article_groups
    if article_group.date.year in {2011, 2012}
]

# Parse their articles
cp_bibcodes = polars.read_csv(snakemake.input.cp_bibcodes)

# Load translations
bibcode_to_url = dict(polars.read_csv(snakemake.input.bibcode_to_url).select("bibcode", "url").rows())
old_to_new_bibcodes = dict(polars.read_csv(snakemake.input.old_to_new_bibcodes).select("old", "new").rows())

# Get all venues
venue_mapping = {
    "(P)VLDB": "VLDB",
    "TOPS/TISSEC": "TISSEC",
}
venues = {
    venue_mapping.get(name, name)
    for name in {
        *{article_group.venue for article_group in article_groups_2012},
        *{venue.split(" ")[0] for venue in cp_bibcodes["venue"]},
    }
}

# For each venue, write report
lines = [
    "This report shows the differences between DBLP bibcodes and C&P bibcodes for each venue.",
    "",
]
for venue in rich.progress.track(venues, description="venues"):
    print(venue)
    lines.append(f"# {venue}")
    this_dblp_bibcodes = {
        (article.dblp_url.path or "").split("/")[-1]
        for article_group in article_groups_2012
        if venue in article_group.venue
        for article in article_group.articles
    }
    this_cp_bibcodes = frozenset(
        old_to_new_bibcodes.get(bibcode, bibcode)
        for bibcode in cp_bibcodes.filter(polars.col("venue").str.contains(venue))["bibcode"]
    )
    if this_dblp_bibcodes - this_cp_bibcodes:
        lines.append(f"## In DBLP but not C&P {len(this_dblp_bibcodes - this_cp_bibcodes)}")
        for bibcode in this_dblp_bibcodes - this_cp_bibcodes:
            url = bibcode_to_url.get(bibcode)
            lines.append(f"{bibcode} {url}")
        lines.append("")
    if this_cp_bibcodes - this_dblp_bibcodes:
        lines.append(f"## In C&P but not DBLP {len(this_cp_bibcodes - this_dblp_bibcodes)}")
        for bibcode in this_cp_bibcodes - this_dblp_bibcodes:
            url = bibcode_to_url.get(bibcode)
            lines.append(f"{bibcode} {url}")
        lines.append("")
    lines.append(f"Size of Intersection: {len(this_dblp_bibcodes & this_cp_bibcodes)}")
    lines.append("")

pathlib.Path(snakemake.output[0]).write_text("\n".join(lines))
