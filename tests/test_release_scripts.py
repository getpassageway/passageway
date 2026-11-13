import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
pytestmark = pytest.mark.skipif(not shutil.which("jq"), reason="the release scripts need jq")


def run(script, *args, cwd=ROOT, env=None):
    return subprocess.run(["bash", str(SCRIPTS / script), *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def project_version():
    import tomllib
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


# ---- check-version.sh ---------------------------------------------------------------------------

def test_a_tag_that_matches_pyproject_passes():
    assert run("check-version.sh", f"v{project_version()}").returncode == 0


def test_a_tag_that_differs_from_pyproject_fails_with_both_versions_in_the_message():
    done = run("check-version.sh", "v99.0.0")
    assert done.returncode != 0 and "99.0.0" in done.stderr and project_version() in done.stderr


@pytest.mark.parametrize("tag", ["1.0.0", "v1", "v1.0.0; rm -rf /", "v1.0.0 extra", "main", ""])
def test_a_malformed_tag_is_refused(tag):
    assert run("check-version.sh", tag).returncode != 0


PACKAGE_FILES = sorted(str(p.relative_to(ROOT)) for pattern in ("connectors/*/pyproject.toml", "embedders/*/pyproject.toml")
                       for p in ROOT.glob(pattern)) + ["sdk/pyproject.toml"]
PUBLISH_DIRS = [d.rsplit("/pyproject.toml", 1)[0] for d in PACKAGE_FILES]
VERSION_FILES = ["pyproject.toml", ".claude-plugin/plugin.json", "skills/passageway/SKILL.md", *PACKAGE_FILES]


def copy_version_files(dst):
    for name in VERSION_FILES:
        (dst / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, dst / name)


@pytest.mark.parametrize("name", PACKAGE_FILES)
def test_every_package_version_equals_the_root_version(name):
    import tomllib
    assert tomllib.loads((ROOT / name).read_text())["project"]["version"] == project_version(), name


def test_a_connector_with_another_version_fails_naming_its_file(tmp_path):
    copy_version_files(tmp_path)
    assert run("bump-version.sh", "9.9.9", cwd=tmp_path).returncode == 0
    path = tmp_path / "connectors/wikipedia/pyproject.toml"
    path.write_text(path.read_text().replace('version = "9.9.9"', 'version = "0.0.1"'))
    done = run("check-version.sh", "v9.9.9", cwd=tmp_path)
    assert done.returncode != 0 and "connectors/wikipedia/pyproject.toml" in done.stderr


def test_bump_version_moves_every_file_and_check_version_agrees(tmp_path):
    copy_version_files(tmp_path)
    assert run("bump-version.sh", "9.9.9", cwd=tmp_path).returncode == 0
    done = run("check-version.sh", "v9.9.9", cwd=tmp_path)
    assert done.returncode == 0, done.stderr


def test_bump_version_moves_every_pin_between_the_packages_whatever_the_extras(tmp_path):
    # a stale `passageway-sdk[web,html]~=0.3.0` refuses SDK 0.4.0, and the connector cannot be installed
    copy_version_files(tmp_path)
    assert run("bump-version.sh", "9.9.9", cwd=tmp_path).returncode == 0
    pins = [(name, pin) for name in ["pyproject.toml", *PACKAGE_FILES]
            for pin in re.findall(r'"(passageway-[a-z-]+(?:\[[a-z,]+\])?\s*[~=]=[^"]*)"', (tmp_path / name).read_text())]
    assert pins and all(pin.endswith("=9.9.9") for _, pin in pins), [p for p in pins if not p[1].endswith("=9.9.9")]


@pytest.mark.parametrize("version", ["v1.0.0", "1.0", "1.0.0; x", ""])
def test_bump_version_refuses_a_malformed_version(version, tmp_path):
    copy_version_files(tmp_path)
    assert run("bump-version.sh", version, cwd=tmp_path).returncode != 0


# ---- release-notes.sh ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    """A git repo with one annotated tag, and a fake `gh` that answers the release-notes API call."""
    git = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, text=True)  # noqa: E731
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.org")
    git("config", "user.name", "T")
    (tmp_path / "f").write_text("x")
    git("add", "f")
    git("commit", "-q", "-m", "Merge pull request #9 from someone/branch")
    git("tag", "-a", "v1.2.3", "-m", "The headline of this release.\n\nA second paragraph.")
    git("tag", "v1.2.4")  # lightweight: no message of its own
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$@" >> "$GH_LOG"\n'
        "cat <<'BODY'\n"
        "## What's Changed\n"
        "* Something merged in https://example.org/pull/1\n"
        "\n"
        "**Full Changelog**: https://example.org/compare\n"
        "BODY\n")
    fake.chmod(0o755)
    return tmp_path, {"PATH": f"{bin_dir}:{os.environ['PATH']}", "GH_LOG": str(tmp_path / "gh.log"),
                      "GITHUB_REPOSITORY": "getpassageway/passageway", "GH_TOKEN": "x"}


def test_release_notes_have_the_tag_message_the_merged_prs_and_install_instructions(repo):
    cwd, env = repo
    out = run("release-notes.sh", "v1.2.3", cwd=cwd, env=env)
    assert out.returncode == 0, out.stderr
    notes = out.stdout
    assert notes.startswith("The headline of this release.")
    assert "A second paragraph." in notes
    assert "Something merged" in notes and "Full Changelog" in notes
    assert 'uv tool install --python 3.14 "passageway[wikipedia]==1.2.3"' in notes
    assert "git+https" not in notes
    assert "https://getpassageway.com" in notes


def test_a_lightweight_tag_gets_no_borrowed_commit_message(repo):
    cwd, env = repo
    notes = run("release-notes.sh", "v1.2.4", cwd=cwd, env=env).stdout
    assert "Merge pull request" not in notes and notes.lstrip().startswith("## What")


def test_the_previous_tag_bounds_the_generated_list(repo):
    cwd, env = repo
    run("release-notes.sh", "v1.2.4", cwd=cwd, env=env)
    assert "previous_tag_name=v1.2.3" in (cwd / "gh.log").read_text()


def test_pre_release_and_stray_tags_never_become_the_previous_release(repo):
    cwd, env = repo
    git = lambda *a: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)  # noqa: E731
    git("tag", "v1.2.4-rc1")
    git("tag", "vendor-sync")
    git("tag", "-a", "v1.2.5", "-m", "next")
    run("release-notes.sh", "v1.2.5", cwd=cwd, env=env)
    assert "previous_tag_name=v1.2.4 " in (cwd / "gh.log").read_text() + " "


def test_the_first_release_has_no_previous_tag(tmp_path):
    git = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, text=True)  # noqa: E731
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.org")
    git("config", "user.name", "T")
    (tmp_path / "f").write_text("x")
    git("add", "f")
    git("commit", "-q", "-m", "first")
    git("tag", "-a", "v0.1.0", "-m", "First release.")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text('#!/usr/bin/env bash\necho "$@" >> "$GH_LOG"\necho "## What\'s Changed"\n')
    (bin_dir / "gh").chmod(0o755)
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "GH_LOG": str(tmp_path / "gh.log"),
           "GITHUB_REPOSITORY": "getpassageway/passageway"}
    done = run("release-notes.sh", "v0.1.0", cwd=tmp_path, env=env)
    assert done.returncode == 0 and "previous_tag_name" not in (tmp_path / "gh.log").read_text()


def test_an_empty_tag_message_adds_no_leading_blank_lines(repo):
    cwd, env = repo
    subprocess.run(["git", "tag", "-a", "v1.2.9", "-m", ""], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_EDITOR": "true"})
    notes = run("release-notes.sh", "v1.2.9", cwd=cwd, env=env).stdout
    assert notes.startswith("## What")


def test_a_tag_that_does_not_exist_fails_clearly_before_calling_github(repo):
    cwd, env = repo
    done = run("release-notes.sh", "v9.9.9", cwd=cwd, env=env)
    assert done.returncode != 0 and "no such tag" in done.stderr
    assert not (cwd / "gh.log").exists()


# ---- the workflow -------------------------------------------------------------------------------

def test_the_release_workflow_calls_only_scripts_that_exist():
    import re

    import yaml

    text = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    workflow = yaml.safe_load(text)
    assert workflow[True]["push"]["tags"] == ["v*"]  # PyYAML reads the key `on` as True
    for script in set(re.findall(r"scripts/[\w.-]+\.sh", text)):
        path = ROOT / script
        assert path.is_file() and os.access(path, os.X_OK), f"{script} is called by the workflow but is not executable"
    assert "contents: write" in text
    # a user-supplied tag must never be interpolated into a shell command
    for step in workflow["jobs"]["release"]["steps"]:
        assert "inputs.tag" not in step.get("run", ""), "inputs.tag must go through the environment"
    # the tag is validated before any other step sees it
    first_run = next(step["run"] for step in workflow["jobs"]["release"]["steps"] if "run" in step)
    assert "check-version.sh" in first_run, "scripts/check-version.sh must be the first run step"


def test_the_release_workflow_publishes_every_package_in_order_without_a_credential_on_the_command_line():
    import re

    import yaml

    text = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    job = yaml.safe_load(text)["jobs"]["publish"]
    assert "release" in job["needs"] if isinstance(job["needs"], list) else job["needs"] == "release"
    environment = job["environment"]
    assert (environment["name"] if isinstance(environment, dict) else environment) == "pypi"
    assert job["permissions"]["id-token"] == "write"
    steps = "\n".join(step.get("run", "") for step in job["steps"])
    # trusted publishing alone: no token, neither as an argument nor from a secret (#28)
    assert not re.search(r"--token|--password", json.dumps(job)), "a credential must not be an argument"
    assert "secrets." not in json.dumps(job) and "UV_PUBLISH_TOKEN" not in text, "publishing needs no stored token"
    assert "uv build --all-packages" in steps
    publish = re.findall(r"uv publish[^\n]*", steps)
    assert len(publish) == 1 and "--check-url" in publish[0] and "--trusted-publishing always" in publish[0]
    order = re.search(r'packages="([^"]+)"', steps).group(1).split()
    import tomllib
    names = [tomllib.loads((ROOT / d / "pyproject.toml").read_text())["project"]["name"]
             for d in PUBLISH_DIRS]
    assert order[0] == "passageway-sdk" and order[-1] == "passageway" and sorted(order) == sorted([*names, "passageway"])


def test_the_publish_step_checks_every_file_exists_before_uploading_anything():
    import yaml

    steps = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text())["jobs"]["publish"]["steps"]
    publish = next(step["run"] for step in steps if "uv publish" in step.get("run", ""))
    # an old tag re-run through workflow_dispatch builds an old tree: refuse before the first upload, never half-publish
    assert "compgen" in publish and publish.index("compgen") < publish.index("uv publish")
