# passageway

Retrieval for Claude over MCP: connectors (out-of-process programs speaking JSON Lines) feed passages to a core that indexes and ranks them. Documentation: https://getpassageway.com/ (the pages are in `docs/`).

## Commands

```bash
uv sync                                   # the core and every connector package
uv run pytest -q                          # the whole suite, offline
uvx --with mkdocs-material==9.7.7 --with mkdocs-llmstxt==0.5.1 --with 'mkdocs<2' mkdocs build --strict   # the docs, as CI builds them
PASSAGEWAY_LIVE=1 uv run pytest connectors/wikipedia/tests/test_wikipedia_live.py   # opt-in, hits Wikipedia
```

## Working in this repository

- Every change is judged against `docs/values.md`, what passageway stands for; a review names the point it touches ("this breaks V2"). A change to that page needs my approval and says why.
- Every change starts from an issue. Branches, commits and pull request titles carry `PASSAGEWAY #<issue>:` (the `/ccp:ship-pr` flow). Dependabot's carry `Dependencies:` instead.
- Tests first: write the failing test, watch it fail, then the code. `tests/test_docs.py` keeps the docs in step with the code.
- CI is the gate, and I decide when a branch is finished and when it is merged. A `/ccp:ship-pr` request is the go-ahead for push and PR only, not for the merge. Merge only when I say "merge". The one exception: Dependabot's patch and minor bumps merge by themselves once CI is green (`.github/workflows/dependabot-automerge.yml`); its majors wait for me like any other PR.
- Every HTTPS client verifies against the operating system's trust store: `verify=` (httpx) or `context=` (urllib) is `truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)`, and `tests/test_trust.py` lists the client.
- Never print or write a secret into a file, a log or a commit. Credentials live in 1Password; GitHub secrets are set by piping from there.

## Roadmap

The plan for where passageway is going, and for how trilium-recall folds into it, is `docs/roadmap.yml`, rendered as the timeline on the Roadmap page (`docs/roadmap.md`, `docs_hooks/roadmap.py`). Keep it true: mark a step done in the pull request that finishes it, and change the file in the pull request that changes the plan.

## Releases

A `vX.Y.Z` tag is a release and must equal the version in `pyproject.toml`. The Release workflow creates the GitHub release; see `docs/development.md`.
