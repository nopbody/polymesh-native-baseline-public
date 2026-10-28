# Public Polymesh native baseline

This repository contains only infrastructure for one existing, non-security-sensitive
test from the unmodified public Polymesh v8.1.2 release. It contains no vulnerability
regressions, private research, disclosure reports, credentials, or copied Git history.

- Public source commit: `d44a84c1634d2fa6e0b3c690c569f43345683a1d`.
- Existing baseline: `corporate_actions_test::dist_claim_works`.
- Released CI toolchain: `nightly-2026-09-01`, using an immutable public image digest.
- Manual `workflow_dispatch` only; read-only workflow permissions; one concurrent job.
- Standard `ubuntu-24.04` runner, maximum job duration 90 minutes.
- Native compilation: two workers, two CPUs, 6 GiB memory, 70-minute wall limit.
- Exact test: one thread, no network, 1 GiB memory, 30-second wall limit.
- No blockchain node, chain synchronization, transactions, or local Rust compilation.

Build and test output from this public baseline is public and retained for seven days.
Only original output showing the exact test passing establishes baseline success.
Configuration validation, compilation alone, zero tests, and ignored tests do not.

The released native TestStorage harness includes Identity/no_cdd. A passing baseline
does not attest to unchanged Mainnet configuration or establish a security finding.

One manual baseline attempt is authorized. Do not automatically retry failures,
increase resource limits, enable paid infrastructure, or change billing settings.
Never add private research, PoCs, patches, reports, or sensitive logs to this repository.
