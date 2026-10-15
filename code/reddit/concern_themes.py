"""Transparent topic rules shared by YouTube and Reddit analyses."""
from __future__ import annotations
import re

THEME_PATTERNS = {
    "Visa status and screening": r"\b(?:visas?|revok\w*|status|f[ -]?1|consular|embass\w*|screen\w*|interview\w*)\b",
    "OPT, CPT and work authorization": r"\b(?:opt|cpt|ead|work permits?|work authori[sz]ation)\b",
    "H-1B and employment": r"\b(?:h[ -]?1b|sponsor\w*|employer\w*|jobs?|layoff\w*|careers?|hir\w*|employment)\b",
    "Travel and entry": r"\b(?:travel\w*|entry|airport\w*|borders?|bans?|deport\w*|re[ -]?entry)\b",
    "University and enrollment": r"\b(?:universit\w*|college\w*|campus|enroll\w*|admission\w*|degrees?|sevp)\b",
    "Financial pressure": r"\b(?:tuition|fees?|costs?|money|debts?|rents?|financ\w*|scholarships?)\b",
    "Safety and uncertainty": r"\b(?:afraid|fear\w*|anxi\w*|stress\w*|uncertain\w*|worr\w*|scared|unsafe|confus\w*)\b",
}


def comment_themes(value: object) -> list[str]:
    text = str(value or "").lower()
    return [name for name, pattern in THEME_PATTERNS.items() if re.search(pattern, text)] or ["Other discussion"]
