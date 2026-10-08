"""Assert the release/image outcome of an integration scenario at HEAD.

Usage: verify_release.py name | main|dependency|handfix

`name` prints the release/tag name of the Dockerfiles at HEAD: the targets' image
tags (main version only, folder prefix for secondary) joined in workdir order.

For every scenario: both targets have their image tag on Docker Hub and ghcr
with equal digests and the revision label, and a GitHub release for the name
exists whose body carries the state marker of HEAD (a freshly built state).
* main: a main version changed, so the git tag is new and sits at HEAD.
* dependency, handfix: the release for that main version existed before (the
  scenario seeds it): its git tag is untouched, i.e. still at the seed commit,
  and no other tag appears; only the release body was refreshed.
* handfix: additionally the nvchecker/dfupdate steps of the run were skipped.

Environment: GITHUB_REPOSITORY, GH_TOKEN, RUN_ID (run to inspect, handfix).
"""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

TARGETS = [
    # (dockerfile, main ENV, folder prefix)
    ("Dockerfile", "SAMPLE_VERSION", ""),
    ("secondary/Dockerfile", "SECONDARY_VERSION", "secondary-"),
]


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def run(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def read_dockerfile(path: str) -> tuple[dict, str]:
    """Return (ENV values, last FROM tag); a repeated ENV key keeps its first position."""
    envs: dict[str, str] = {}
    base = ""
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        match = re.match(r"(?i)^FROM\s+(\S+)", line)
        if match:
            image = match.group(1).split("@", 1)[0]
            base = (
                image.rsplit(":", 1)[1] if ":" in image.rsplit("/", 1)[-1] else "latest"
            )
            continue
        match = re.match(r"(?i)^ENV\s+(.*)$", line)
        if not match:
            continue
        tokens = shlex.split(match.group(1))
        if tokens and "=" not in tokens[0]:
            envs[tokens[0]] = " ".join(tokens[1:])
        else:
            for token in tokens:
                key, value = token.split("=", 1)
                envs[key] = value
    return envs, base


def image_tag(dockerfile: str, main: str, prefix: str) -> str:
    envs, _ = read_dockerfile(dockerfile)
    return prefix + re.sub(r"[^A-Za-z0-9._-]", "-", envs[main])


def digest(ref: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            ref,
            "--format",
            "{{.Manifest.Digest}}",
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def has_label(ref: str) -> bool:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{json .Image}}"],
        capture_output=True,
        text=True,
    )
    return "org.opencontainers.image.revision" in result.stdout


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "main"
    tags = [image_tag(*target) for target in TARGETS]
    name = "-".join(tags)
    if mode == "name":
        print(name)
        return
    repo = os.environ["GITHUB_REPOSITORY"]
    head = run("git", "rev-parse", "HEAD").strip()

    body = run("gh", "release", "view", name, "--json", "body", "--jq", ".body")
    if f"<!-- cicd-state-sha: {head} -->" not in body:
        fail(f"release {name} body does not carry the state marker of HEAD {head}")
    print(f"ok: release {name} describes HEAD")

    tag_commit = run("git", "rev-parse", f"{name}^{{commit}}").strip()
    at_head = run("git", "tag", "--points-at", "HEAD").split()
    if mode == "main":
        if tag_commit != head:
            fail(f"tag {name} is at {tag_commit}, expected HEAD {head}")
        print(f"ok: new tag {name} at HEAD")
    else:
        if tag_commit == head or at_head:
            fail(f"tag moved or created at HEAD (tag {name} at {tag_commit}, at HEAD: {at_head})")
        print(f"ok: tag {name} stayed at {tag_commit}; no tag at HEAD")

    for tag in tags:
        digests = []
        for registry in ("", "ghcr.io/"):
            ref = f"{registry}{repo}:{tag}"
            digests.append(digest(ref))
            if not digests[-1]:
                fail(f"{ref} is missing")
            if not has_label(ref):
                fail(f"{ref} has no revision label")
        if digests[0] != digests[1]:
            fail(f"{repo}:{tag} differs between Docker Hub and ghcr: {digests}")
        if digests[0] not in body:
            fail(f"release {name} body does not list the digest {digests[0]} of {tag}")
        print(f"ok: {repo}:{tag} on both registries ({digests[0]})")

    if mode == "handfix":
        jq = (
            '.jobs[].steps[]? | select(.name == "Run nvchecker" or '
            '.name == "Run dfupdate") | .conclusion'
        )
        conclusions = run(
            "gh",
            "api",
            "--paginate",
            f"repos/{repo}/actions/runs/{os.environ['RUN_ID']}/jobs",
            "--jq",
            jq,
        ).split()
        if any(c != "skipped" for c in conclusions):
            fail(f"nvchecker/dfupdate ran in publish mode: {conclusions}")
        if not conclusions:
            print("warning: no nvchecker/dfupdate steps visible in the jobs API")
        else:
            print(f"ok: nvchecker/dfupdate steps skipped ({len(conclusions)})")


if __name__ == "__main__":
    main()
