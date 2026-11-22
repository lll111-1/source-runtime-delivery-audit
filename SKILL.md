---
name: source-runtime-delivery-audit
description: Use when checking whether an editable source tree, a running local service, and a delivered copy contain the same version of a fix or feature. Do not use for ordinary code review or a generic security audit without a version or delivery claim.
---

# Source, runtime, and delivery evidence

The three layers can disagree even when their paths look identical. Establish the exact claim and inspect only its relevant files and runtime resources.

## Source

Record the editable root, Git commit/branch and relevant working-tree changes. Read the entrypoint and callers that produce the claimed behavior. A source test proves only that source under the tested inputs; it does not prove a running process or package uses those bytes.

## Runtime

Ask the running process for its own loaded module path, resolved data/static roots, and file identity (size, stat identity, SHA-256 where practical). Pair that with PID, parent and launch command. A reported cwd or matching path string alone is insufficient when overlays, copies, junctions, or hard links may exist. **Hashing the path after import proves current disk bytes, not the code already loaded in memory.** To bind loaded code to a revision, prefer a build identifier or hash captured at process startup, or restart from a known artifact and verify behavior. If that evidence is unavailable, mark loaded-code identity unknown. Verify observed behavior separately from file identity.

When process inspection is restricted, try only available read-only evidence in order: an existing health/status response, startup logs with PID and launch command, then a process-reported module/data path or startup-captured revision if the service already exposes one. Record which check was denied; no response or an inaccessible process list does **not** prove the service is stopped. A generic version string or a current file hash does not prove loaded-code identity. Prove the launcher used to start the service separately from the Python modules it loaded; matching launcher bytes alone cannot establish either runtime code or behavior. Do not restart or instrument a service just to complete an audit unless that action is separately authorized.

## Delivery

Use [compare_release_files.py](scripts/compare_release_files.py) for an explicit list of small source files and a delivery directory. Pass `--manifest` only when the package has a SHA256SUMS-style manifest. The tool refuses path escape and sensitive paths, caps reads, and treats a shared file entity as non-independent. Exit 0 means only that the selected independent bytes match and, if requested, their manifest entries match. It never proves the entire package or runtime behavior. Do not hash or overwrite large model artifacts to make this comparison pass.

The sensitive-path filter catches common names, not secrets hidden in ordinary files. Review the selected paths before running the helper or publishing its output; never feed it credentials merely because their filenames look harmless.

## Decision

Report `claim | source evidence | runtime evidence | delivery evidence | behavior evidence | open gap`. Keep each conclusion at its proven layer. A failing or missing layer blocks a cross-layer PASS; it need not block unrelated source work. Preserve existing files and checkpoints. Never copy, convert, delete, deploy, commit, or publish artifacts merely because an audit found a mismatch.
