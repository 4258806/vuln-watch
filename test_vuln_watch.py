#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vuln-watch 单元测试（Python 标准库 unittest，不联网）。跑：python3 -m unittest test_vuln_watch -v"""
import importlib.util
import json
import os
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "vuln_watch", os.path.join(_HERE, "vuln-watch.py"))
vw = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vw)


def _entry(**kw):
    e = {"cveID": "CVE-2026-12345", "vendorProject": "Acme",
         "product": "Widget", "vulnerabilityName": "Acme Widget RCE",
         "dateAdded": "2026-11-19", "dueDate": "2026-12-03",
         "shortDescription": "Acme Widget has a flaw.",
         "requiredAction": "Apply the vendor patch."}
    e.update(kw)
    return e


class TestLoadConfig(unittest.TestCase):
    def test_basic_and_comments(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("# 注释\nPUSHPLUS_TOKEN=abc123\nTG_CHAT_ID=  123456789  \n空行下面\n")
            path = f.name
        try:
            cfg = vw.load_config(path)
            self.assertEqual(cfg["PUSHPLUS_TOKEN"], "abc123")
            self.assertEqual(cfg["TG_CHAT_ID"], "123456789")
        finally:
            os.unlink(path)

    def test_missing_file(self):
        self.assertEqual(vw.load_config("/nonexistent/config.env"), {})


class TestLoadKeywords(unittest.TestCase):
    def test_parse(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# 注释\nnginx=Nginx\n\nSynology=群晖\nbadline\n=空键\n")
            path = f.name
        try:
            kws = vw.load_keywords(path)
            self.assertIn(("nginx", "Nginx"), kws)
            self.assertIn(("synology", "群晖"), kws)
            self.assertEqual(len(kws), 2)
        finally:
            os.unlink(path)

    def test_missing_file(self):
        self.assertEqual(vw.load_keywords("/nonexistent/keywords.txt"), [])


class TestRelevance(unittest.TestCase):
    def test_match_and_dedup(self):
        kws = [("nginx", "Nginx"), ("openresty", "OpenResty"),
               ("java", "Java")]
        tags = vw.relevance_tags(
            _entry(vendorProject="F5", product="NGINX Open Source",
                   vulnerabilityName="NGINX flaw"), kws)
        self.assertEqual(tags, ["Nginx"])

    def test_no_match(self):
        tags = vw.relevance_tags(_entry(), [("nginx", "Nginx")])
        self.assertEqual(tags, [])

    def test_case_insensitive(self):
        tags = vw.relevance_tags(
            _entry(vendorProject="SYNOLOGY"), [("synology", "群晖")])
        self.assertEqual(tags, ["群晖"])


class TestFormatMessage(unittest.TestCase):
    def test_title_and_flags(self):
        title, content = vw.format_message(
            [_entry(), _entry(cveID="CVE-2024-10441", vendorProject="Synology",
                              product="DiskStation Manager (DSM)")],
            "2026-11-19", [("synology", "群晖")])
        self.assertIn("新增 2 条", title)
        self.assertIn("CVE-2026-12345 【其他】", content)
        self.assertIn("CVE-2024-10441 【相关：群晖】", content)
        self.assertIn("来源：CISA KEV", content)

    def test_escapes_html(self):
        _, content = vw.format_message(
            [_entry(vulnerabilityName="A <b> & \"quoted\"")], "2026-11-19", [])
        self.assertIn("A &lt;b&gt; &amp;", content)
        self.assertNotIn("<b> &", content)


class TestTelegramText(unittest.TestCase):
    def test_br_to_newline_and_bold_kept(self):
        text = vw.tg_content("<b>CVE-2026-12345</b><br>厂商：Acme<br>")
        self.assertEqual(text, "<b>CVE-2026-12345</b>\n厂商：Acme\n")
        self.assertNotIn("<br>", text)

    def test_split_short(self):
        self.assertEqual(vw.split_message("a\nb\nc"), ["a\nb\nc"])

    def test_split_long(self):
        long_text = "\n".join("行 %d %s" % (i, "x" * 100) for i in range(100))
        chunks = vw.split_message(long_text)
        self.assertTrue(len(chunks) > 1)
        self.assertTrue(all(len(c) <= 4000 for c in chunks))
        self.assertEqual("\n".join(chunks), long_text)

    def test_split_single_huge_line(self):
        chunks = vw.split_message("y" * 9000)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(c) <= 4000 for c in chunks))


class TestState(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "seen.json")
            vw.save_state(path, {"CVE-2026-1", "CVE-2026-2"}, "2026-11-19")
            seen, last = vw.load_state(path)
            self.assertEqual(seen, {"CVE-2026-1", "CVE-2026-2"})
            self.assertEqual(last, "2026-11-19")

    def test_corrupt_state(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "seen.json")
            with open(path, "w") as f:
                f.write("{not json")
            seen, last = vw.load_state(path)
            self.assertEqual(seen, set())


class TestVendorUrl(unittest.TestCase):
    def test_vendor_first(self):
        e = _entry(notes="https://www.synology.com/zh-tw/security/advisory/Synology_SA_24_20 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04 ; https://nvd.nist.gov/vuln/detail/CVE-2024-10441")
        self.assertEqual(
            vw.vendor_url(e),
            "https://www.synology.com/zh-tw/security/advisory/Synology_SA_24_20")

    def test_skips_nvd_and_cisa(self):
        e = _entry(notes="https://nvd.nist.gov/vuln/detail/CVE-2021-39793 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04")
        self.assertEqual(vw.vendor_url(e), "")

    def test_vendor_after_nvd(self):
        e = _entry(notes="https://nvd.nist.gov/vuln/detail/CVE-2026-1 ; https://github.com/BerriAI/litellm/security/advisories/GHSA-wxxx-gvqv-xp7p")
        self.assertEqual(
            vw.vendor_url(e),
            "https://github.com/BerriAI/litellm/security/advisories/GHSA-wxxx-gvqv-xp7p")

    def test_no_notes(self):
        self.assertEqual(vw.vendor_url(_entry()), "")


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestTranslateText(unittest.TestCase):
    def setUp(self):
        self._real_urlopen = vw.urllib.request.urlopen

    def tearDown(self):
        vw.urllib.request.urlopen = self._real_urlopen

    def _fake_json(self, payload):
        vw.urllib.request.urlopen = lambda req, timeout=None: FakeResponse(
            200, json.dumps(payload).encode("utf-8"))

    def test_success(self):
        self._fake_json({"responseData": {"translatedText": "中文译文"},
                         "responseStatus": 200, "quotaFinished": False})
        self.assertEqual(vw.translate_text("English text"), "中文译文")

    def test_network_error(self):
        import urllib.error
        vw.urllib.request.urlopen = lambda req, timeout=None: (_ for _ in ()).throw(
            urllib.error.URLError("no network"))
        self.assertIsNone(vw.translate_text("English text"))

    def test_quota_warning_text(self):
        self._fake_json({"responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY. NEXT AVAILABLE IN 07 HOURS"},
                         "responseStatus": 200, "quotaFinished": None})
        self.assertIsNone(vw.translate_text("English text"))

    def test_quota_finished(self):
        self._fake_json({"responseData": {"translatedText": "中文译文"},
                         "responseStatus": 200, "quotaFinished": True})
        self.assertIsNone(vw.translate_text("English text"))

    def test_same_as_input(self):
        self._fake_json({"responseData": {"translatedText": "English text"},
                         "responseStatus": 200, "quotaFinished": False})
        self.assertIsNone(vw.translate_text("English text"))


class TestFormatMessageTranslated(unittest.TestCase):
    def test_translated_and_links(self):
        notes = ("https://www.synology.com/zh-tw/security/advisory/Synology_SA_24_20 ; "
                 "https://nvd.nist.gov/vuln/detail/CVE-2024-10441")
        _, content = vw.format_message(
            [_entry(cveID="CVE-2024-10441", notes=notes)],
            "2026-11-19", [],
            translate=lambda t: "【译】" + t)
        self.assertIn("【译】Acme Widget RCE", content)
        self.assertIn("【译】Acme Widget has a flaw.", content)
        self.assertNotIn("Apply the vendor patch.", content)
        self.assertIn('<a href="https://www.synology.com/zh-tw/security/advisory/Synology_SA_24_20">厂商公告</a>', content)
        self.assertIn('<a href="https://nvd.nist.gov/vuln/detail/CVE-2024-10441">NVD</a>', content)

    def test_translate_none_falls_back(self):
        _, content = vw.format_message(
            [_entry()], "2026-11-19", [], translate=lambda t: None)
        self.assertIn("Acme Widget RCE", content)
        self.assertIn("Acme Widget has a flaw.", content)
        self.assertIn('<a href="https://nvd.nist.gov/vuln/detail/CVE-2026-12345">NVD</a>', content)
        self.assertNotIn("厂商公告", content)


if __name__ == "__main__":
    unittest.main()
