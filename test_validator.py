import shlex
import subprocess
import tempfile
import pydantic_core
import collections
import yaml
import typing
import aiohttp
import pathlib
import pytest
import pytest_asyncio
from repro_validator import validator
from repro_validator import schema
from repro_validator import dockerfile


project_root = pathlib.Path(__file__)


@pytest_asyncio.fixture(scope="function")
async def aiohttp_client() -> collections.abc.AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as aiohttp_client:
        yield aiohttp_client


@pytest.mark.asyncio
@pytest.mark.vcr
async def test_directory(
    aiohttp_client: aiohttp.ClientSession,
) -> None:
    errors = await async_collect_list(
        validator.validate_article_yaml(
            pathlib.Path("test_cases/"),
            aiohttp_client,
            use_archive_org=False,
            offline=False,
        )
    )
    assert any(
        level == validator.Level.fatal_error and "is a directory" in msg
        for level, msg in errors
    )


@pytest.mark.asyncio
@pytest.mark.vcr
async def test_nonexistant(
    aiohttp_client: aiohttp.ClientSession,
) -> None:
    errors = await async_collect_list(
        validator.validate_article_yaml(
            pathlib.Path("test_cases/nonexistant.yaml"),
            aiohttp_client,
            use_archive_org=False,
            offline=False,
        )
    )
    assert any(
        level == validator.Level.fatal_error and "does not exist" in msg
        for level, msg in errors
    )


@pytest.mark.asyncio
@pytest.mark.vcr
async def test_invalid_yaml(
    aiohttp_client: aiohttp.ClientSession,
) -> None:
    errors = await async_collect_list(
        validator.validate_article_yaml(
            pathlib.Path("test_cases/invalid_yaml.yaml"),
            aiohttp_client,
            use_archive_org=False,
            offline=False,
        )
    )
    assert any(
        level == validator.Level.fatal_error and "not valid yaml" in msg.lower()
        for level, msg in errors
    )


@pytest.mark.asyncio
@pytest.mark.vcr
async def test_invalid_article(
    aiohttp_client: aiohttp.ClientSession,
) -> None:
    errors = await async_collect_list(
        validator.validate_article_yaml(
            pathlib.Path("test_cases/invalid_article.yaml"),
            aiohttp_client,
            use_archive_org=False,
            offline=False,
        )
    )
    assert any(
        [
            level in {validator.Level.error, validator.Level.fatal_error}
            for level, message in errors
        ]
    )


@pytest.mark.asyncio
@pytest.mark.vcr
async def test_empty_article(
    aiohttp_client: aiohttp.ClientSession,
) -> None:
    errors = await async_collect_list(
        validator.validate_article(
            aiohttp_client,
            pathlib.Path(),
            schema.Article(
                dblp_url=pydantic_core.Url(
                    "https://dblp.org/rec/journals/taco/VerdoolaegeJCGTC13"
                )
            ),
            use_archive_org=False,
            offline=False,
        )
    )
    print(errors)
    assert any([level == validator.Level.error for level, msg in errors])


@pytest.mark.asyncio
@pytest.mark.vcr
async def test_invalid_ids(
    aiohttp_client: aiohttp.ClientSession,
) -> None:
    errors = await async_collect_list(
        validator.validate_article(
            aiohttp_client,
            pathlib.Path(),
            schema.Article(
                dblp_url=pydantic_core.Url("https://dblp.org/rec/a/b/c"),
            ),
            use_archive_org=False,
            offline=False,
        )
    )
    assert any(
        [level == validator.Level.error and "dblp.org" in msg for level, msg in errors]
    )


def test_run_cmd_coercer(
    aiohttp_client: aiohttp.ClientSession,
) -> None:
    r = schema.Run(
        type="RUN",
        cmds=[
            "ls foo bar", # type: ignore
            schema.Command(
                args=["cat", "bar", "baz"],
            ),
            {  # type: ignore
                "args": ["spam", "eggs"]
            },
        ],
    )
    assert r.cmds[0] == schema.Command(args=["ls", "foo", "bar"])
    assert r.cmds[1] == schema.Command(args=["cat", "bar", "baz"])
    assert r.cmds[2] == schema.Command(args=["spam", "eggs"])


buildable_cases = [
    pathlib.Path("test_cases/valid.yaml"),
    pathlib.Path("test_cases/valid_raw_string.yaml"),
    pathlib.Path("test_cases/valid_extra_resources.yaml"),
]


@pytest.mark.asyncio
@pytest.mark.vcr
@pytest.mark.parametrize("buildable_case", buildable_cases)
async def test_valid_article_yaml(
    aiohttp_client: aiohttp.ClientSession,
    buildable_case: pathlib.Path,
) -> None:
    errors = await async_collect_list(
        validator.validate_article_yaml(
            pathlib.Path("test_cases/valid.yaml"),
            aiohttp_client,
            use_archive_org=False,
            offline=False,
        )
    )
    for level, msg in errors:
        print(level, msg)
    assert not any(
        [
            level in {validator.Level.error, validator.Level.fatal_error}
            for level, msg in errors
        ]
    )


@pytest.mark.parametrize("buildable_case", buildable_cases)
def test_dockerfile_build(buildable_case: pathlib.Path) -> None:
    article_yaml_text = buildable_case.read_text()
    article_dict = yaml.safe_load(article_yaml_text)
    article = schema.Article(**article_dict)
    assert isinstance(article.computational_status, schema.ComputationalArticle)
    assert isinstance(article.computational_status.source_search, schema.SourceFound)
    assert article.computational_status.source_search.build_attempt is not None
    print(article.computational_status.source_search.build_attempt.base_image)
    result = dockerfile.to_dockerfile(
        pathlib.Path(),
        article.computational_status.source_search.build_attempt.base_image,
        [
            *article.computational_status.source_search.build_attempt.build_directives,
            *article.computational_status.source_search.build_attempt.test_directives,
        ],
    )
    subprocess.run(
        ["podman", "build", result.parent],
        check=True,
    )


def test_venv_installation() -> None:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([
            "bash",
            "-c",
            " && ".join([
                shlex.join(["python", "-m", "venv", ".venv"]),
                shlex.join(["source", ".venv/bin/activate"]),
                shlex.join(["pip", "install", str(project_root.parent)]),
                *[
                    shlex.join(["repro-validator", "export-dockerfile", str(buildable_case.resolve())])
                    for buildable_case in buildable_cases
                ],
            ]),
        ], check=True, cwd=td)


_T = typing.TypeVar("_T")


async def async_collect_list(
    iterable: typing.AsyncIterator[_T],
) -> list[_T]:
    return [item async for item in iterable]
