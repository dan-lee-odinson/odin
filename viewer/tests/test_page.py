"""The page's own checks, read from its source: no network, no writing, no HTML
built from recorded text. tests/test_page_in_browser.py checks the same page
running in a browser."""

import re
import unittest

import _support as S

# SVG's XML namespace name. verda.js passes it to createElementNS; it is a name,
# and nothing is ever fetched from it.
SVG_NAMESPACE = "http://www.w3.org/2000/svg"

NETWORK = [
    r"\bfetch\s*\(", r"XMLHttpRequest", r"\bWebSocket\b", r"\bEventSource\b", r"sendBeacon",
    r"\bimport\s*\(", r"importScripts", r"serviceWorker", r"RTCPeerConnection", r"\bnew\s+Worker\b",
    r"SharedWorker", r"\bwindow\.open\s*\(", r"location\.(assign|replace|href\s*=)", r"@import",
    r"WebTransport", r"navigator\.connection",
]
WRITING = [
    r"localStorage", r"sessionStorage", r"indexedDB", r"document\.cookie", r"\bdownload\s*=",
    r"createObjectURL", r"showSaveFilePicker", r"<form\b", r"FileSystem", r"\.postMessage\s*\(",
    r"navigator\.clipboard",
]
HTML_FROM_TEXT = [r"innerHTML", r"outerHTML", r"insertAdjacentHTML", r"document\.write", r"\beval\s*\(",
                  r"new\s+Function\s*\(", r"setTimeout\s*\(\s*['\"]"]


def page_sources():
    folder = S.page_dir()
    files = {name: (folder / name).read_text(encoding="utf-8") for name in ("index.html", "verda.js", "verda.css")}
    return files


def csp(html):
    found = re.findall(r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"', html)
    if len(found) != 1:
        raise AssertionError("expected one Content-Security-Policy meta tag, found %d" % len(found))
    policy = {}
    for part in found[0].split(";"):
        words = part.split()
        if words:
            policy[words[0]] = words[1:]
    return policy


class NoNetwork(unittest.TestCase):
    def test_no_network_calls_or_addresses(self):
        for name, text in page_sources().items():
            for pattern in NETWORK:
                with self.subTest(file=name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, text), "%s uses %s" % (name, pattern))
            without_ns = text.replace(SVG_NAMESPACE, "")
            with self.subTest(file=name, check="addresses"):
                self.assertEqual(re.findall(r"(?:https?|wss?|ftp)://[^\s'\")]*", without_ns, re.I), [])
                self.assertEqual(re.findall(r"""(?:src|href)\s*=\s*['"]//""", without_ns, re.I), [])

    def test_html_loads_only_files_beside_it(self):
        html = page_sources()["index.html"]
        refs = re.findall(r"""\b(?:src|href)\s*=\s*["']([^"']*)["']""", html)
        self.assertEqual(sorted(refs), ["timelines/index.js", "verda.css", "verda.js"])
        self.assertEqual(re.findall(r"<script\b(?![^>]*\bsrc=)[^>]*>", html), [], "inline script")
        self.assertEqual(re.findall(r"\son[a-z]+\s*=", html), [], "inline event handler")

    def test_content_security_policy_refuses_connections(self):
        policy = csp(page_sources()["index.html"])
        self.assertEqual(policy.get("default-src"), ["'none'"])
        self.assertEqual(policy.get("connect-src"), ["'none'"])
        self.assertEqual(policy.get("form-action"), ["'none'"])
        for directive in ("script-src", "style-src", "font-src", "media-src"):
            sources = policy.get(directive, [])
            self.assertTrue(set(sources) <= {"'self'", "file:"}, "%s allows %s" % (directive, sources))


class NoWriting(unittest.TestCase):
    def test_page_writes_nothing(self):
        for name, text in page_sources().items():
            for pattern in WRITING:
                with self.subTest(file=name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, text), "%s uses %s" % (name, pattern))

    def test_recorded_text_is_never_parsed_as_html(self):
        text = page_sources()["verda.js"]
        for pattern in HTML_FROM_TEXT:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, text), "verda.js uses %s" % pattern)


if __name__ == "__main__":
    unittest.main()
