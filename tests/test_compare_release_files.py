"""Cross-project fixtures for the read-only release evidence helper."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_release_files.py"
spec = importlib.util.spec_from_file_location("compare_release_files", SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def roots(tmp_path):
    source = tmp_path / "inventory-source"
    delivery = tmp_path / "inventory-delivery"
    (source / "app").mkdir(parents=True)
    (delivery / "app").mkdir(parents=True)
    (delivery / "checksums").mkdir()
    return source, delivery


def manifest(delivery, relative, data):
    digest = hashlib.sha256(data).hexdigest()
    (delivery / "checksums" / "SHA256SUMS.txt").write_text(
        digest + "  " + relative + "\n", encoding="utf-8")


def test_independent_matching_files_and_manifest(tmp_path):
    source, delivery = roots(tmp_path)
    data = b"inventory service v2"
    (source / "app" / "server.py").write_bytes(data)
    (delivery / "app" / "server.py").write_bytes(data)
    manifest(delivery, "app\\server.py", data)
    result = tool.compare(source, delivery, ["app/server.py"], 1024,
                          "checksums/SHA256SUMS.txt")
    assert result["requested_evidence_passed"] is True
    assert result["files"][0]["status"] == "same"
    assert result["files"][0]["manifest"] == "match"
    assert result["scope"] == "selected_files_only"
    assert result["runtime_verified"] is False


def test_old_delivery_can_have_an_internally_valid_manifest(tmp_path):
    source, delivery = roots(tmp_path)
    (source / "app" / "server.py").write_bytes(b"v2")
    (delivery / "app" / "server.py").write_bytes(b"v1")
    manifest(delivery, "app/server.py", b"v1")
    result = tool.compare(source, delivery, ["app/server.py"], 1024,
                          "checksums/SHA256SUMS.txt")
    assert result["files"][0]["status"] == "different"
    assert result["files"][0]["manifest"] == "match"
    assert result["requested_evidence_passed"] is False


def test_no_manifest_still_limits_claim_to_selected_bytes(tmp_path):
    source, delivery = roots(tmp_path)
    (source / "app" / "server.py").write_bytes(b"same")
    (delivery / "app" / "server.py").write_bytes(b"same")
    result = tool.compare(source, delivery, ["app/server.py"], 1024)
    assert result["requested_evidence_passed"] is True
    assert result["manifest_requested"] is False
    assert result["files"][0]["manifest"] == "not_requested"
    assert result["runtime_verified"] is False


def test_missing_unlisted_and_duplicate_manifest_fail_closed(tmp_path):
    source, delivery = roots(tmp_path)
    (source / "app" / "server.py").write_bytes(b"same")
    relative = "app/server.py"
    missing = tool.compare(source, delivery, [relative], 1024)
    assert missing["files"][0]["status"] == "package_missing"
    (delivery / "app" / "server.py").write_bytes(b"same")
    manifest(delivery, "other.py", b"other")
    unlisted = tool.compare(source, delivery, [relative], 1024,
                            "checksums/SHA256SUMS.txt")
    assert unlisted["files"][0]["manifest"] == "unlisted"
    assert unlisted["requested_evidence_passed"] is False
    manifest(delivery, relative, b"same")
    with (delivery / "checksums" / "SHA256SUMS.txt").open("a", encoding="utf-8") as stream:
        stream.write(hashlib.sha256(b"same").hexdigest() + "  " + relative + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        tool.compare(source, delivery, [relative], 1024,
                     "checksums/SHA256SUMS.txt")


def test_escape_sensitive_and_large_files_are_not_read(tmp_path):
    source, delivery = roots(tmp_path)
    for relative in ("../outside.py", "C:\\outside.py", ".env",
                     "config/token.txt", "config/credentials.json",
                     ".ssh/id_rsa", ".npmrc"):
        with pytest.raises(ValueError):
            tool.compare(source, delivery, [relative], 1024)
    (source / "app" / "server.py").write_bytes(b"longer")
    (delivery / "app" / "server.py").write_bytes(b"longer")
    large = tool.compare(source, delivery, ["app/server.py"], 1)
    assert large["files"][0]["status"] == "large_file_skipped"
    assert large["requested_evidence_passed"] is False


def test_manifest_read_is_bounded(tmp_path, monkeypatch):
    source, delivery = roots(tmp_path)
    (source / "app" / "server.py").write_bytes(b"x")
    (delivery / "app" / "server.py").write_bytes(b"x")
    manifest(delivery, "app/server.py", b"x")
    monkeypatch.setattr(tool, "MAX_MANIFEST_BYTES", 8, raising=False)
    with pytest.raises(ValueError, match="manifest.*large"):
        tool.compare(source, delivery, ["app/server.py"], 1024,
                     "checksums/SHA256SUMS.txt")


def test_shared_file_entity_is_not_independent_evidence(tmp_path, monkeypatch):
    source, delivery = roots(tmp_path)
    data = b"shared bytes"
    (source / "app" / "server.py").write_bytes(data)
    (delivery / "app" / "server.py").write_bytes(data)
    monkeypatch.setattr(tool.os.path, "samefile", lambda *_: True)
    result = tool.compare(source, delivery, ["app/server.py"], 1024)
    assert result["files"][0]["status"] == "shared_file_entity"
    assert result["requested_evidence_passed"] is False


def test_real_hard_link_when_supported(tmp_path):
    source, delivery = roots(tmp_path)
    file = source / "app" / "server.py"
    file.write_bytes(b"shared bytes")
    try:
        os.link(str(file), str(delivery / "app" / "server.py"))
    except OSError as exc:
        pytest.skip("hard links unavailable: %s" % exc)
    result = tool.compare(source, delivery, ["app/server.py"], 1024)
    assert result["files"][0]["status"] == "shared_file_entity"


def test_same_root_is_detected_as_shared_without_hard_link_privileges(tmp_path):
    source, _ = roots(tmp_path)
    (source / "app" / "server.py").write_bytes(b"same file")
    result = tool.compare(source, source, ["app/server.py"], 1024)
    assert result["files"][0]["status"] == "shared_file_entity"
    assert result["requested_evidence_passed"] is False


def test_cli_exit_codes_preserve_the_claim_ceiling(tmp_path, capsys):
    source, delivery = roots(tmp_path)
    data = b"matching bytes"
    (source / "app" / "server.py").write_bytes(data)
    (delivery / "app" / "server.py").write_bytes(data)
    args = ["--source", str(source), "--delivery", str(delivery), "app/server.py"]
    assert tool.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["runtime_verified"] is False
    assert result["scope"] == "selected_files_only"
    assert tool.main(args + ["missing.py"]) == 1
    capsys.readouterr()
    assert tool.main(args[:-1] + ["../escape.py"]) == 2
