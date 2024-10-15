import shutil
import collections
import tempfile
import pathlib
import shlex
import typing
from . import schema


def to_dockerfile(
    base_path: pathlib.Path,
    base_image: schema.BaseImage,
    directives: typing.Sequence[schema.DockerfileDirective],
) -> pathlib.Path:
    tempdir = pathlib.Path(tempfile.mkdtemp())  # TODO: this
    (tempdir / "Dockerfile").write_text(to_dockerfile_source(base_image, directives))
    for directive in directives:
        if isinstance(directive, schema.CopyFile):
            shutil.copy2(base_path / directive.source, tempdir / directive.source)
    return tempdir


def to_dockerfile_source(
    base_image: schema.BaseImage,
    directives: typing.Sequence[schema.DockerfileDirective],
) -> str:
    lines = [
        f"FROM {base_image.name}:{base_image.tag}"
    ]
    for directive in directives:
        if isinstance(directive, schema.Run):
            lines.append("RUN \\")
            if directive.eval_string:
                lines.append(f"    eval {directive.eval_string} && \\")
            if directive.specific_env_vars:
                lines.extend(
                    f"    {var}={val} \\"
                    for var, val in directive.specific_env_vars.items()
                )
            for command, is_last in is_last_sentinel(directive.cmds):
                lines.append(
                    " ".join(
                        filter(
                            bool,
                            [
                                "    ",
                                f"{shlex.join(command.args)}",
                                (
                                    f"< {command.redirect_stdin}"
                                    if command.redirect_stdin
                                    else ""
                                ),
                                (
                                    f"> {command.redirect_stdout}"
                                    if command.redirect_stdout
                                    else ""
                                ),
                                (
                                    f"2> {command.redirect_stderr}"
                                    if command.redirect_stderr
                                    else ""
                                ),
                                ("|| true" if command.ignore_failure else ""),
                                ("&& \\" if not is_last else ""),
                            ],
                        )
                    )
                )
        elif isinstance(directive, schema.RawRun):
            lines.append("RUN \\")
            lines.append("    " + directive.cmds)
        elif isinstance(directive, schema.Env):
            lines.append("ENV \\")
            for (var, val), is_last in is_last_sentinel(directive.mapping.items()):
                lines.append(f"    {var}={val}" + (" \\" if is_last else ""))
        elif isinstance(directive, schema.CopyFileLiteral):
            lines.append(f"RUN cat <<EOF > {directive.destination!s}\\")
            lines.append(directive.contents)
            if directive.executable:
                lines.append(f"EOF && chmod +x {directive.destination!s}")
            else:
                lines.append("EOF")
        elif isinstance(directive, schema.CopyFile):
            lines.append(f"COPY {directive.source!s} {directive.destination!s}")
        elif isinstance(directive, schema.AptGetInstall):
            lines.append("RUN apt-get update && \\")
            lines.append("    apt-get install -y --no-install-recommends\\")
            for package, is_last in is_last_sentinel(directive.packages):
                if isinstance(package, str):
                    package_str = str(package)
                elif isinstance(package, tuple) and len(package) == 2:
                    package_str = f"{package[0]}={package[1]}"
                else:
                    raise TypeError(
                        f"Unknown package: {type(package).__name__}: {package!r}"
                    )
                lines.append(f"    {package_str} " + ("&& \\" if is_last else "\\"))
            lines.append("    rm -rf /var/lib/apt/lists/*")
        else:
            raise TypeError(
                f"Unknown directive: {type(directive).__name__}: {directive!r}"
            )

        lines.append("")

    return "\n".join(lines)


_T = typing.TypeVar("_T")


def is_last_sentinel(
    it: collections.abc.Iterable[_T],
) -> collections.abc.Iterator[tuple[_T, bool]]:
    elements = list(it)
    for i, element in enumerate(elements):
        if i == len(elements) - 1:
            yield element, True
        else:
            yield element, False
