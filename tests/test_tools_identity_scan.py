"""The identity scan for the Director's records (00_HANDOFF.md §3, item 8): Windows usernames, machine names,
private paths and private email addresses are found and reported; the public identity passes. Every
name and address here is made up for the test."""

import pytest

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
