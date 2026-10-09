"""Build the list of policy events for any date range.
Usage:
    # Serve a model first, e.g.:  vllm serve Qwen/Qwen2.5-14B-Instruct-AWQ --port 8000
    python build_review_list.py --start 2025-01-20 --end 2026-10-01 --model Qwen/Qwen2.5-14B-Instruct-AWQ
"""

import argparse
import csv
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import requests

from fetch_federal_register import fetch_federal_register
from fetch_state_department import fetch_state_department
from build_event_windows import LIST_COLUMNS, window_columns
from find_earliest_signal import add_signals

# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

STOPWORDS = set("a an and the of to for from in on by with at certain united states u s".split())


def title_words(title):
    words = re.findall(r"[a-z0-9]+", title.lower())
    # Crude stemming so "restricting"/"restriction" and "workers"/"worker" match.
    return {re.sub(r"(ing|ion|s)$", "", w) for w in words if w not in STOPWORDS}


def link_same_events(rows, max_days=10, min_overlap=0.4):
    """Set `same_event_as` on State Department rows that match a Federal
    Register row: dates within max_days and similar titles."""
    fr = [r for r in rows if r["source"] == "Federal Register"]
    for r in rows:
        r.setdefault("same_event_as", "")
        if r["source"] == "Federal Register" or not r["event_date"]:
            continue
        day, words = date.fromisoformat(r["event_date"]), title_words(r["title"])
        best, best_score = None, min_overlap
        for f in fr:
            if abs(date.fromisoformat(f["event_date"]) - day) > timedelta(days=max_days):
                continue
            other = title_words(f["title"])
            score = len(words & other) / len(words | other) if words | other else 0
            if score >= best_score:
                best, best_score = f, score
        if best:
            r["same_event_as"], best["same_event_as"] = best["source_id"], r["source_id"]


def merge(fr_rows, sd_rows, start, end):
    """Both sources' rows inside the date range, sorted by date, with the same
    event in both sources linked."""
    rows = sorted((dict(r) for r in fr_rows + sd_rows if start <= r["event_date"] <= end), key=lambda r: r["event_date"])
    link_same_events(rows)
    return rows


# ---------------------------------------------------------------------------
# Rule screen
# ---------------------------------------------------------------------------

# Titles of documents that concern other visa programs or are operational notices; none of them change rules for students.
OFF_TOPIC_TITLE = re.compile(
    r"diversity|eb-5|fifth preference|h-2a|h-2b|asylum|parole|naturaliz|immigrant visa \(iv\)|"
    r"immigrant visa processing|public benefits|premium processing|e-filing|lightering|"
    r"alien registration|visa bond|pause of routine|pause of visa|limited (?:visa )?services|"
    r"working group|annual limit|per-country limit|birth tourism|correction",
    re.I,
)
STUDENT_TERMS = re.compile(
    r"\b[fjm]-1\b|\bf, m,? (?:and|or) j\b|\bstudents?\b|duration of status|exchange visitor|sevis|"
    r"interview waiver|waivers? of the (?:nonimmigrant visa )?interview|country of (?:nationality or )?residence|"
    r"online presence|screening and vetting|practical training",
    re.I,
)


def rule_screen(r):
    """Return (keep, note). keep=False rows never reach the LLM."""
    if r["source"] != "Federal Register" and r["same_event_as"]:
        return False, f"same event as Federal Register document {r['same_event_as']}"
    if r["source_id"].startswith("C") or "correction" in r["title"].lower():
        return False, "correction to another document"
    if OFF_TOPIC_TITLE.search(r["title"]):
        return False, "other visa program or operational notice"
    if r["auto_tier"] == "exclude":
        return False, f"automatic screen: {r['auto_reason']}"
    return True, ""


def rule_hint(r):
    """Rule-based guess at the group, used without the LLM and to flag disagreements."""
    student = r["student_hits"] + r["fj_visa_hits"] + r["opt_sevis_hits"]
    if "h-1b" in r["title"].lower() or r["h1b_hits"] >= 20:
        return "work_pathway"
    if STUDENT_TERMS.search(f"{r['title']} {r['summary']}") or student >= 10:
        return "student_rules"
    return ""


# ---------------------------------------------------------------------------
# LLM screen
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You screen U.S. government documents for a research project on how U.S. policy changes \
affect international students (especially Indian students) and what they say online about studying in the U.S.

Put the document in one group:
- student_rules (relevant): changes, announces, or enforces rules for F-1/J-1/M-1 students or applicants. \
This includes student visa applications; social-media or other vetting of student applicants; visa interview rules \
that apply to all nonimmigrant applicants (interview waivers, where applicants must interview), because students \
apply through them; entry or travel bans that suspend F or J visas for some countries; duration of status or length \
of stay; SEVIS/SEVP; actions against a university's international students; visa revocations aimed at students.
- work_pathway (relevant): OPT, CPT, STEM OPT, and H-1B. Every H-1B rule, proclamation, or notice is relevant \
(lottery, fees, wages, vetting, entry restrictions, grace periods) even if it never mentions students, because \
H-1B is the main route for international graduates to work in the U.S.
- background (not relevant): affects all foreigners and students only incidentally, such as biometrics at the \
border, general vetting orders with no visa-specific rules, public charge (green card) rules, or revocation statistics.
- none (not relevant): other visa programs (diversity lottery, EB-5, H-2A/H-2B, asylum, parole, B-1/B-2-only \
rules); work permits for other groups unless the text mentions OPT or F-1 students; embassy-specific operational \
pauses; sanctions on named officials; routine fee inflation adjustments; corrections.

relevant: "yes" for student_rules or work_pathway, "no" for background or none. Use "unsure" only when the text \
is missing (title only) or truly ambiguous.

india_relevance:
- "direct": H-1B, OPT/STEM OPT, and visa interview scheduling or waiver rules (Indian applicants are the largest \
group affected).
- "indirect": other rules that apply to international students in general.
- "none": India is not covered (e.g. a country list that does not include India), or the document is not relevant.

Examples:
- Proclamation requiring a large payment for new H-1B petitions -> yes, work_pathway, direct.
- Proclamation suspending B, F, M and J visas for nationals of listed countries (India not listed) -> yes, \
student_rules, none.
- Notice that most nonimmigrant visa applicants now need an in-person interview -> yes, student_rules, direct.
- Rule ending automatic extensions of work permits, with no mention of OPT or students -> no, none, none.
- Rule requiring photographs of all foreigners entering and leaving at airports -> no, background, indirect.

The text is an excerpt: the opening of the document, then passages around mentions of students, F/J visas, \
H-1B, and India, separated by " ... ".

Answer with JSON only:
{"relevant": "yes" | "no" | "unsure",
 "group": "student_rules" | "work_pathway" | "background" | "none",
 "india_relevance": "direct" | "indirect" | "none",
 "reason": "<one sentence, citing what the document does>"}"""

ALLOWED = {
    "relevant": {"yes", "no", "unsure"},
    "group": {"student_rules", "work_pathway", "background", "none"},
    "india_relevance": {"direct", "indirect", "none"},
}
FAILED = "LLM request failed"

# Passages around these terms are what the model needs to see in long documents
# (e.g. the F/J suspension sections of a travel-ban proclamation).
KEY_TERMS = re.compile(r"\b[fjm]-1\b|\b[fj] visas?\b|\bf, m,? (?:and|or) j\b|\bstudents?\b|exchange visitor|"
                       r"practical training|duration of status|\bsevis\b|\bh-1b\b|\bindia\b", re.I)


def document_text(r):
    """Federal Register: the full text from the summary or proclamation body
    onward (the abstract if the full text was not downloaded). State
    Department: the page text."""
    text = r["text"] or r["summary"] or ""
    if r["source"] == "Federal Register" and r["text"]:
        starts = [i for i in (text.find("SUMMARY:"), text.find("By the authority vested")) if i >= 0]
        text = text[min(starts):] if starts else text
    return " ".join(text.split())


def excerpt(r, limit=3500, head=800, window=250):
    """The opening of the document plus passages around KEY_TERMS, up to about
    `limit` characters."""
    text = document_text(r)
    if len(text) <= limit:
        return text
    parts, covered = [text[:head]], head
    for m in KEY_TERMS.finditer(text):
        if m.start() < covered:
            continue
        start, end = max(covered, m.start() - window), m.end() + window
        parts.append(text[start:end])
        covered = end
        if sum(map(len, parts)) >= limit:
            break
    return " ... ".join(parts)


def user_prompt(r):
    return (f"Source: {r['source']} ({r['doc_type']})\nDate: {r['event_date']}\nTitle: {r['title']}\n\n"
            f"Text excerpt:\n{excerpt(r)}")


def parse_answer(content):
    """Pull the JSON object out of a model reply and normalise its fields."""
    content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S)
    m = re.search(r"\{.*\}", content, re.S)
    data = json.loads(m.group(0)) if m else {}
    answer = {k: str(data.get(k, "")).strip().lower() for k in ALLOWED}
    for k, allowed in ALLOWED.items():
        if answer[k] not in allowed:
            answer[k] = "unsure" if k == "relevant" else ""
    answer["reason"] = str(data.get("reason", "")).strip() or "(no reason given)"
    return answer


class LLMScreen:
    def __init__(self, url, model, concurrency, disable_thinking, api_key="EMPTY"):
        self.url = url.rstrip("/") + "/chat/completions"
        self.model, self.api_key = model, api_key
        self.concurrency, self.disable_thinking = concurrency, disable_thinking
        self.json_mode = True

    def chat(self, system, user, max_tokens=300):
        """One chat request; returns the reply text. Raises after 4 failed tries."""
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.disable_thinking:  # Qwen3 thinking models (vLLM / SGLang chat template switch)
            body["chat_template_kwargs"] = {"enable_thinking": False}
        headers = {"Authorization": f"Bearer {self.api_key}"}

        for attempt in range(4):
            try:
                resp = requests.post(self.url, json=body, headers=headers, timeout=300)
                if resp.status_code == 400 and "response_format" in body:
                    # Some servers don't support response_format; fall back to plain text.
                    self.json_mode = False
                    body.pop("response_format")
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except (requests.RequestException, KeyError, ValueError):
                if attempt == 3:
                    raise
                time.sleep(2 * 2 ** attempt)

    def ask(self, r):
        """Screen one document; a failed request comes back flagged, not raised."""
        try:
            return parse_answer(self.chat(SYSTEM_PROMPT, user_prompt(r)))
        except (requests.RequestException, KeyError, ValueError) as err:
            return {"relevant": "unsure", "group": "", "india_relevance": "", "reason": f"{FAILED}: {err}"}

    def screen(self, rows):
        """Return {source_id: answer} for the rows, asking in parallel."""
        print(f"LLM screen: sending {len(rows)} documents ({self.concurrency} in parallel to {self.url})")
        answers = {}
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {pool.submit(self.ask, r): r for r in rows}
            for done, fut in enumerate(as_completed(futures), 1):
                answers[futures[fut]["source_id"]] = fut.result()
                if done % 10 == 0 or done == len(rows):
                    print(f"  {done}/{len(rows)}")
        return answers


# ---------------------------------------------------------------------------
# The list to verify
# ---------------------------------------------------------------------------

OUT_COLUMNS = LIST_COLUMNS  # defined in build_event_windows.py
# earliest_signal / signal_source: found by find_earliest_signal.py or entered by hand; topic: corrected by hand
KEPT_BY_HAND = ["verified", "notes", "earliest_signal", "signal_source", "topic"]


def decide(r, answer):
    """Return (include, group, why_listed) for one rule-screened candidate."""
    hint = rule_hint(r)
    if answer["reason"].startswith(FAILED):
        return True, hint, "LLM request failed; check"
    group = answer["group"] if answer["group"] not in ("", "none") else hint
    if answer["relevant"] == "yes" and answer["group"] != "background":
        return True, group, "LLM: relevant"
    if answer["relevant"] == "unsure":
        return True, group, "LLM unsure; check"
    if hint:
        # Keep anything the rules call student-related, even when the LLM calls it
        # background: the LLM has been inconsistent on notices like interview waivers.
        return True, hint, f"rules say relevant, LLM says {answer['group'] or 'not'}; check"
    return False, group, ""


# Titles of notices on visa interviews (waivers, where to apply); Indian
# applicants face the longest interview waits, so these are direct.
INTERVIEW_TITLE = re.compile(r"interview|country of (?:nationality or )?residence", re.I)


def india_relevance(r, group, answer):
    """Rules decide the clear cases (the LLM labelled almost everything
    "indirect"); the LLM's label is used for the rest."""
    if group == "work_pathway" or (group == "student_rules" and INTERVIEW_TITLE.search(r["title"])):
        return "direct"
    return answer["india_relevance"]


def screen_documents(docs, llm):
    """Rule screen, then the LLM. Returns (every document with its decisions,
    the listed documents)."""
    rows = [dict(d) for d in docs]
    for r in rows:
        r["rule_keep"], r["rule_note"] = rule_screen(r)
        r["rule_hint"] = rule_hint(r)
    candidates = [r for r in rows if r["rule_keep"]]
    print(f"Rule screen: {len(candidates)} of {len(rows)} documents go to the LLM")

    answers = llm.screen(candidates)
    blank = {"relevant": "", "group": "", "india_relevance": "", "reason": ""}
    listed = []
    for r in rows:
        a = answers.get(r["source_id"], blank)
        include, group, why = decide(r, a) if r["rule_keep"] else (False, "", "")
        r.update(llm_relevant=a["relevant"], llm_group=a["group"], llm_reason=a["reason"],
                 india_relevance=india_relevance(r, group, a), group=group, why_listed=why, listed=include)
        if include:
            listed.append(r)
    return rows, listed


def write_review_list(listed, out_path, stop, llm=None):
    """Write the listed events with their analysis windows (ending at `stop`),
    keeping the columns filled in by hand on an earlier version of out_path.
    With an LLM, policies without an earliest_signal are searched in the news."""
    existing = {}
    if out_path.exists():
        with out_path.open(newline="", encoding="utf-8-sig") as f:
            existing = {r["source_id"]: r for r in csv.DictReader(f)}
    for r in listed:
        for col in KEPT_BY_HAND:
            r[col] = existing.get(r["source_id"], {}).get(col, "")
    if llm:
        add_signals(listed, llm)
    for r in listed:
        r.update(window_columns(r, stop))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:  # -sig so Excel reads UTF-8
        w = csv.DictWriter(f, fieldnames=OUT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(listed)
    flagged = sum("check" in r["why_listed"] for r in listed)
    print(f"{len(listed)} events to verify ({flagged} flagged for a closer look) -> {out_path}")
    if any(FAILED in r["why_listed"] for r in listed):
        print("  Some LLM requests failed; they are listed and flagged. Rerun to retry them.")


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", default="2025-01-20", help="earliest date (YYYY-MM-DD)")
    parser.add_argument("--end", default=date.today().isoformat(), help="latest date (YYYY-MM-DD); default: today")
    parser.add_argument("--llm-url", default=os.environ.get("LLM_URL", "http://localhost:8000/v1"),
                        help="OpenAI-compatible base URL (vLLM default :8000/v1, Ollama :11434/v1)")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"),
                        help="model name as the server knows it")
    parser.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", "EMPTY"))
    parser.add_argument("--concurrency", type=int, default=16, help="parallel LLM requests")
    parser.add_argument("--disable-thinking", action="store_true", help="turn off Qwen3 thinking mode")
    parser.add_argument("--out", default=str(root / "data" / "processed" / "policy_events_to_verify.csv"))
    args = parser.parse_args()

    docs = merge(fetch_federal_register(args.start, args.end), fetch_state_department(args.start, args.end),
                 args.start, args.end)
    llm = LLMScreen(args.llm_url, args.model, args.concurrency, args.disable_thinking, args.api_key)
    rows, listed = screen_documents(docs, llm)
    write_review_list(listed, Path(args.out), date.fromisoformat(args.end), llm)


if __name__ == "__main__":
    main()
