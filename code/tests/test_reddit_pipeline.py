import sys
import unittest
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reddit_pipeline import canonical_post, collect, load_policies, parse_reddit, search_plan


def epoch(day):
    return datetime(2025, 5, day, 12, tzinfo=timezone.utc).timestamp()


class RedditPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policies(Path(__file__).resolve().parents[1] / "config/policies.example.json")[0]

    def test_window_and_comment_gaps(self):
        data = [
            {"data": {"children": [{"data": {"id": "abc", "created_utc": epoch(27),
                "title": "Student visa appointments paused", "selftext": "", "subreddit": "f1visa",
                "num_comments": 4}}]}},
            {"data": {"children": [
                {"kind": "t1", "data": {"id": "c1", "created_utc": epoch(28), "body": "Same here",
                    "replies": {"data": {"children": [{"kind": "more", "data": {"parent_id": "t1_c1", "count": 3}}]}}}}
            ]}}
        ]
        post, comments = parse_reddit(data, self.policy, "https://www.reddit.com/r/f1visa/comments/abc/")
        self.assertEqual(post["status"], "matched")
        self.assertEqual(len(comments), 1)
        self.assertFalse(post["comments_complete"])
        self.assertEqual(post["unresolved_more_nodes"][0]["count"], 3)
        self.assertTrue(comments[0]["within_policy_window"])
        data[0]["data"]["children"][0]["data"]["created_utc"] = datetime(2025, 6, 4, tzinfo=timezone.utc).timestamp()
        post, _ = parse_reddit(data, self.policy, "https://www.reddit.com/r/f1visa/comments/abc/")
        self.assertEqual(post["status"], "outside_window")

    def test_url_and_query_plan(self):
        self.assertEqual(canonical_post("https://old.reddit.com/r/f1visa/comments/ABC/slug/?utm_source=x")[0], "abc")
        self.assertIsNone(canonical_post("https://example.com/r/f1visa/comments/ABC/"))
        self.assertEqual(len(search_plan([self.policy], 20)), 16)

    def test_csv_to_search_to_post_and_comments(self):
        policies = load_policies(Path(__file__).resolve().parents[1] / "config/policies.example.csv")
        self.assertEqual(policies[0]["keywords"][0], "student visa appointments")
        reddit_response = [
            {"data": {"children": [{"data": {"id": "abc", "created_utc": epoch(27),
                "title": "Student visa appointments paused", "selftext": "I cannot book an interview",
                "subreddit": "f1visa", "num_comments": 1}}]}},
            {"data": {"children": [{"kind": "t1", "data": {"id": "c1", "created_utc": epoch(28),
                "body": "Same here", "replies": ""}}]}}
        ]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            with patch("reddit_pipeline.tavily_search", return_value=([{"url": "https://www.reddit.com/r/f1visa/comments/abc/slug/"},
                                                                         {"url": "https://www.reddit.com/r/other/comments/xyz/slug/"}], 1)):
                with patch("reddit_pipeline._request_json", return_value=reddit_response) as fetch:
                    report = collect(policies, Path(tmp) / "run", max_queries=16, delay=0)
            self.assertEqual(report["matched_posts"], 1)
            self.assertEqual(report["comments_retrieved"], 1)
            self.assertEqual(report["candidate_urls"], 1)
            self.assertEqual(report["rejected_other_subreddit"], 28)
            self.assertEqual(report["tavily_credits_reported"], 16)
            self.assertEqual(fetch.call_count, 1)
            self.assertIn("/comments/abc.json?", fetch.call_args.args[0])
            post = json.loads((Path(tmp) / "run/posts.jsonl").read_text().splitlines()[0])
            self.assertEqual(post["status"], "matched")
            self.assertTrue(post["comments_complete"])
            with self.assertRaisesRegex(ValueError, "already contains files"):
                collect(policies, Path(tmp) / "run", max_queries=16)

    def test_truncated_plan_rejected_before_api_call(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            with self.assertRaisesRegex(ValueError, "Search plan needs 16 queries"):
                collect([self.policy], Path(tmp) / "run", max_queries=1)


if __name__ == "__main__":
    unittest.main()
