# cicd integration test

This repository exercises the reusable workflows from snw35/cicd as a full integration test. This is needed because simulating Github Actions runs using tools like ACT are too limited, and cannot cover all of the workflow code involved. It keeps the
repository in a steady state by resetting back to a baseline after each run.

## Files
- Dockerfile: minimal container with SAMPLE_VERSION.
- nvchecker.toml, old_ver.json, version.txt: sample update inputs.
- .github/workflows/integration-update.yaml: calls snw35/cicd workflows.
- .github/workflows/verify-reset.yaml: verifies changes, then resets to baseline.

## Setup

Configure secrets:
 - DOCKER_PASSWORD: Docker Hub password or access token for $GITHUB_REPOSITORY_OWNER.

Optional repository variables:
- CICD_REF: override the ref used for snw35/cicd helper scripts.
- BASELINE_REF: override the baseline tag or branch name (default: baseline).

Cross-repo PR integration note:
- `snw35/cicd` dispatches this workflow on an ephemeral branch and rewrites this
  workflow's reusable `uses:` refs to the `cicd` PR SHA before dispatch.
- The token used in `snw35/cicd` (`CICD_INTEGRATION_TOKEN`) needs least-privilege
  fine-grained PAT permissions on this repository:
  - **Actions: Read and write** (dispatch + workflow run polling)
  - **Contents: Read and write** (ephemeral branch ref and workflow file rewrite)

## Workflow example
The integration update workflow calls the reusable workflows like any downstream
repository:

```yaml
jobs:
  update:
    uses: snw35/cicd/.github/workflows/github.yaml@main
    with:
      IMAGE_TAG: SAMPLE_VERSION
      CICD_REF: ${{ inputs.cicd_ref || vars.CICD_REF || 'main' }}
    secrets: inherit

  release:
    needs: update
    if: github.ref_name == github.event.repository.default_branch && needs.update.outputs.changed == 'true'
    uses: snw35/cicd/.github/workflows/create-release.yaml@main
    with:
      targets_json: ${{ needs.update.outputs.targets }}
      CICD_REF: ${{ inputs.cicd_ref || vars.CICD_REF || 'main' }}
    secrets: inherit
```

## What happens
- Integration Update runs the upstream workflow and creates tags/releases when
  changes are detected.
- Verify and Reset checks that Dockerfile and old_ver.json match version.txt,
  then force-resets the default branch back to the baseline commit.
