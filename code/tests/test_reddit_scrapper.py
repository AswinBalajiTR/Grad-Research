
import sys
import unittest
import json
import csv
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reddit"))
from reddit_scrapper import (canonical_post, collect, load_policies, parse_reddit, search_plan,
                             build_coverage, build_search_jobs, merge_reviewed, analyze_sentiment)


def epoch(day):
    return datetime(2025, 5, day, 12, tzinfo=timezone.utc).timestamp()


class RedditPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policies(Path(__file__).resolve().parents[1] / "reddit/config/policies.example.json")[0]

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
        policies = load_policies(Path(__file__).resolve().parents[1] / "reddit/config/policies.example.csv")
        self.assertEqual(policies[0]["keywords"][0], "student visa appointments")
        reddit_response = [
            {"data": {"children": [{"data": {"id": "abc", "created_utc": epoch(27),
                "title": "Student visa appointments paused", "selftext": "I cannot book an interview",
                "subreddit": "f1visa", "num_comments": 1}}]}},
            {"data": {"children": [{"kind": "t1", "data": {"id": "c1", "created_utc": epoch(28),
                "body": "Same here", "replies": ""}}]}}
        ]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            with patch("reddit_scrapper.tavily_search", return_value=([{"url": "https://www.reddit.com/r/f1visa/comments/abc/slug/"}], 1)):
                with patch("reddit_scrapper._request_json", return_value=reddit_response) as fetch:
                    report = collect(policies, Path(tmp) / "run", max_queries=16, delay=0)
            self.assertEqual(report["matched_posts"], 1)
            self.assertEqual(report["comments_retrieved"], 1)
            self.assertEqual(report["candidate_urls"], 1)
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

    def test_coverage_uses_actual_search_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text(json.dumps({"events": [{"event_id": "e1", "title": "Policy",
                "event_date": "2025-05-27", "end_date_inclusive": "2025-06-03"}],
                "subreddits": ["f1visa", "h1b"]}))
            (root / "search_audit.jsonl").write_text(json.dumps({"event_id": "e1", "subreddit": "f1visa",
                "status": "searched"}) + "\n" + json.dumps({"event_id": "e1", "subreddit": "h1b",
                "status": "failed"}) + "\n")
            build_coverage(root / "manifest.json", root / "candidates.jsonl", root,
                           root / "coverage.csv", root / "search_audit.jsonl")
            with (root / "coverage.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["discovery_search_completed"] for row in rows], ["True", "False"])

    def test_search_cues_follow_source_id_when_policies_reorder(self):
        manifest = json.loads((Path(__file__).resolve().parents[1] / "reddit/config/policy_batch_scope.json").read_text())
        original = {job["title"] + job["event_date"]: job["cue"] for job in build_search_jobs(manifest)}
        manifest["events"].reverse()
        reordered = {job["title"] + job["event_date"]: job["cue"] for job in build_search_jobs(manifest)}
        self.assertEqual(original, reordered)

    def test_merge_writes_final_files_outside_interim(self):
        with tempfile.TemporaryDirectory() as tmp:
            interim, final = Path(tmp) / "interim", Path(tmp) / "processed"
            interim.mkdir()
            (interim / "posts.jsonl").write_text(json.dumps({"event_id": "e1", "post_id": "p1",
                "raw_run_file": "run.json"}) + "\n")
            (interim / "comments.jsonl").write_text(json.dumps({"event_id": "e1", "post_id": "p1",
                "comment_id": "c1", "raw_run_file": "run.json"}) + "\n")
            result = merge_reviewed(interim, final)
            self.assertEqual(result["unique_policy_comment_pairs"], 1)
            self.assertTrue((final / "all_reviewed_comments.jsonl").exists())
            self.assertFalse((interim / "all_reviewed_comments.jsonl").exists())

    def test_sentiment_joins_parent_and_applies_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            processed, interim = root / "processed", root / "interim"
            processed.mkdir()
            (root / "manifest.json").write_text(json.dumps({"events": [{"event_id": "e1",
                "title": "Visa policy", "topic": "Visa interviews"}]}))
            (processed / "all_reviewed_posts.jsonl").write_text(json.dumps({"event_id": "e1",
                "post_id": "p1", "title": "Interview delays", "body": "A visa post", "post_url": "https://reddit.com/post"}) + "\n")
            (processed / "all_reviewed_comments.jsonl").write_text(json.dumps({"event_id": "e1",
                "post_id": "p1", "comment_id": "c1", "body": "Applicants need an interview."}) + "\n")
            overrides = root / "overrides.csv"
            overrides.write_text("event_id,post_id,comment_id,sentiment,review_note\n"
                                 "e1,p1,c1,neutral,Factual statement\n")
            with patch("reddit_scrapper._ollama_labels", return_value=[{"comment_id": "c1", "sentiment": "negative"}]):
                report = analyze_sentiment(root / "manifest.json", processed, interim, "test-model", 1, overrides)
            row = json.loads((processed / "comment_sentiment.jsonl").read_text().splitlines()[0])
            self.assertEqual((row["parent_post_title"], row["policy_topic"]), ("Interview delays", "Visa interviews"))
            self.assertEqual((row["model_sentiment"], row["sentiment"]), ("negative", "neutral"))
            self.assertEqual(report["labels_changed_by_audit"], 1)


if __name__ == "__main__":
    unittest.main()
