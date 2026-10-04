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
- `.github/workflows/verify-reset.yaml`: verifies version updates for all
  targets, deletes run-created release/tags, and force-resets to baseline.

## What this integration test covers

- Multi-target workflow dispatch/update through the shared `container-update.yaml`
  workflow's workdir matrix (root + secondary).
- `nvchecker` + `dfupdate` processing for Dockerfiles containing:
  - multiple `ENV` declarations,
  - duplicate keys where last assignment is the effective value.
- Compose validation path in reusable workflow using the local image tag through
  `docker-compose.yaml`.
- Tag/release creation path and metadata output handling from reusable workflows.

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
  workflow's reusable `uses:` refs to the `cicd` PR SHA before dispatch.
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
      actions: read
    uses: snw35/cicd/.github/workflows/container-update.yaml@main
    with:
      WORKDIRS: '[".","secondary"]'
      IMAGE_TAG: SAMPLE_VERSION
      IMAGE_TAG_BY_WORKDIR: '{"secondary":"SECONDARY_VERSION"}'
      CICD_REF: ${{ inputs.cicd_ref || vars.CICD_REF || 'main' }}
      RUN_AUTOMATED_UPDATE_ON_PR: ${{ github.event_name == 'pull_request' }}
    secrets: inherit
```

## Verification and reset behavior

When updates are detected, the verify workflow checks **both** targets:

- root target:
  - `version.txt` equals effective `SAMPLE_VERSION` in `Dockerfile`,
  - `old_ver.json` has matching `SAMPLE.version`.
- secondary target:
  - `secondary/version.txt` equals effective `SECONDARY_VERSION` in
    `secondary/Dockerfile`,
  - `secondary/old_ver.json` has matching `SECONDARY.version`.

After successful verification, it removes release/tag artifacts created by the
run and force-resets the default branch back to `BASELINE_REF`.
