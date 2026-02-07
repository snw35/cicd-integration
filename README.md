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
  that calls reusable workflows.
- `.github/workflows/verify-reset.yaml`: verifies version updates for all
  targets, deletes run-created release/tags, and force-resets to baseline.

## What this integration test covers

- Multi-target workflow dispatch/update via `TARGETS_JSON` (root + secondary).
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

The integration update workflow calls reusable workflows with explicit
multi-target configuration:

```yaml
jobs:
  update:
    uses: snw35/cicd/.github/workflows/github.yaml@main
    with:
      TARGETS_JSON: >-
        [{"name":"root","workdir":".","image_tag":"SAMPLE_VERSION"},{"name":"secondary","workdir":"secondary","image_tag":"SECONDARY_VERSION"}]
      CICD_REF: ${{ inputs.cicd_ref || vars.CICD_REF || 'main' }}
    secrets: inherit

  create-release:
    needs: update
    if: github.ref_name == github.event.repository.default_branch && needs.update.outputs.changed == 'true'
    uses: snw35/cicd/.github/workflows/create-release.yaml@main
    with:
      targets_json: ${{ needs.update.outputs.targets }}
      CICD_REF: ${{ inputs.cicd_ref || vars.CICD_REF || 'main' }}
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
