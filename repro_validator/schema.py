from __future__ import annotations
import enum
import typing
import pydantic
import pydantic_core
import shlex
import pathlib


class ArticleGroup(pydantic.BaseModel):
    dblp_search: pydantic.HttpUrl

    articles: typing.Sequence[Article]
    """
    Articles, sorted, and shuffled with seed 0.
    """

    date: pydantic.AwareDatetime

    venue: str

    venue_type: VenueType

    area: list[CSArea]


class VenueType(enum.StrEnum):
    conference = enum.auto()
    journal = enum.auto()


class CSArea(enum.StrEnum):
    computer_architecture = enum.auto()
    programming_languages = enum.auto()
    operating_systems = enum.auto()
    computer_security = enum.auto()


class Unknown(pydantic.BaseModel):
    type: typing.Literal["Unknown"] = "Unknown"


class Article(pydantic.BaseModel):
    version: str = "0.2.11"
    """Version of the schema validator this article uses.

    If omitted, we will fall back to the first version available."""

    dblp_url: typing.Annotated[
        pydantic.HttpUrl, pydantic.AfterValidator(is_valid_dblp_url)
    ]
    """DBLP key in https://dblp.org

    This can be found by:

    1. Searching for the article title and/or authors in DBLP
       E.g., https://dblp.org/search?q=LOT%3A+A+Defense+Against+IP+Spoofing+and+Flooding+Attacks

    2. Hovering over the fourth button (Share Record).
       E.g., "https://dblp.org/rec/journals/tissec/GiladH12

    Or just directly guessing (and verifying!) it. Here are some examples:

    - https://dblp.org/rec/journals/tissec/GiladH12.ttl
    - https://dblp.org/rec/conf/asplos/0003GN18

    But there are some exceptions (VLDB -> "pvldb", etc.)

    """

    computational_status: typing.Annotated[
        ComputationalArticle | NoncomputationalArticle | Unknown,
        pydantic.Field(discriminator="type"),
    ] = Unknown()
    """
    This should be determined by going through the following steps, breaking
    when you are sufficiently confident in the answer:

    1. If the article has source code, it is backed by soruce.

    2. Read the abstract, paying close attention to key words such as
       "evaluate", "tool", and "benchmark".

    3. Read any heading similar to "evalution", "experiments".

    4. Look at any quantitative graphs (bar-char, line graph, etc.).

    """

    badges: set[Badge] | None = None
    """What badges, if any, this article has."""


class NoncomputationalArticle(pydantic.BaseModel):
    type: typing.Literal["NoncomputationalArticle"]


class ComputationalArticle(pydantic.BaseModel):
    type: typing.Literal["ComputationalArticle"]

    source_link_used_by_cp16: BreakableLink | None = None
    """Link to source code used by [CP16], if article comes from CP16 dataset.

    Also see [CP16 raw data].

    [CP16]: Collberg and Proebsting. Repeatability in computer systems research.
    2016. https://doi.org/10.1145/2812803

    [CP16 raw data]:
    https://web.archive.org/web/20220119115703/http://reproducibility.cs.arizona.edu/

    """

    tool_names: typing.Sequence[str]
    """Name of the tools by the paper introduced, if any."""

    innermost_computational_section_headings: typing.Sequence[str]
    """List of the innermost section headings that describe computational results.

    Omit the heading number, if any.

    E.g., "Experimental Evaluation"
    """

    source_search: typing.Annotated[
        SourceFound | SourceNotFound,
        pydantic.Field(discriminator="type"),
    ]
    """
    If the article is backed by computation, source or binary should be found be
    discovered with the following procedure:

    1. Notice if there is an artifact badge (image) at the top of the first page
       ("Artifact Available", "Artifact Functional", etc.). If the article has a
       badge, it should have source available somewhere. TODO: example

    2. Check the publisher's website. This is usually the padge before you get
       to the PDF, searching for "reproduc" or "artifact". E.g., TODO: example

    3. Download the article and Ctrl+F for "availab", "git", "artifact",
       "material" (as in supplementary/companion material), "reproduc",
       "zenodo", "http".

       "http" may hit a lot in the references page. Please check the first five
       hits on the references page, and then you may skip the rest of the hits
       on the references pages for "http".

    4. Skim the headings to see if there is a artifact or reproducibility section.

    5. Skim the footnotes to see if any contains a source URL.

    6. Search "${name of tool} ${keyword of domain} ${author name or names}
       (github | source code)" and several variants on Google.

    """


class SourceNotFound(pydantic.BaseModel):
    type: typing.Literal["SourceNotFound"]

    google_searches_tried: typing.Sequence[str]
    """List of search strings (NOT URLs)"""

    notes: str
    """Any extra notes"""


class SourceFound(pydantic.BaseModel):
    type: typing.Literal["SourceFound"]

    path: LinkPath
    """Link path to source code(s) used in this work.

    Make sure to keep track of the links you are clicking and record the entire
    path. In particular,

      - The first link should be the article DOI or a Google search.

      - The intermediate links should be links found in the prior element's HTML
        or PDF. OR the link switches to/from archive.org version.

      - The last link should be "final/downloadable" link to the sources, e.g.,
        Zip file, HTTP view of a git repo. Prefer git-cloneable URL over
        downloadable zip if both are offered. After that, prefer https:// over
        http:// over git:// if equivalent URLs are offered.

    If multiple repositories are found, choose the one which has the newest
    commits.

    """

    is_source_versioned: bool
    """Whether older or newer versions of the source are available (possibly at different links).

    E.g., for git repositories, this should be set to True.

    """

    extra_resources: frozenset[NonstandardResource] = frozenset()
    """A list of extra resources requried beyond a headless x86_64 Linux, if any.

    This should usually be empty.
    """

    reproducibility_documentation_level: DocumentationLevel

    build_attempt: BuildAttempt | None = None
    """Build attempt, if any was made"""


class DocumentationLevel(enum.StrEnum):
    """Choose the first applicable level, in order."""

    specifies_every_command = enum.auto()
    """The documentation specifies every or almost every command you had to run to get this artifact to build.

    Small exceptions are allowed if they are obvious or system-specific, e.g., `cd /code`, `apt-get update`.

    """

    specifies_some_commands = enum.auto()
    """The documentation specifies some of the commands you had to run to get this artifact to build."""

    specifies_english = enum.auto()
    """The documentation does not specify any commands, but has plain English description of the required steps."""

    no_documentation = enum.auto()
    """There is no reproducibility documentation at all."""


class BreakableLink(pydantic.BaseModel):
    url: typing.Annotated[
        pydantic_core.Url,
        pydantic.UrlConstraints(
            host_required=True,
            allowed_schemes=["https", "http", *vcs_schemes, "ftp"],
        ),
    ]
    """URL

    Prefer HTTPS > HTTP > Git > hg (mercurial) > SVN > FTP.

    Prefer code repository over downloadable Zip archive.

    No need to write lifetime (born_after, etc.) for Google or Internet Archive queries.
    """

    born_after: pydantic.AwareDatetime | None = None
    """Date at which the link does not resolve or does not hold the specified
    information (at any version).

    This will usually come from archive.org.

    None means "we don't know" or "not applicable".
    """

    earliest_alive_on: pydantic.AwareDatetime | None = None
    """Earliest date we know of on which the link resolved and holds the specified
    information (any version).

    This will usually come from archive.org

    None means "we don't know".
    """

    latest_alive_on: pydantic.AwareDatetime | None = None
    """Latetst date we know of on which the link resolved and holds the specified
    information (at any version).


    This will usually come from archive.org (for dead links) or your wall
    calendar and clock (for alive links).

    """

    dead_on: pydantic.AwareDatetime | None = None

    description: str = ""


class LinkPath(pydantic.BaseModel):
    links: typing.Sequence[BreakableLink]


class BaseImage(pydantic.BaseModel):
    name: str
    tag: str


class BuildAttempt(pydantic.BaseModel):
    base_image: BaseImage = BaseImage(name="ubuntu", tag="16.04")
    """Base-image and tag for build and test

    Use base-images in this order of preference:
    1. A slim Ubuntu image from the time of the articles publsihing.
    2. A newer or older slim Ubuntu image
    3. Any other slim generic Linux distribution base image
    4. Any other image
    """

    # instruction_quality:
    # """Time spent working on the build (excluding finding the main source code) in minutes."""

    time_spent: int
    """Time spent working on the build (excluding finding the main source code) in minutes."""

    build_directives: typing.Sequence[DockerfileDirectiveUnion]
    """A list of Docker directives"""

    test_directives: typing.Sequence[DockerfileDirectiveUnion]
    """A list of Docker directives

    Use the first of the following that apply as a test:

    1. Test suite (e.g., pytest, mvn test).
    2. Example input/output (e.g., diff <(./built_binary < input) expected_output).
    3. Running several runnable scripts.
    3. Executability of built binary (e.g., ./built_binary --version) or importability of scripts.
    """

    result: typing.Annotated[
        BuildCrash | TestFail | BuildAndTestSuccess,
        pydantic.Field(discriminator="type"),
    ]


class BuildCrash(pydantic.BaseModel):
    type: typing.Literal["BuildCrash"]

    time_spent: int
    """Time spent working on the build (excluding finding the main source code) in minutes."""

    crashing_command_output: str
    """Abbreviated output of the commnad that is crashing.

    Previous commands are not needed, unless they look relevant."""

    code: ErrorCode
    """Choose the most applicable code"""

    description: str
    """Markdown description of why the crash is failing.

    The description should include:

    1. The proximate and ultimate causes of the crash
    2. Online sources consulted
    3. Workarounds tried
    """


class ErrorCode(enum.StrEnum):
    """If you don't have a specific error code in mind, use `unassigned`."""

    missing_data = enum.auto()
    unassigned = enum.auto()


class TestFail(pydantic.BaseModel):
    type: typing.Literal["TestFail"]

    description: str
    """Description of why the test failed.

    The description should include:
    1. The proximal and distal cause of test failure.
    2. Fixes tried.
    """

    code: ErrorCode
    """Choose the most applicable code"""


class BuildAndTestSuccess(pydantic.BaseModel):
    type: typing.Literal["BuildAndTestSuccess"]

    notes: str = ""


def is_valid_dblp_url(url: pydantic.HttpUrl) -> pydantic.HttpUrl:
    if (
        url.scheme == "https"
        and url.host == "dblp.org"
        and url.path
        and url.path.startswith("/rec/")
        and "." not in url.path
    ):
        return url
    else:
        raise ValueError(
            f"{url} does not smell like a DBLP key, e.g. 'https://dblp.org/rec/journals/tissec/GiladH12'"
        )


vcs_schemes = ["git", "svn", "cvs", "hg"]


class NonstandardResource(enum.StrEnum):
    arm_cpu = enum.auto()
    intel_cpu = enum.auto()
    intel_sgx_cpu = enum.auto()
    intel_vt_x = enum.auto()
    gpu = enum.auto()
    more_than_1_hour = enum.auto()
    more_than_8gb_ram = enum.auto()
    more_than_100gb_storage = enum.auto()
    graphical_environment = enum.auto()
    remote_api = enum.auto()
    commercial_cloud = enum.auto()
    performance_counter_access = enum.auto()
    manipulate_linux_kernel_modules = enum.auto()
    manipulate_docker_containers = enum.auto()


class DockerfileDirective(pydantic.BaseModel):
    # id: str
    # predecessors: frozenset[str]
    comment: str = ""


class Run(DockerfileDirective, pydantic.BaseModel):
    """A structured version of the usual RUN command.

    All of the commands are run with ' && ' between them.
    """

    type: typing.Literal["RUN"] = "RUN"

    cmds: typing.Annotated[
        typing.Sequence[Command],
        pydantic.BeforeValidator(parse_cmds),
    ]
    """cmds accepts a list of strings"""

    specific_env_vars: typing.Mapping[str, str] = dict()
    """Environment variables to set at the beginning of execution"""

    eval_string: str = ""
    """Eval this string before continuing. Can be $(subshell)"""


def parse_cmds(
    cmds: list[Command | str | typing.Mapping[str, typing.Any]],
) -> typing.Sequence[Command]:
    ret = []
    for cmd in cmds:
        if isinstance(cmd, str):
            ret.append(Command(args=shlex.split(cmd)))
        elif isinstance(cmd, Command):
            ret.append(cmd)
        elif isinstance(cmd, dict):
            ret.append(Command(**cmd))
        else:
            raise TypeError(f"Unexpected cmds: {cmds!r}, cmds[0]: {cmds[0]!r}")
    return ret


class Command(pydantic.BaseModel):
    """A structured command."""

    args: typing.Sequence[str]
    """Arguments supplied to executable"""

    redirect_stdin: pathlib.Path | None = None
    """Redirect stdin with '<'"""

    redirect_stdout: pathlib.Path | None = None
    """Redirect stdout with '>'"""

    redirect_stderr: pathlib.Path | None = None
    """Redirect stdout with '2>'"""

    ignore_failure: bool = False
    """Ignore failure with '|| true'"""


def parse_args(cmd: list[str] | str) -> typing.Sequence[str]:
    if isinstance(cmd, list):
        return cmd
    elif isinstance(cmd, str):
        return shlex.split(cmd)
    else:
        raise TypeError(f"Unexpected {type(cmd).__name__}: {cmd!r}")


class RawRun(DockerfileDirective, pydantic.BaseModel):
    """For special cases where the structured RUN does not work"""

    type: typing.Literal["Raw RUN"] = "Raw RUN"
    cmds: str


class AptGetInstall(DockerfileDirective, pydantic.BaseModel):
    type: typing.Literal["apt-get install"] = "apt-get install"
    packages: typing.Sequence[str | tuple[str, str]]


class Env(DockerfileDirective, pydantic.BaseModel):
    type: typing.Literal["ENV"] = "ENV"
    mapping: typing.Mapping[str, str]


class CopyFileLiteral(DockerfileDirective, pydantic.BaseModel):
    type: typing.Literal["COPY file literal"] = "COPY file literal"
    contents: str
    destination: pathlib.PurePath
    executable: bool


class CopyFile(DockerfileDirective, pydantic.BaseModel):
    type: typing.Literal["COPY file"] = "COPY file"
    source: pathlib.Path
    destination: pathlib.PurePath


DockerfileDirectiveUnion: typing.TypeAlias = typing.Annotated[
    Run | RawRun | AptGetInstall | Env | CopyFileLiteral | CopyFile,
    pydantic.Field(json_schema_extra={"descriminator": "type"}),
]


class Badge(enum.StrEnum):
    """Badges defined on these pages:

    - <https://www.acm.org/publications/policies/artifact-review-and-badging-current>
    - <https://www.acm.org/publications/policies/artifact-review-badging>
    """

    artifacts_evaluated_functional_v1_1 = enum.auto()
    artifacts_evaluated_reusable_v1_1 = enum.auto()
    artifacts_available_v1_1 = enum.auto()
    results_reproduced_v1_1 = enum.auto()
    results_replicated_v1_1 = enum.auto()

    artifacts_evaluated_functional = enum.auto()
    artifacts_evaluated_reusable = enum.auto()
    artifacts_available = enum.auto()
    results_reproduced = enum.auto()
    results_replicated = enum.auto()
