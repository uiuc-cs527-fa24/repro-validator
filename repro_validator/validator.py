import enum
import rdflib
import typing
import datetime
import aiohttp
import pydantic
import yaml
import pathlib
from . import schema
from . import util


class Level(enum.Enum):
    fatal_error = enum.auto()
    error = enum.auto()
    possible_error = enum.auto()


async def validate_article_yaml(
    article_yaml: pathlib.Path,
    aiohttp_client: aiohttp.ClientSession,
    use_archive_org: bool,
    offline: bool,
) -> typing.AsyncIterator[tuple[Level, str]]:
    if not article_yaml.exists():
        yield (Level.fatal_error, f"{article_yaml!s} does not exist.")
        return
    if article_yaml.is_dir():
        yield (Level.fatal_error, f"{article_yaml!s} is a directory.")
        return
    try:
        article_dict = yaml.safe_load(article_yaml.read_text())
        article = schema.Article(**article_dict)
    except yaml.YAMLError as exc:
        yield (Level.fatal_error, f"{article_yaml!s} is not valid YAML\n{exc!s}")
        return
    except pydantic.ValidationError as exc:
        yield (
            Level.fatal_error,
            str(exc),
        )
        return
    async for error in validate_article(
        aiohttp_client,
        article_yaml.parent,
        article,
        use_archive_org,
        offline,
    ):
        yield error


async def validate_article(
    aiohttp_client: aiohttp.ClientSession,
    base_path: pathlib.Path,
    article: schema.Article,
    use_archive_org: bool,
    offline: bool,
) -> typing.AsyncIterator[tuple[Level, str]]:
    # dblp_key is filled, the first result should be the DBLP metadata in Turtle format
    dblp_request = (
        util.url_bytes(
            aiohttp_client,
            util.pydantic_to_yarl(article.dblp_url).with_suffix(".ttl"),
        )
        if not offline
        else None
    )

    if article.badges is None:
        yield (
            Level.error,
            "Please fill badges with a list of ACM badges the article earned or empty-list",
        )

    if isinstance(article.computational_status, schema.Unknown):
        yield (Level.error, "computational_status should be filled")
    elif isinstance(article.computational_status, schema.ComputationalArticle):
        cp16_validation = (
            validate_breakable_link(
                aiohttp_client,
                article.computational_status.source_link_used_by_cp16,
                use_archive_org,
                offline,
            )
            if isinstance(article.computational_status, schema.ComputationalArticle)
            and article.computational_status.source_link_used_by_cp16
            else None
        )
        if isinstance(
            article.computational_status.source_search, schema.SourceNotFound
        ):
            for (
                search
            ) in article.computational_status.source_search.google_searches_tried:
                if search.startswith("http"):
                    yield (
                        Level.error,
                        "google_searches_tried should have the search strings, not URLs",
                    )
        else:
            source = article.computational_status.source_search
            source_path_validation = validate_link_path(
                aiohttp_client,
                source.path,
                use_archive_org=use_archive_org,
                offline=offline,
            )

            if source.build_attempt is not None:
                for directive in [
                    *source.build_attempt.build_directives,
                    *source.build_attempt.test_directives,
                ]:
                    if isinstance(directive, schema.CopyFile):
                        if (
                            directive.source.is_absolute()
                            or ".." in directive.source.parts
                        ):
                            yield (
                                Level.error,
                                f"Source {directive.source} should be relative and not contain ..",
                            )
                        if not directive.source.exists():
                            yield (
                                Level.error,
                                f"Source {directive.source} does not exist relative to the YAML {base_path}",
                            )
                        else:
                            if (
                                directive.source.is_file()
                                and directive.source.stat().st_size < 1024
                            ):
                                yield (
                                    Level.error,
                                    f"Source {directive.source} is a small file; include it as a CopyFileLiteral instead",
                                )
                        if not directive.destination.is_absolute():
                            yield (
                                Level.error,
                                f"Destination {directive.destination} should be absolute",
                            )
                    elif isinstance(directive, schema.CopyFileLiteral):
                        if not directive.destination.is_absolute():
                            yield (
                                Level.error,
                                f"Destination {directive.destination} should be absolute",
                            )
                    elif isinstance(directive, schema.Run):
                        for command in directive.cmds:
                            if command.args[0] == "wget":
                                yield (
                                    Level.possible_error,
                                    "Replace wget with curl if possible",
                                )
                            elif command.args[0] in {"apt", "apt-get"}:
                                yield (
                                    Level.error,
                                    "Replace apt with apt-get install block",
                                )
                            elif command.args[0] == "sudo":
                                yield (
                                    Level.error,
                                    "Remvoe sudo; we are already root in the docker container",
                                )
                            elif (
                                command.args[0] == "apt-get"
                                and "build-essential" in command.args
                            ):
                                yield (
                                    Level.error,
                                    "Replace build-essential with more specific packages (e.g., make, gcc)",
                                )

                if isinstance(source.build_attempt.result, schema.BuildCrash):
                    if len(source.build_attempt.result.crashing_command_output) > 1024:
                        yield (
                            Level.possible_error,
                            "Is there any way you can abbreviate the crashing_command_output? Redundant log lines can be deleted",
                        )

            async for error in source_path_validation:
                yield error

        if cp16_validation is not None:
            async for error in cp16_validation:
                yield error

    if dblp_request is not None:
        url, status, _, text = await dblp_request
        if status == 200:
            graph = rdflib.Graph()
            graph.parse(data=text.decode(), format="ttl")
            article_node = rdflib.URIRef(str(article.dblp_url))
            years = [
                *graph.objects(
                    article_node,
                    rdflib.URIRef("https://dblp.org/rdf/schema#yearOfPublication"),
                ),
                *graph.objects(
                    article_node,
                    rdflib.URIRef("https://dblp.org/rdf/schema#yearOfEvent"),
                ),
            ]
            if not years:
                yield (
                    Level.error,
                    "DBLP doesn't record the year of publication for this article. Report to TAs.",
                )
            else:
                if int(str(years[0])) in {2012, 2013}:
                    if (
                        isinstance(
                            article.computational_status, schema.ComputationalArticle
                        )
                        and article.computational_status.source_link_used_by_cp16
                        is None
                    ):
                        yield (
                            Level.error,
                            "Article from 2012 or 2013 should have source_link_used_by_cp16",
                        )
        else:
            yield (
                Level.error,
                f"dblp_key is wrong; {url!s} does not resolve ({status})",
            )


async def validate_breakable_link(
    aiohttp_client: aiohttp.ClientSession,
    breakable_link: schema.BreakableLink,
    use_archive_org: bool,
    offline: bool,
) -> typing.AsyncIterator[tuple[Level, str]]:
    host = breakable_link.url.host or ""
    if host in {"www.google.com", "web.archive.org"}:
        if (
            breakable_link.born_after
            or breakable_link.earliest_alive_on
            or breakable_link.latest_alive_on
            or breakable_link.dead_on
        ):
            yield (
                Level.error,
                "Do not put lifetime information on Google searches or Internet Archive queries",
            )
        return

    link_request = (
        util.url_status(
            aiohttp_client,
            util.pydantic_to_yarl(breakable_link.url),
        )
        if not offline
        else None
    )

    order = []
    if breakable_link.born_after:
        order.append(breakable_link.born_after)
    if breakable_link.earliest_alive_on:
        order.append(breakable_link.earliest_alive_on)
    if breakable_link.latest_alive_on:
        order.append(breakable_link.latest_alive_on)
    if breakable_link.dead_on:
        order.append(breakable_link.dead_on)
    order.append(datetime.datetime.now().astimezone())
    if order != sorted(order):
        yield (
            Level.error,
            f"Dates are in the wrong order for {breakable_link.url!s}; should be born_after < earliest_alive_on < latest_alive_on < dead_on < now()",
        )

    if link_request:
        url, status, _ = await link_request
        if status != 200 and not breakable_link.dead_on:
            yield (
                Level.error,
                f"{breakable_link.url!s} is dead; dead_on should be set to whenever you first noticed this (today?)",
            )
        elif status == 200:
            if breakable_link.dead_on:
                yield (
                    Level.possible_error,
                    f"{breakable_link.url!s} seems to resolve, so maybe it is not dead. If the link resolves, but the intended content is not there, ignore this.",
                )
            elif (
                breakable_link.latest_alive_on is None
                or breakable_link.latest_alive_on
                <= datetime.datetime.now().astimezone() - datetime.timedelta(days=30)
            ):
                yield (
                    Level.possible_error,
                    f"{breakable_link.url!s} seems to resolve, so latest_alive_on should probably be today.",
                )


async def validate_link_path(
    aiohttp_client: aiohttp.ClientSession,
    link_path: schema.LinkPath,
    use_archive_org: bool,
    offline: bool,
) -> typing.AsyncIterator[tuple[Level, str]]:
    breakable_link_validations = [
        validate_breakable_link(
            aiohttp_client,
            link,
            use_archive_org=use_archive_org,
            offline=offline,
        )
        for link in link_path.links
    ]
    url_results = [
        util.url_bytes(
            aiohttp_client,
            util.pydantic_to_yarl(link.url),
        )
        if not offline
        else None
        for link in link_path.links[:-1]
    ]
    for link0, link0_results, link1 in zip(
        link_path.links[:-1], url_results, link_path.links[1:]
    ):
        link1_host = (link1.url.host or "").lower().encode()
        link1_path = (link1.url.path or "").lower().encode()
        if link0_results:
            _, link0_status, link0_url, link0_page = await link0_results
            if link1_host == b"web.archive.org":
                archived_url = link1_path.split(b"/")[2]
                if archived_url != str(link0.url).encode():
                    yield (
                        Level.error,
                        f"{link1.url!s} is an archive URL, but it does not look like an archived version of {link0.url!s}",
                    )
            elif link0_status != 200:
                yield (
                    Level.possible_error,
                    f"Link {link0.url!s} does not resolve ({link0_status}) and the next link is NOT web.archive.org. If I am wrong about whether the link resolves (if it resolves for you in browser), please ignore.",
                )
                continue
            else:
                link0_page = link0_page.lower()
                if link1_host not in link0_page or link1_path not in link0_page:
                    yield (
                        Level.possible_error,
                        f"I don't see where {link0.url!s} links to {link1.url!s}. If the link really is there, ignore this message.",
                    )

    first_url_host = link_path.links[0].url.host or ""
    if (first_url_host or "").lower() not in {"doi.org", "www.google.com"}:
        yield (
            Level.error,
            f"First link in every path should be article (https://doi.org/10.xxx/yyy) or https://www.google.com/search search query not {first_url_host}",
        )

    for breakable_link_validation in breakable_link_validations:
        async for error in breakable_link_validation:
            yield error


def get_archive_id(dt: datetime.datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S")
