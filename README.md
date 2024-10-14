# Running

If you don't like Nix, use Docker (most students should do this one):

``` sh
docker run -it --rm -v $PWD:$PWD -w $PWD ghcr.io/charmoniumq/mp2-validator:0.1.9 validate bibcode.yaml
```

If you don't like Docker, use Nix:

``` sh
nix run github:uiuc-cs527-fa24/mp2-validator/0.1.9 -- validate bibcode.yaml
```

Whichever method, you have the following subcommands:

- ``` sh
  validate bibcode.yaml
  ```

- ``` sh
  export-dockerfile bibcode.yaml
  ```

## About the new schema

For any confusion, consult [`schema.py`](./schema.py), which has as [Pydantic schema](https://pydantic.dev/) and _lots_ of doc-strings comments. If you have trouble reading or understanding it, please consult me. There is an example of correct and incorrect Articles [here](./test_cases).

I changed the schema because:

- The old one had a set of boolean rules (e.g., if this field is present, that one should/shouldn't be). The new one is more correct-by-construction. E.g., if an article is build-crashing, add the object `BuildCrash`, rather than setting crash-specific fields on the parent.

- The old one had some confusingly named field (and probably incorrect data as a result!). For example, it was ambiguous to which link `before_live` referred to. Now, the lifetime attributes are associated with a link, not at the top-level.

- The old one was harder to parse for automated analyses.

- The new schema will be a single file most of the time.

Here are some differences between schema in MP2 and the ongoing reproducibility data-collection:

- The original dataset did not hold the full [DBLP](https://dblp.org) key; they just kept the last fragment. We will need the full key to look up articles in DBLP, so please help us by finding the _full_ key for each article. See doc-string for more details.

- Some of the articles don't have source because their result is non-computational. These articles should be excluded from the "open-source vs closed-source" ratio (since they have no source at all), therefore they must be labelled as such in the field `compuatational_status`. See the doc-string for process and details.

- See the doc-string in `source_search` for the procedure for searing for source. Unlike MP2, we will accept binary artifacts, if there is no source code alternative.

- The doc-string for `path` (in `SourceFound`) describes the process for that.

- Archive.org has been down recently. You may skip the `born_after`, `earliest_alive_on` for all links (alive or dead) and skip `latest_alive_on` for dead links, until it comes back up in the middle/beginning of a progress report cycle.

- I slightly changed the interpretation for `latest_alive_on`:

  - For dead links, this will come from Archive.org, like in MP2, which is currently down, so it can be omitted.

  - For live links, this should be set to today. This is a slight departure from the interpretation of `latest_alive_on` in MP2.

- Dead links should also set `dead_on` to today (or earlier, if Archive.org comes back up).

- `Dockerfile`, `docker_build_output.txt`, and `problem.md` should be _entered into the YAML file directly_ in `build_directives`/`test_directives`, `BuildCrash.crashing_command_output`, and `BuildCrash.description` respectively. Files copied into the Docker container should be included as strings if they are smaller than 1KiB and included by path if they are larger. This means that most of the times, you only have _one_ (1) file for each article, named the bibcode + `.yaml`. Single-file should make many operations  more convenient.

## Dockerfile Directives

You should still develop the `Dockerfile` iteratively, like usual, but when you are done, the commands should be entered in a structured format. E.g.,

```bash
RUN PATH=/opt/bin make foobar && \
  echo hello > world && \
  cat /foobar | grep barbaz
```

should be turned into:

```yaml
- type: RUN
  specific_env_vars:
    PATH: /opt/bin
  cmds:
    # These commands get `&&` together.

    # If there is no "special" shell syntax, just write the command as a list element.
    - make foobar

    # notice how we have to be more verbose for "special" shell syntaxes, like redirection.
    # We need to set `args` explicitly, along with any extra attributes.
    # See Command in schema.py for more details.
    - args: echo hello
      redirect_stdout: world

    # notice how `cmd0 | cmd1` can be rewritten `cmd0 > tmp && cmd1 < tmp`.
    - args: cat /foobar
      redirect_stdout: tmp
    - args: grep barbaz
      redirect_stdin: tmp
```

You may always use `type: Raw RUN` as an escape hatch, if the structured format does not support some shell syntax (subshell, logical OR (except `cmd || true` is specifically supported)).

  ```yaml

  - type: Raw RUN
    cmds: |
      (arbitrary commands | not=supported) && by structured || cmd
  ```

There is also a special syntax for apt-get install. Previously, each student did this operation slightly differently. This will reduce the repeated code across Dockerfiles, increase analyzability, and enforce best practices:

```yaml
- type: apt-get install
  packages:
    - gcc
    - cmake
```

Once you have the Dockerfile translated into a structured YAML format, you can use `export-dockerfile` to get an unstructured `Dockerfile` back out. Make sure the exported Dockerfile still builds.

Finally, logically related commands should be grouped into as single RUN, and a single RUN should only hold logically related commands. I.e., one library's download, configure, build, install should be combined into one `RUN`. I will help with this during the review process.

Note: there is no equivalent of `WORKDIR`. Simply `cd` at the beginning of your `RUN` or use `env --chdir $dir $cmd...`.
