# cicd integration test

This repository exercises reusable workflows from `snw35/cicd` as an end-to-end
GitHub Actions integration test. It validates multi-target update flows,
container metadata refresh, compose validation, and post-run repository reset to
keep the default branch in a known baseline state.

## Repository layout

- `Dockerfile`: root target image with `SAMPLE_VERSION` and duplicate `ENV`
  keys to test `dfupdate` behavior.
- `nvchecker.toml`, `old_ver.json`, `version.txt`: root target update inputs.
- `secondary/Dockerfile`: secondary target image with `SECONDARY_VERSION` and
  duplicate `ENV` keys.
- `secondary/nvchecker.toml`, `secondary/old_ver.json`, `secondary/version.txt`:
  secondary target update inputs.
- `docker-compose.yaml`: compose stack used by reusable workflow validation.
- `.github/workflows/integration-update.yaml`: scheduled/dispatch update job
  that calls the shared `container-update.yaml` workflow.
- `.github/actionlint.yaml`: tolerates the `concurrency.queue` key that
  actionlint does not know yet.
- `.github/workflows/scenario.yaml`: prepares `main` for a scenario
  (`main`, `dependency`, `handfix`) and starts it.
- `.github/workflows/verify-reset.yaml`: asserts the scenario outcome (versions,
  release/tag, images), deletes run-created release/tags, and force-resets to
  baseline.
- `.github/scripts/verify_release.py`: release/tag/image assertions used by
  `verify-reset`.

## What this integration test covers

- Multi-target workflow dispatch/update through the shared `container-update.yaml`
  workflow's workdir matrix (root + secondary).
- `nvchecker` + `dfupdate` processing for Dockerfiles containing:
  - multiple `ENV` declarations,
  - duplicate keys where last assignment is the effective value.
- Compose validation path in reusable workflow using the local image tag through
  `docker-compose.yaml`.
- Moving image tags named by the main version only (Docker Hub and ghcr, equal
  digests), the combined git tag/release `<root tag>-secondary-<secondary tag>`
  (created only when a main version changes; dependency-only bumps refresh the
  release body), and publish mode (a push
  to `main` re-publishes the committed Dockerfile without nvchecker/dfupdate).

## Setup

Configure secrets:

- `DOCKER_PASSWORD`: Docker Hub password or access token for
  `$GITHUB_REPOSITORY_OWNER`.

Optional repository variables:

- `CICD_REF`: override the ref used for `snw35/cicd` workflows/helper scripts.
- `BASELINE_REF`: override the baseline tag or branch name (default:
  `baseline`).

Cross-repo PR integration note:

- `snw35/cicd` dispatches this workflow on an ephemeral branch and rewrites this
  workflow's `container-update.yaml` ref to the `cicd` PR SHA before dispatch.
  The release job runs only on `main`, so PR integration does not execute
  `create-release.yaml`; the scenarios do.
- The token used in `snw35/cicd` (`CICD_INTEGRATION_TOKEN`) needs least-
  privilege fine-grained PAT permissions on this repository:
  - **Actions: Read and write** (dispatch + workflow run polling)
  - **Contents: Read and write** (ephemeral branch ref and workflow file rewrite)

## Workflow example

The integration update workflow calls the shared `container-update.yaml`
workflow (the same thin shape the consumer repos use) with a two-workdir matrix:

```yaml
jobs:
  container-update:
    concurrency:
      group: ${{ github.event_name == 'pull_request' && format('pr-{0}', github.run_id) || format('container-update-{0}', github.repository) }}
      queue: max
      cancel-in-progress: false
    permissions:
      contents: write
      packages: write
    uses: snw35/cicd/.github/workflows/container-update.yaml@main
    with:
      WORKDIRS: '[".","secondary"]'
      IMAGE_TAG: SAMPLE_VERSION
      IMAGE_TAG_BY_WORKDIR: '{"secondary":"SECONDARY_VERSION"}'
      CICD_REF: ${{ inputs.cicd_ref || vars.CICD_REF || 'main' }}
      RUN_AUTOMATED_UPDATE_ON_PR: ${{ github.event_name == 'pull_request' }}
    secrets: inherit
```

## Scenarios

Run **Integration Scenario** (`gh workflow run scenario.yaml -R snw35/cicd-integration -f scenario=<name>`):

| Scenario | What it does | `verify-reset` asserts |
|---|---|---|
| `main` | baseline as is: stale main versions + base bump; starts the update run | versions updated; new git tag `<root tag>-secondary-<secondary tag>` at HEAD + release whose body marks HEAD; image tags (main version only) have equal digests on both registries and carry the revision label |
| `dependency` | makes the main versions current so only the base image bumps; first seeds a tag + release for that version | the seeded tag did not move, no tag at HEAD, the release body was refreshed to mark HEAD; images as above |
| `handfix` | seeds a tag + release, then pushes a Dockerfile comment edit (publish mode, push event) | same as `dependency`, plus nvchecker/dfupdate steps skipped |

The daily cron runs the `main` shape. Run the scenarios one after another; each
ends with the reset to `baseline`. Not automated (check by hand when changing
the matrix/release logic): two quick dispatches queue FIFO; a second run leaves
the tag SHA unchanged; one failing leg commits the other leg and creates no tag.

## Verification and reset behavior

After a successful run on the default branch (schedule, dispatch or hand-fix
push; PR runs are ignored), `verify-reset` requires that the default branch
changed since the baseline, then checks **both** targets (update scenarios):

- root target:
  - `version.txt` equals effective `SAMPLE_VERSION` in `Dockerfile`,
  - `old_ver.json` has matching `SAMPLE.version`.
- secondary target:
  - `secondary/version.txt` equals effective `SECONDARY_VERSION` in
    `secondary/Dockerfile`,
  - `secondary/old_ver.json` has matching `SECONDARY.version`.

then runs `verify_release.py`. After successful verification, it removes
release/tag artifacts created by the run and force-resets the default branch
back to `BASELINE_REF` (a tag: move it whenever the fixture's baseline files change).
