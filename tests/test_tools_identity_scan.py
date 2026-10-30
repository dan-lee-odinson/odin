"""The identity scan for the Director's records (00_HANDOFF.md §3, item 8): Windows usernames, machine names,
private paths and private email addresses are found and reported; the public identity passes. Every
name and address here is made up for the test."""

import gzip

import pytest

from tools import identity_scan
from tools.identity_scan import scan

MACHINE = {"USERNAME": "jqtester", "COMPUTERNAME": "ORION7"}

PLANTED = {
    "a Windows user-profile path": "Saved to C:\\Users\\someone\\Documents\\notes.md",
    "a forward-slash user-profile path": "see c:/Users/someone/AppData/Local/odin",
    "a Git Bash path": "cd /c/Users/someone/Documents",
    "a macOS home path": "open /Users/someone/Desktop/card.html",
    "a private email address": "Questions to jq.tester@example.net.",
    "this machine's username": "Logged in as JQTester",
    "this machine's name": "Captured on orion7 at 19:04",
    "a default Windows machine name": "Host DESKTOP-AB12CD3 answered",
}


@pytest.mark.parametrize("what", PLANTED)
def test_red_each_kind_of_private_detail_is_found(what):
    findings = scan("record.md", PLANTED[what].encode("utf-8"), MACHINE)
    assert findings and findings[0][:2] == ("record.md", 1)


def test_the_public_identity_and_ordinary_text_pass():
    text = ("Dan Lee-Odinson <dan.lee.odinson@gmail.com>\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
            "ORION7X is not the machine; jqtesters is not the user.\nThe ground station at D: band\n")
    assert scan("record.md", text.encode("utf-8"), MACHINE) == []


def test_findings_name_the_line():
    findings = scan("card.html", b"one\ntwo\nfile:///C:/Users/someone/card.html\n", MACHINE)
    assert [(line, kind) for _, line, kind, _ in findings] == [(3, "user-profile path")]


# A scene saved compressed hides a path from a scan of its bytes (ANIM-01, 30 October 2026): the scan reads
# through zstd and gzip, layer by layer, and says which layers it read.
SCENE = b"BLENDER17-01 ... Save As Blender File\x00C:\\Users\\someone\\Documents\\render\\out\\a1.png\x00 ..."


def zstd_compress(data):
    if identity_scan.zstd is None:
        pytest.skip("zstd needs Python 3.14 or later")
    return identity_scan.zstd.compress(data)


@pytest.mark.parametrize("packed, layers", [
    (lambda: gzip.compress(SCENE), "gzip"),
    (lambda: zstd_compress(SCENE), "zstd"),
    (lambda: gzip.compress(zstd_compress(SCENE)), "gzip/zstd")])
def test_red_a_path_planted_inside_a_compressed_file_is_found(packed, layers):
    findings = scan("huginn_a1.blend", packed(), MACHINE)
    assert [(name, kind, text) for name, _, kind, text in findings] == [
        (f"huginn_a1.blend ({layers})", "user-profile path", "C:\\Users\\someone")]


def test_a_compressed_file_that_cannot_be_read_is_a_finding_not_a_pass():
    damaged = gzip.compress(SCENE)[:40]
    [(name, line, kind, problem)] = scan("scene.blend", damaged, MACHINE)
    assert (name, line, kind) == ("scene.blend (gzip)", 0, "unreadable compressed file")
    assert problem.startswith("cannot be decompressed: ")
