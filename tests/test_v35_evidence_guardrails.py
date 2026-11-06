#!/usr/bin/env python3
"""Regression tests for evidence provenance and weekly cut-off governance."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v35 = load_script("v35_diagnosis_test", "macro_v35_diagnosis.py")
news = load_script("weekly_news_test", "00_fetch_weekly_news_context.py")


class V35EvidenceGovernanceTests(unittest.TestCase):
    def test_ai_commentary_does_not_create_official_inflation_facts(self):
        context = {
            "weekly_news_theme": "CPI 降溫",
            "macro_drivers": ["通膨降溫已獲確認"],
            "news_categories": {
                "利率": [{
                    "title": "美債殖利率回落",
                    "source": "測試來源",
                    "published_at": "2026-11-05 10:00:00 UTC",
                    "why_it_matters": "CPI 降溫，官方硬數據已證實",
                }]
            },
        }
        text = v35.collect_news_text(context, "", {}, "")
        self.assertIn("美債殖利率回落", text)
        self.assertNotIn("cpi", text)
        self.assertNotIn("官方硬數據", text)
        flags = v35.extract_macro_event_flags_v35(text)
        self.assertFalse(flags["inflationCooling"])

    def test_news_cutoff_uses_taipei_date_and_excludes_undated(self):
        def article(title, published):
            return {
                "title": title, "source": "測試來源", "url": "https://example.org/" + title,
                "published_at": published, "theme": "long_bond_yields", "query": "美債",
            }

        items = [
            article("截止日內新聞", "2026-11-05 14:30:00 UTC"),
            article("截止日後新聞", "2026-11-05 23:21:00 UTC"),
            article("日期不明新聞", ""),
        ]
        ranked = news.dedupe_and_rank(items, max_items=10, week_start="2026-10-30", week_end="2026-11-05")
        self.assertEqual([item["title"] for item in ranked], ["截止日內新聞"])

    def test_gemini_cannot_invent_news_not_in_rss(self):
        ranked = [{
            "title": "美債殖利率回落", "source": "原始RSS",
            "url": "https://example.org/real", "published_at": "2026-11-05 10:00:00 UTC",
            "theme": "long_bond_yields", "score": 30,
        }]
        response = {
            "news_categories": {
                "利率": [{"title": "美債殖利率回落", "url": "https://example.org/forged"}],
                "其他": [{"title": "未出現在來源中的重大新聞", "url": "https://example.org/fake"}],
            },
            "top_news": [{"title": "未出現在來源中的重大新聞"}],
        }
        normalized = news.normalize_news_categories(response, ranked_items=ranked)
        titles = [item["title"] for group in normalized["news_categories"].values() for item in group]
        self.assertNotIn("未出現在來源中的重大新聞", titles)
        self.assertIn("美債殖利率回落", titles)
        self.assertEqual(normalized["top_news"][0]["url"], "https://example.org/real")

    def test_market_quote_dates_and_unverified_official_data_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            data = {"series": [
                {"key": "US10Y", "points": [
                    {"date": "2026-10-30", "value": 4.93},
                    {"date": "2026-11-05", "value": 4.84},
                ]},
                {"key": "USDTWD", "points": [
                    {"date": "2026-10-30", "value": 32.6},
                    {"date": "2026-11-04", "value": 33.07},
                ]},
                {"key": "WTI", "points": [
                    {"date": "2026-10-30", "value": 104.12},
                    {"date": "2026-11-05", "value": 91.20},
                ]},
            ]}
            (folder / "weekly_market_series.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            (folder / "weekly_news_context.json").write_text(
                json.dumps({"news_categories": {}}, ensure_ascii=False), encoding="utf-8"
            )
            result = v35.build_weekly_v35_diagnosis(
                folder, start_override="2026-10-30", end_override="2026-11-05"
            )
            coverage = result["meta"]["market_date_coverage"]
            self.assertIn("USDTWD: 2026-11-04", coverage["lagging_assets"])
            self.assertEqual(coverage["last_quote_dates"]["US10Y"], "2026-11-05")
            self.assertTrue(any(
                "USDTWD" in value for value in result["weekly_v35_diagnosis"]["asset_validation"]
            ))
            self.assertFalse(
                result["meta"]["evidence_policy"]["verified_official_inflation_series_ingested"]
            )


if __name__ == "__main__":
    unittest.main()
