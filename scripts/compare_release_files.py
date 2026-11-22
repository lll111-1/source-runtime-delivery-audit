"""Read-only comparison of selected small files across source and delivery.

An optional SHA256SUMS-style manifest can be checked for those same files.
This cannot verify runtime behavior or the rest of the delivery.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys


SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
SECRET_NAMES = {".npmrc", ".pypirc", "id_rsa", "id_ed25519"}
MAX_MANIFEST_BYTES = 16 * 1024 * 1024


def safe_relative_path(value):
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if (not normalized or normalized.startswith("/") or ":" in normalized
            or any(part in ("", ".", "..") for part in parts)):
        raise ValueError("path must be a relative file path inside both roots")
    lower = [part.lower() for part in parts]
    name = lower[-1]
    if (any(part in {"secrets", ".git", ".ssh"} for part in lower)
            or name in SECRET_NAMES or name == ".env" or name.startswith(".env.")
            or name.endswith(tuple(SECRET_SUFFIXES))
            or any(word in name for word in ("api_key", "password", "secret",
                                                  "token", "credential", "private_key"))):
        raise ValueError("sensitive paths are excluded")
    return normalized


def inside_root(root, relative):
    candidate = (root / relative).resolve()
    try:
        if os.path.commonpath((str(root), str(candidate))) != str(root):
            raise ValueError("path resolves outside a root")
    except ValueError:
        raise ValueError("path resolves outside a root")
    return candidate


def sha256_small(path, max_bytes):
    before = path.stat()
    if before.st_size > max_bytes:
        return None, before.st_size
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("file changed while being hashed")
    return digest.hexdigest(), before.st_size


def read_manifest(path):
    if not path.is_file():
        return None
    entries = {}
    with path.open("rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest is too large")
    for line in raw.decode("utf-8").splitlines():
        match = re.match(r"^([a-fA-F0-9]{64})  (.+?)\s*$", line)
        if match:
            relative = match.group(2).replace("\\", "/").lower()
            if relative in entries:
                raise ValueError("duplicate entry in checksum manifest")
            entries[relative] = match.group(1).lower()
    return entries


def compare(source_root, package_root, relatives, max_bytes, manifest_relative=None):
    source_root = Path(source_root).resolve()
    package_root = Path(package_root).resolve()
    if not source_root.is_dir() or not package_root.is_dir():
        raise ValueError("source and package roots must both exist")
    manifest = (read_manifest(inside_root(package_root, safe_relative_path(manifest_relative)))
                if manifest_relative else None)
    results = []
    for supplied in relatives:
        relative = safe_relative_path(supplied)
        source = inside_root(source_root, relative)
        package = inside_root(package_root, relative)
        row = {"file": relative, "status": None,
               "manifest": "not_requested" if not manifest_relative else "not_checked"}
        if not source.is_file():
            row["status"] = "source_missing"
        elif not package.is_file():
            row["status"] = "package_missing"
        else:
            source_hash, source_size = sha256_small(source, max_bytes)
            package_hash, package_size = sha256_small(package, max_bytes)
            row["source_bytes"] = source_size
            row["package_bytes"] = package_size
            if source_hash is None or package_hash is None:
                row["status"] = "large_file_skipped"
            else:
                row["source_sha256"] = source_hash
                row["package_sha256"] = package_hash
                try:
                    same_entity = os.path.samefile(str(source), str(package))
                except OSError:
                    same_entity = False
                row["status"] = ("shared_file_entity" if same_entity else
                                 "same" if source_hash == package_hash else "different")
                if manifest_relative and manifest is None:
                    row["manifest"] = "missing"
                elif manifest_relative and relative.lower() not in manifest:
                    row["manifest"] = "unlisted"
                elif manifest_relative:
                    row["manifest"] = ("match" if manifest[relative.lower()] == package_hash
                                       else "mismatch")
        results.append(row)
    all_equal = bool(results) and all(row["status"] == "same" for row in results)
    manifest_ok = (None if not manifest_relative else
                   manifest is not None and all(row["manifest"] == "match" for row in results))
    return {
        "scope": "selected_files_only",
        "runtime_verified": False,
        "manifest_requested": bool(manifest_relative),
        "manifest_present": manifest is not None,
        "all_selected_files_equal": all_equal,
        "requested_evidence_passed": all_equal and manifest_ok is not False,
        "files": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--delivery", "--package", dest="delivery", required=True)
    parser.add_argument("--manifest", help="relative SHA256SUMS-style path inside delivery")
    parser.add_argument("--max-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)
    if args.max_bytes <= 0:
        parser.error("--max-bytes must be positive")
    try:
        result = compare(args.source, args.delivery, args.files, args.max_bytes,
                         manifest_relative=args.manifest)
    except (OSError, ValueError) as exc:
        print("comparison rejected: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["requested_evidence_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
