# Development

```bash
git clone https://github.com/getpassageway/passageway
cd passageway
uv sync                # installs the core and every connector package
uv run pytest -q       # the whole suite, offline
```

## Layout

The repository is a uv workspace: the core package `passageway` at the root and one self-contained package per connector under `connectors/`, each with its own `pyproject.toml`, tests and README. See [ADR 0002](adr/0002-connectors-as-workspace-packages.md).

## Tests

- `uv run pytest -q` runs everything offline. Connector tests run the connector as a real subprocess against an in-test server and through `passageway.testing.contract.check_connector`.
- `corpus/` holds the frozen sample corpus, `corpus/snapshot.py` (the script that writes it), `corpus/questions.toml` (the 100 questions) and `corpus/measure.sh` (runs them and updates [Measurements](measurements.md), which needs the embedding model); its tests run offline against the Wikipedia connector's fake MediaWiki and check the committed files ([Sample corpus](reference/corpus.md)).
- Opt-in live tests hit real services: `PASSAGEWAY_LIVE=1 uv run pytest connectors/wikipedia/tests/test_wikipedia_live.py`.
- `tests/test_docs.py` keeps these docs honest: it fails when a setting is added to the code without being documented, and it runs the example connector from the guide.

## Docs

```bash
uvx --with mkdocs-material==9.7.7 --with mkdocs-llmstxt==0.5.1 --with 'mkdocs<2' mkdocs serve           # live preview
uvx --with mkdocs-material==9.7.7 --with mkdocs-llmstxt==0.5.1 --with 'mkdocs<2' mkdocs build --strict   # what CI runs
```

The Roadmap page is rendered from `docs/roadmap.yml` by a small MkDocs hook (`docs_hooks/roadmap.py`), so adding or finishing a step is one entry in that file; `mkdocs serve` rebuilds the page when the file changes. Its icons are Material Design icons, named in the file.

The header bar has two extra links for AI agents (`SKILL.md` and `llms-full.txt`). Material has no setting for that, so `overrides/partials/header.html` is a copy of Material's own header template with one block added. When you change the pinned Material version, copy the new `header.html` from the package and re-add the block; a test fails if the version in the copy and the pinned one differ.

## Changes

Every change starts from an issue and goes through a pull request; the CI build must pass, including the strict docs build. The Checks workflow has four jobs, the test suite, the docs build, the plugin (`claude plugin validate .` and the hook's self-test) and the sidecar image, and a `changes` job in front that runs each only when a file it reads changed: a skill does not build the image, a Dockerfile does not build the docs. Run the same gates locally before a push: `uv run pytest -q`, the docs build above, `claude plugin validate .`. Decisions that future contributors will ask about get an ADR in `docs/adr/`.

Dependabot keeps the dependencies and the GitHub Actions current (`.github/dependabot.yml`): security updates arrive at once; everything else waits two weeks after a release and comes grouped on Monday mornings, with the `Dependencies:` prefix instead of an issue number. Patch and minor bumps merge by themselves once the required checks are green; majors wait for review. A scheduled audit (`.github/workflows/audit.yml`) checks the locked runtime dependencies for known vulnerabilities every day.

## Releasing

A release is a tag. Run `scripts/bump-version.sh X.Y.Z` and `uv lock`, merge the result, then tag the commit. The script moves the version of the core, the SDK, every connector and the embedder together, with the plugin manifest, the general skill and the pins between the packages: they all carry the tag's version.

```bash
git tag -a v0.2.0 -m "A one-line headline for the release"
git push origin v0.2.0
```

The `Release` workflow checks that the tag equals the version in `pyproject.toml`, runs the tests, and creates the GitHub release. Its notes are the tag message, the pull requests merged since the previous release, and install instructions. The `publish` job then builds every package and uploads them to PyPI, the SDK first and the core last, skipping what is already there, so running it again after a failure carries on. It refuses before the first upload if a package's files are missing. A published version can only be yanked, never replaced. It authenticates by trusted publishing, so no token is stored anywhere.

To publish an existing tag again, run the workflow by hand from the Actions tab and give it the tag. This rewrites the release notes, so edits made by hand on GitHub are lost. The check compares the tag with the root `pyproject.toml` and with every package.

Each project on PyPI (`passageway`, `passageway-sdk`, every `passageway-connector-*` and `passageway-embedder-openai`) has a trusted publisher: repository `getpassageway/passageway`, workflow `release.yml`, environment `pypi` (the environment exists on GitHub). A new package needs a pending publisher with the same three values on pypi.org before the release that first uploads it. PyPI creates at most four new projects per account in 24 hours; a release that adds more fails with `429 Too many new projects created`, and running the publish job again a day later carries on.
