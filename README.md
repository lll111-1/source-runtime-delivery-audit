# Source / Runtime / Delivery Audit

An Agent Skill for checking a specific version-consistency claim across three different layers: editable source, a running service, and a delivered copy. It prevents a matching path, a green source test, or an internally valid package checksum from being mistaken for proof that all three layers run the same code.

The Skill is intentionally narrow. It is not a security scanner, deployment tool, full-package verifier, or replacement for runtime behavior tests.

## Use

Install this directory as `source-runtime-delivery-audit` in your agent's skills directory, then ask the agent to check whether a named fix or feature in source is present in the running service and the delivered copy. The agent reads [`SKILL.md`](SKILL.md) and reports a claim-by-claim evidence matrix.

The included comparison script is read-only and uses only the Python standard library:

```text
python scripts/compare_release_files.py --source SOURCE_ROOT --delivery DELIVERY_ROOT --manifest checksums/SHA256SUMS.txt path/to/file.py
```

`--manifest` is optional. List only the small files relevant to the claim. The default per-file limit is 16 MiB, and the manifest limit is 16 MiB. Exit code 0 means only that the **selected independent files** match and, if requested, their manifest entries match. Exit code 1 means the selected evidence does not pass; 2 means the comparison was rejected. Output always says `runtime_verified: false` because the script does not inspect a running process.

The script rejects path escapes and common credential filenames, but filenames cannot reveal every secret. Review selected paths before using the tool or sharing its output. A running process can also keep old Python code loaded after its file changes on disk; use a startup-captured revision or a controlled restart plus behavior evidence when runtime identity matters.

## Validation

Run `python -m pytest tests -q` after installing `pytest` for the test suite. The tests cover stale delivery copies with internally valid checksums, missing and shared files, path and size boundaries, CLI exit codes, and the difference between loaded Python code and current disk bytes. One real hard-link creation test may skip where the environment does not permit hard links.

The Skill has been tried against one real project and in an independent read-only Agent trial. That evidence supports its bounded workflow; it does not establish effectiveness across every stack or prove that a particular running service has been verified.

## License

MIT. See [LICENSE](LICENSE).
