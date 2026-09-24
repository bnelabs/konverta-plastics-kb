"""Deploy-path tests.

The host timer deploys releases without a human in the loop, so the release
scripts are production code. These tests stub ``gh``, ``docker``, ``git`` and the
MicroK8s kubectl so the real scripts run end to end with no cluster or network.

They cover the two regressions this file exists for:

* ``deploy-release.sh`` must render the manifest for the target version. Applying
  the raw manifest used to set the image to a hardcoded older tag first and only
  then patch it, briefly rolling the Deployment back.
* ``rollback-release.sh`` must withdraw the releases published *after* the target,
  because the timer deploys the newest release every five minutes and otherwise
  re-converges onto the version being rolled back.
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY = REPO_ROOT / "scripts" / "deploy-release.sh"
AUTO = REPO_ROOT / "scripts" / "auto-deploy-release.sh"
ROLLBACK = REPO_ROOT / "scripts" / "rollback-release.sh"

pytestmark = [
    pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required"),
    pytest.mark.skipif(shutil.which("flock") is None, reason="flock is required"),
]

FAKE_GH = r"""
log() { printf '%s\n' "$*" >> "$FAKE_STATE/gh_calls"; }
log "$*"
state="$FAKE_STATE"
if [[ "${1:-}" == "release" ]]; then
  sub="${2:-}"
  case "$sub" in
    view)
      shift 2
      tag=""
      if [[ -n "${1:-}" && "${1}" != --* ]]; then tag="$1"; shift; fi
      if [[ -z "$tag" ]]; then cat "$state/latest_tag"; exit 0; fi
      cat "$state/assets.$tag" 2>/dev/null || true
      exit 0
      ;;
    list)
      cat "$state/releases.tsv"
      exit 0
      ;;
    download)
      tag="$3"; shift 3
      dir=""
      while [[ $# -gt 0 ]]; do
        case "$1" in --dir) dir="$2"; shift 2 ;; *) shift ;; esac
      done
      gzip -c <<< "fake-image-$tag" > "$dir/plastics-kb-${tag#v}.tar.gz"
      exit 0
      ;;
    delete)
      tag="$3"
      printf '%s\n' "$tag" >> "$state/gh_deleted"
      # Model the release disappearing, so "latest" re-points at what remains -
      # this is what the real timer would see on its next poll.
      if [[ -f "$state/releases.tsv" ]]; then
        awk -F'\t' -v t="$tag" '$2 != t' "$state/releases.tsv" > "$state/releases.tsv.tmp"
        mv "$state/releases.tsv.tmp" "$state/releases.tsv"
        sort "$state/releases.tsv" | tail -n1 | cut -f2 > "$state/latest_tag"
      fi
      exit 0
      ;;
  esac
fi
exit 0
"""

FAKE_DOCKER = r"""
printf '%s\n' "$*" >> "$FAKE_STATE/docker_calls"
if [[ "${1:-}" == "load" ]]; then cat > /dev/null; fi
exit 0
"""

FAKE_GIT = r"""
printf '%s\n' "$*" >> "$FAKE_STATE/git_calls"
exit 0
"""

FAKE_KUBECTL = r"""
state="$FAKE_STATE"
printf '%s\n' "$*" >> "$state/kubectl_calls"
if [[ "${1:-}" == "kubectl" ]]; then shift; fi
if [[ "${1:-}" == "-n" ]]; then shift 2; fi
case "${1:-}" in
  get)
    if [[ "${2:-}" == "deployment" ]]; then cat "$state/running_image"; fi
    exit 0
    ;;
  apply)
    shift
    while [[ $# -gt 0 ]]; do
      case "$1" in -f) cp "$2" "$state/applied.yaml"; shift 2 ;; *) shift ;; esac
    done
    exit 0
    ;;
esac
exit 0
"""


class Harness:
    def __init__(self, tmp_path: Path):
        self.state = tmp_path / "state"
        self.bin = tmp_path / "bin"
        self.state.mkdir()
        self.bin.mkdir()
        for name, body in (
            ("gh", FAKE_GH),
            ("docker", FAKE_DOCKER),
            ("git", FAKE_GIT),
            ("microk8s", FAKE_KUBECTL),
        ):
            script = self.bin / name
            script.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")
            script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.set_running("localhost:32000/plastics-kb:0.2.1")
        self.set_latest("v0.3.0")
        self.set_releases(
            ("2026-09-23T15:50:12Z", "v0.1.2"),
            ("2026-09-23T18:32:22Z", "v0.2.1"),
            ("2026-09-23T18:58:54Z", "v0.3.0"),
        )
        for tag in ("v0.1.2", "v0.2.1", "v0.3.0"):
            self.set_assets(tag, f"plastics-kb-{tag[1:]}.tar.gz")

    def set_running(self, image: str) -> None:
        (self.state / "running_image").write_text(image, encoding="utf-8")

    def set_latest(self, tag: str) -> None:
        (self.state / "latest_tag").write_text(tag + "\n", encoding="utf-8")

    def set_assets(self, tag: str, *assets: str) -> None:
        (self.state / f"assets.{tag}").write_text("\n".join(assets) + ("\n" if assets else ""), encoding="utf-8")

    def set_releases(self, *rows) -> None:
        body = "".join(f"{published}\t{tag}\tfalse\n" for published, tag in rows)
        (self.state / "releases.tsv").write_text(body, encoding="utf-8")

    def read(self, name: str) -> str:
        path = self.state / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def run(self, script: Path, *args: str, project: Path = REPO_ROOT, stdin=None):
        env = dict(os.environ)
        env.update(
            PATH=f"{self.bin}{os.pathsep}{env['PATH']}",
            FAKE_STATE=str(self.state),
            KB_STATE=str(self.state),
            KB_REPO="example/konverta-plastics-kb",
            KB_PROJECT_DIR=str(project),
            KB_LOCK_FILE=str(self.state / "release.lock"),
            KUBECTL="microk8s kubectl",
            TMPDIR=str(self.state),
        )
        return subprocess.run(
            ["bash", str(script), *args],
            capture_output=True, text=True, env=env, cwd=str(project),
            stdin=stdin, timeout=120,
        )


@pytest.fixture()
def harness(tmp_path):
    return Harness(tmp_path)


# --- deploy-release.sh --------------------------------------------------------

def test_deploy_renders_the_target_version_into_the_manifest(harness):
    result = harness.run(DEPLOY, "0.3.0")

    assert result.returncode == 0, result.stderr
    applied = harness.read("applied.yaml")
    assert "plastics-kb:0.3.0" in applied, "the applied manifest must name the released image"
    assert "__KB_RELEASE__" not in applied, "the placeholder must be rendered away"
    assert "0.1.2" not in applied, "a stale hardcoded version must never be applied"
    assert applied.count("0.3.0") >= 2, "both the image tag and APP_VERSION must be rendered"

    calls = harness.read("kubectl_calls")
    assert "set image deployment/plastics-kb plastics-kb=localhost:32000/plastics-kb:0.3.0" in calls
    assert "set env deployment/plastics-kb APP_VERSION=0.3.0" in calls
    assert "rollout status" in calls


def test_deploy_refuses_a_manifest_without_the_placeholder(harness, tmp_path):
    project = tmp_path / "project"
    (project / "deploy").mkdir(parents=True)
    manifest = (REPO_ROOT / "deploy" / "k8s.yaml").read_text(encoding="utf-8")
    (project / "deploy" / "k8s.yaml").write_text(
        manifest.replace("__KB_RELEASE__", "0.1.2"), encoding="utf-8")

    result = harness.run(DEPLOY, "0.3.0", project=project)

    assert result.returncode == 2
    assert "placeholder" in result.stderr
    assert harness.read("applied.yaml") == "", "nothing may be applied when the manifest is unsafe"


def test_deploy_rejects_a_non_semver_argument(harness):
    result = harness.run(DEPLOY, "latest")
    assert result.returncode == 2
    assert "Usage" in result.stderr


# --- auto-deploy-release.sh ---------------------------------------------------

def test_auto_deploy_skips_when_the_version_is_already_running(harness):
    harness.set_running("localhost:32000/plastics-kb:0.3.0")
    harness.set_latest("v0.3.0")

    result = harness.run(AUTO)

    assert result.returncode == 0, result.stderr
    assert harness.read("docker_calls") == "", "an already-running version must not be re-imported"
    assert harness.read("applied.yaml") == ""


def test_auto_deploy_skips_when_the_release_has_no_image_asset(harness):
    harness.set_latest("v0.3.0")
    harness.set_assets("v0.3.0")

    result = harness.run(AUTO)

    assert result.returncode == 0, result.stderr
    assert harness.read("docker_calls") == ""
    assert harness.read("applied.yaml") == ""


def test_auto_deploy_skips_when_the_latest_tag_is_not_semver(harness):
    harness.set_latest("nightly")

    result = harness.run(AUTO)

    assert result.returncode == 0, result.stderr
    assert harness.read("docker_calls") == ""


def test_auto_deploy_rolls_forward_to_the_latest_release(harness):
    result = harness.run(AUTO)

    assert result.returncode == 0, result.stderr
    assert "pull --ff-only origin main" in harness.read("git_calls"), "the checkout must be fast-forwarded first"

    docker_calls = harness.read("docker_calls")
    assert "load" in docker_calls
    assert "tag plastics-kb:0.3.0 localhost:32000/plastics-kb:0.3.0" in docker_calls
    assert "push localhost:32000/plastics-kb:0.3.0" in docker_calls
    assert "plastics-kb:0.3.0" in harness.read("applied.yaml")


# --- rollback-release.sh ------------------------------------------------------

def test_rollback_withdraws_only_the_releases_newer_than_the_target(harness):
    result = harness.run(ROLLBACK, "--to", "v0.2.1", "--yes", "--no-deploy")

    assert result.returncode == 0, result.stderr
    assert harness.read("gh_deleted").split() == ["v0.3.0"], "only newer releases may be withdrawn"
    assert "v0.2.1" in result.stdout and "0.2.1" in result.stdout


def test_rollback_refuses_a_target_without_an_image_asset(harness):
    harness.set_assets("v0.2.1")

    result = harness.run(ROLLBACK, "--to", "0.2.1", "--yes")

    assert result.returncode != 0
    assert "asset" in result.stderr
    assert harness.read("gh_deleted") == ""


def test_rollback_refuses_an_unknown_target(harness):
    result = harness.run(ROLLBACK, "--to", "v9.9.9", "--yes")
    assert result.returncode != 0
    assert "not found" in result.stderr
    assert harness.read("gh_deleted") == ""


def test_rollback_converges_onto_the_target_when_asked(harness):
    # Realistic rollback: 0.3.0 is running and we want 0.2.1 again.
    harness.set_running("localhost:32000/plastics-kb:0.3.0")

    result = harness.run(ROLLBACK, "--to", "v0.2.1", "--yes")

    assert result.returncode == 0, result.stderr
    assert harness.read("gh_deleted").split() == ["v0.3.0"]
    assert "plastics-kb:0.2.1" in harness.read("applied.yaml")
    assert "push localhost:32000/plastics-kb:0.2.1" in harness.read("docker_calls")


def test_rollback_withdraws_newer_releases_even_when_already_on_the_target(harness):
    # The withdrawal is what makes the rollback stick; it must happen regardless of
    # which version happens to be running, and it must not re-deploy needlessly.
    harness.set_running("localhost:32000/plastics-kb:0.2.1")

    result = harness.run(ROLLBACK, "--to", "v0.2.1", "--yes")

    assert result.returncode == 0, result.stderr
    assert harness.read("gh_deleted").split() == ["v0.3.0"]
    assert harness.read("docker_calls") == "", "nothing to re-import when the target already runs"


def test_rollback_requires_confirmation_without_yes(harness):
    # No --yes and no TTY: the script must refuse rather than delete releases.
    result = harness.run(ROLLBACK, "--to", "v0.2.1", stdin=subprocess.DEVNULL)

    assert result.returncode != 0
    assert "confirmation" in result.stderr
    assert harness.read("gh_deleted") == "", "nothing may be withdrawn without confirmation"


def test_rollback_list_reports_the_running_version(harness):
    result = harness.run(ROLLBACK, "--list")

    assert result.returncode == 0, result.stderr
    assert "0.2.1" in result.stdout, "the running image must be reported"
    for tag in ("v0.1.2", "v0.2.1", "v0.3.0"):
        assert tag in result.stdout
    assert harness.read("gh_deleted") == ""
