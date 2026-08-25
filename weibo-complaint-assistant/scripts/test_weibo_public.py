#!/usr/bin/env python3

import json
import unittest
from unittest.mock import patch

import weibo_public


class LinkParsingTests(unittest.TestCase):
    def test_numeric_mid(self):
        target = weibo_public.parse_target("5309997458393240")
        self.assertEqual(target.mid, "5309997458393240")
        self.assertIsNone(target.bid)

    def test_desktop_url_extracts_uid_and_bid(self):
        target = weibo_public.parse_target("https://weibo.com/1234567890/Qw06Kd98p")
        self.assertEqual(target.uid, "1234567890")
        self.assertEqual(target.bid, "Qw06Kd98p")
        self.assertTrue(target.mid.isdigit())

    def test_mobile_detail_url(self):
        target = weibo_public.parse_target("https://m.weibo.cn/detail/5309997458393240")
        self.assertEqual(target.mid, "5309997458393240")

    def test_account_profile_is_not_treated_as_post(self):
        target = weibo_public.parse_target("https://weibo.com/u/1234567890")
        self.assertEqual(target.uid, "1234567890")
        self.assertIsNone(target.mid)
        self.assertTrue(any("account profile URL" in item for item in target.warnings))

    def test_non_weibo_url_is_rejected(self):
        target = weibo_public.parse_target("https://example.com/123")
        self.assertIsNone(target.mid)
        self.assertTrue(any("Only weibo.com" in item for item in target.warnings))


class TextAndStatusTests(unittest.TestCase):
    def test_strip_html_preserves_line_break(self):
        value = weibo_public.strip_html("<p>第一行<br>第二行</p>")
        self.assertEqual(value, "第一行\n第二行")

    def test_normalize_status(self):
        status = {
            "id": 123,
            "bid": "abc",
            "text": "<span>测试正文</span>",
            "created_at": "Mon Jun 15 09:05:12 +0800 2026",
            "user": {"id": 456, "screen_name": "测试账号"},
            "reposts_count": 1,
            "comments_count": 2,
            "attitudes_count": 3,
            "pics": [{"large": {"url": "https://wx1.sinaimg.cn/large/test.jpg"}}],
        }
        value = weibo_public.normalize_status(status, weibo_public.Target("123"))
        self.assertEqual(value["canonical_url"], "https://weibo.com/456/abc")
        self.assertEqual(value["text"], "测试正文")
        self.assertEqual(value["user"]["screen_name"], "测试账号")
        self.assertEqual(value["media"]["images"], ["https://wx1.sinaimg.cn/large/test.jpg"])

    @patch.object(weibo_public, "fetch_status", return_value=(None, ["blocked"]))
    @patch.object(weibo_public.PublicClient, "warm_up", return_value=None)
    def test_collect_failure_returns_partial_not_exception(self, _warm_up, _fetch_status):
        value = weibo_public.collect("5309997458393240", timeout=0.1)
        self.assertEqual(value["status"], "partial")
        self.assertEqual(value["post"]["id"], "5309997458393240")
        self.assertIn("user-provided", value["next_step"])
        json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
