# 0006 — GitHub Actions for CI, not Cloud Build

- **Status**: Accepted
- **Date**: 2026-04-19
- **Authors**: @ioannis-n-melas

## Context

We need CI that runs tests + lint + builds on PRs and pushes, and can optionally deploy on merge to main (behind manual approval).

## Options considered

- **Cloud Build** — what market-snapshot uses. Integrated with GCP, but triggers live in GCP and are less visible to contributors.
- **GitHub Actions** — CI definition lives in the repo, widely familiar, 2000 min/mo free for private repos on personal accounts.
- **Self-hosted runner on GCE** — overkill for POC.

## Decision

**GitHub Actions.** Workflow YAML in `.github/workflows/` is version-controlled alongside the code. Deploys that touch GCP use Workload Identity Federation (no service account JSON in secrets).

## Consequences

- **Good**: PR status checks, lint, and test feedback arrive next to the code.
- **Good**: no long-lived service-account keys in GitHub Secrets.
- **Bad**: 2000 min/mo limit — need to watch CI cost if this repo grows.
- **Trigger to revisit**: CI time budget blown, or need for private-network GCP access during builds.

## References

- [Workload Identity Federation docs](https://cloud.google.com/iam/docs/workload-identity-federation)
