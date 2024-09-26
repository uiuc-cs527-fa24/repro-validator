#!/usr/bin/env python
from typing_extensions import Annotated
import pydantic
import rich.console
import pathlib
import typer
import yaml


console = rich.console.Console()


class MP2InputItem(pydantic.BaseModel):
    bibcode: str
    article_url: str
    title: str
    authors: str = ""
    original_source_link: str = ""
    build_notes: str = ""


MP2Input = pydantic.TypeAdapter(list[MP2InputItem])


class SourceReport(pydantic.BaseModel):
    original_link: pydantic.HttpUrl | None = None
    original_dead: bool
    google_searches: list[str] = []
    link_path: list[pydantic.HttpUrl] = []
    minutes_spent: int
    source_downloadable: bool
    binary_downloadable: bool = False
    before_live_snapshot: pydantic.PositiveInt | None = None
    first_live_snapshot: pydantic.PositiveInt | None = None
    last_live_snapshot: pydantic.PositiveInt | None = None
    first_dead_snapshot: pydantic.PositiveInt | None = None


class PackageManagerReport(pydantic.BaseModel):
    name: str
    packages_installed: list[str]


class BuildReport(pydantic.BaseModel):
    minutes_spent: int
    online_references: list[pydantic.HttpUrl] = []
    package_managers_used: list[PackageManagerReport] = []
    skip_build: bool = False
    build_success: bool | None = None
    crash_reason: str | None = None
    crash_matches_prior: bool | None = None
    functional_test_success: bool | None = None
    functional_test_description: str | None = None
    bitwise_reproducible: bool | None = None
    bitwise_irreproducible_reason: str | None = None


class Report(pydantic.BaseModel):
    source: SourceReport
    build: BuildReport | None = None
    notes: str = ""


def main(
    path: Annotated[pathlib.Path, typer.Argument(help="Path to cs527")],
) -> None:
    mp2_input_path = path / "mp2_input.yaml"
    if not mp2_input_path.exists():
        fatal_error(
            f"{mp2_input_path!s} does not exist. Are you sure this is your right repo?"
        )
    try:
        mp2_input = MP2Input.validate_python(yaml.safe_load(mp2_input_path.read_text()))
    except yaml.YAMLError as exc:
        fatal_error(
            f"{mp2_input_path!s} is not valid; This is likely a problem with the TAs",
            exc,
        )
    except pydantic.ValidationError as exc:
        fatal_error(
            f"{mp2_input_path!s} is not valid; This is likely a problem with the TAs",
            exc,
        )
    build_success = 0
    for item in mp2_input:
        data_path = path / item.bibcode / "data.yaml"
        has_warnings = False
        console.rule(f"{item.bibcode}")
        if not data_path.exists():
            possible_warning(item.bibcode, f"No {data_path}. This is ok if you have two successes PRIOR to this point.")
            continue

        try:
            data_dict = yaml.safe_load(data_path.read_text())
        except yaml.YAMLError as exc:
            warning(item.bibcode, f"{data_path!s}: {exc}")
            continue
        try:
            data = Report.model_validate(data_dict)
        except pydantic.ValidationError as exc:
            warning(item.bibcode, f"{data_path!s}: schema mismatch: {exc}")
            console.print(data_dict)
            continue

        if (
            item.original_source_link
            and data.source.original_link
            and item.original_source_link != str(data.source.original_link)
        ):
            warning(
                item.bibcode,
                f"original_souce_link exists in mp2_input.yaml, so it should be used as the original_link in {item.bibcode}/data.yaml.",
            )
            has_warnings = True

        if not data.source.original_dead and (
            data.source.last_live_snapshot or data.source.first_dead_snapshot
        ):
            warning(
                item.bibcode,
                "last_live and first_dead cannot be observed for a currently live URL.",
            )
            has_warnings = True

        if not data.source.source_downloadable and not data.source.google_searches:
            warning(item.bibcode, "If source is dead, must do Google searches.")
            has_warnings = True

        if not data.source.original_dead and data.source.google_searches:
            possible_warning(item.bibcode, "If source is alive, you probably don't need for Google searches.")

        if data.source.source_downloadable and not data.source.link_path:
            warning(
                item.bibcode, "Must have link_path, even if it is only 1 or 2 elements."
            )
            has_warnings = True

        if (
            item.original_source_link
            and not data.source.original_dead
            and str(data.source.link_path[0]) != item.original_source_link
        ):
            possible_warning(
                item.bibcode,
                "Original link is alive, so it should probably be the start of the link_path. Ignore this if your link_path really does start from somewhere else",
            )

        if data.source.source_downloadable and data.build is None:
            warning(
                item.bibcode, "If source is downloadable, fille the build section. If you need to skip, fill it as much as possible and write skip_build: true",
            )

        if data.build is None:
            continue

        if data.build.minutes_spent == 30:
            possible_warning(
                item.bibcode,
                "build.minutes_spent: 30 was a placeholder. Please be sure this is not in error. If you actually spent 30 minutes, that's fine.",
            )

        if not data.build.skip_build:
            dockerfile_path = path / item.bibcode / "Dockerfile"
            if not dockerfile_path.exists():
                warning(
                    item.bibcode,
                    "If the build is not skipped, please include the Dockerfile",
                )
                has_warnings = True

            if data.build.build_success is None:
                warning(
                    item.bibcode,
                    "If the build is not skipped, please fill build.build_success (bool)",
                )
                has_warnings = True

            if not data.build.build_success:
                problem_md_path = path / item.bibcode / "problem.md"
                if not problem_md_path.exists():
                    warning(
                        item.bibcode,
                        "If build is not successful, write problem.md describing the problem",
                    )
                    has_warnings = True

                problem_md_path = path / item.bibcode / "docker_build_output.txt"
                if not problem_md_path.exists():
                    warning(
                        item.bibcode,
                        "If build is not successful, put output showing error in docker_build_output.txt",
                    )
                    has_warnings = True

                if data.build.crash_reason is None:
                    warning(
                        item.bibcode,
                        "If build is not successful, must have crash_reason",
                    )
                    has_warnings = True

                if data.build.crash_reason not in crash_reasons:
                    warning(
                        item.bibcode,
                        "crash_reason must be a crash reason from <https://canvas.illinois.edu/courses/49727/pages/crash-reasons-for-mp2>",
                    )
                    console.print("Currently accepted crash reasons:\n" + "\n".join(map(repr, crash_reasons)))
                    console.print("Your crash reason: " + repr(data.build.crash_reason))
                    has_warnings = True

                if item.build_notes and data.build.crash_matches_prior is None:
                    warning(
                        item.bibcode,
                        "Determine if this crash matches the one in described in build notes (if any)",
                    )
                    has_warnings = True

                if not item.build_notes and data.build.crash_matches_prior is not None:
                    warning(
                        item.bibcode,
                        "We did not give you any prior build notes to compare to for this article; please remove crash_matches_prior",
                    )
                    has_warnings = True

            else:  # build success
                build_success += 1

                if data.build.functional_test_success is None:
                    warning(
                        item.bibcode,
                        "If build succeeds, report status of functional tests",
                    )
                    has_warnings = True

                if data.build.functional_test_description is None:
                    warning(
                        item.bibcode,
                        "If build succeeds, write and describe functional tests",
                    )
                    has_warnings = True

                if data.build.bitwise_reproducible is None:
                    warning(
                        item.bibcode,
                        "If build succeeds, evaluate bitwise reproducibility",
                    )
                    has_warnings = True

                if (
                    not data.build.bitwise_reproducible
                    and not data.build.bitwise_irreproducible_reason
                ):
                    warning(
                        item.bibcode,
                        "If not bitwise reproducible, please give a brief guess of why this is the case",
                    )
                    has_warnings = True

                if data.build.bitwise_irreproducible_reason is not None and "foo bar" in data.build.bitwise_irreproducible_reason:
                    warning(
                        item.bibcode,
                        "foo bar is placeholder text! Please fill with an acutal reason in bitwise_irreproducible_reason"
                    )

        if "foo bar" in data.notes:
            warning(item.bibcode, "foo bar is placeholder text! If you don't have something to say, don't say anything at all in notes.")

        if not has_warnings:
            console.print(f"[green]{item.bibcode} is valid :white_check_mark:[/green]")

    console.rule()
    console.print(f"[green]{build_success} successful builds[/green]")
    console.print("Please make sure your minutes_spent is up-to-date.")


def fatal_error(string: str, exc: Exception | None = None) -> None:
    console.print(f"[red]:collision: Error: {string}; aborting[/red]")
    if exc:
        console.print(exc)
    raise typer.Exit(code=1)


def fatal_error_in_bibcode(bibcode: str, string: str) -> None:
    console.print(f"[red]:collision: Error: {bibcode}: {string}[/red]")


def warning(bibcode: str, string: str) -> None:
    console.print(f"[yellow]:x: Warning: {bibcode}: {string}[/yellow]")


def possible_warning(bibcode: str, string: str) -> None:
    console.print(f"[yellow]:face_with_raised_eyebrow: Possible warning: {bibcode}: {string}[/yellow]")


crash_reasons = {
    "Un-acquirable software dependence",
    "Not containerizable",
    "Requires GPU",
    "Needs more RAM",
    "Takes too long",
    "Requires more time and/or expertise",
}


if __name__ == "__main__":
    typer.run(main)
