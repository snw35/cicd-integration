import json
import re
import shlex
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


def load_expected_version(version_file: str) -> str:
    expected = Path(version_file).read_text().strip()
    if not expected:
        fail(f"{version_file}: expected version is empty")
    return expected


def parse_effective_env_value(dockerfile: str, env_key: str) -> str:
    occurrences: list[tuple[int, str]] = []
    for line_no, raw in enumerate(Path(dockerfile).read_text().splitlines(), start=1):
        line = raw.strip()
        tokens = [""]
        if not line or line.startswith("#"):
            continue
        match = re.match(r"(?i)^ENV\s+(.*)$", line)
        if not match:
            continue
        payload = match.group(1).strip()
        if not payload:
            continue
        try:
            tokens = shlex.split(payload, posix=True)
        except ValueError as exc:
            fail(f"{dockerfile}:{line_no}: unable to parse ENV statement: {exc}")
        if not tokens:
            continue

        if "=" not in tokens[0]:
            key = tokens[0]
            value = " ".join(tokens[1:]).strip()
            if key == env_key:
                occurrences.append((line_no, value))
            continue

        for token in tokens:
            if "=" not in token:
                fail(
                    f"{dockerfile}:{line_no}: mixed ENV assignment form encountered near '{token}'"
                )
            key, value = token.split("=", 1)
            if key == env_key:
                occurrences.append((line_no, value))

    if not occurrences:
        fail(f"{dockerfile}: {env_key} not found in ENV assignments")

    return occurrences[-1][1]


def extract_oldver_version(oldver_file: str, json_key: str) -> str:
    data = json.loads(Path(oldver_file).read_text())
    if not isinstance(data, dict):
        fail(f"{oldver_file}: top-level JSON must be an object")
        return ""

    direct = data.get(json_key)
    if isinstance(direct, dict) and direct.get("version") is not None:
        return str(direct["version"])

    nested = data.get("data")
    if isinstance(nested, dict):
        nested_target = nested.get(json_key)
        if isinstance(nested_target, dict) and nested_target.get("version") is not None:
            return str(nested_target["version"])

    fail(
        f"{oldver_file}: {json_key}.version not found "
        f"(checked both top-level and data.{json_key})"
    )
    return ""


def verify_target(
    *,
    target_label: str,
    version_file: str,
    dockerfile: str,
    env_key: str,
    oldver_file: str,
    json_key: str,
) -> None:
    expected = load_expected_version(version_file)
    docker_actual = parse_effective_env_value(dockerfile, env_key)
    if docker_actual != expected:
        fail(
            f"{target_label}: {dockerfile} {env_key} mismatch: "
            f"actual={docker_actual!r} expected={expected!r}"
        )

    oldver_actual = extract_oldver_version(oldver_file, json_key)
    if oldver_actual != expected:
        fail(
            f"{target_label}: {oldver_file} {json_key}.version mismatch: "
            f"actual={oldver_actual!r} expected={expected!r}"
        )


def main() -> None:
    verify_target(
        target_label="root target",
        version_file="version.txt",
        dockerfile="Dockerfile",
        env_key="SAMPLE_VERSION",
        oldver_file="old_ver.json",
        json_key="SAMPLE",
    )

    verify_target(
        target_label="secondary target",
        version_file="secondary/version.txt",
        dockerfile="secondary/Dockerfile",
        env_key="SECONDARY_VERSION",
        oldver_file="secondary/old_ver.json",
        json_key="SECONDARY",
    )

    print("Verified updated versions for root and secondary targets.")


if __name__ == "__main__":
    main()
