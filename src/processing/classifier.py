"""Heuristic content-type classifier for parsed emails."""

import re

from src.models import ContentType, ParsedEmail

# Domain / URL patterns
_PAPER_DOMAINS = {"arxiv.org", "openreview.net", "aclanthology.org", "semanticscholar.org"}
_COURSE_DOMAINS = {"coursera.org", "edx.org", "udemy.com", "fast.ai", "deeplearning.ai"}
_TOOL_DOMAINS = {
    "github.com",
    "huggingface.co",
    "pypi.org",
    "npmjs.com",
    "gitlab.com",
}

# Keyword patterns for subject / body matching
_PAPER_KEYWORDS = re.compile(
    r"\b(arxiv|paper|preprint|abstract|proceedings|journal|survey|benchmark|dataset)\b",
    re.IGNORECASE,
)
_TUTORIAL_KEYWORDS = re.compile(
    r"\b(tutorial|how.?to|guide|walkthrough|step.by.step|introduction to|getting started)\b",
    re.IGNORECASE,
)
_COURSE_KEYWORDS = re.compile(
    r"\b(course|curriculum|lecture|lesson|module|enroll|certificate|bootcamp)\b",
    re.IGNORECASE,
)
_NEWS_KEYWORDS = re.compile(
    r"\b(news|announce|launch|release|update|week in|weekly|digest|roundup|highlights)\b",
    re.IGNORECASE,
)
_TOOL_KEYWORDS = re.compile(
    r"\b(library|framework|tool|sdk|api|package|repo|repository|open.?source|cli|install)\b",
    re.IGNORECASE,
)


def _score(text: str, subject: str, link_domains: set[str]) -> dict[ContentType, int]:
    """Return a score for each ContentType."""
    scores: dict[ContentType, int] = {ct: 0 for ct in ContentType if ct != ContentType.UNKNOWN}

    # Domain-based signals (high confidence)
    if link_domains & _PAPER_DOMAINS:
        scores[ContentType.PAPER] += 3
    if link_domains & _COURSE_DOMAINS:
        scores[ContentType.COURSE] += 3
    if link_domains & _TOOL_DOMAINS:
        scores[ContentType.TOOL] += 2

    # Keyword signals
    combined = f"{subject} {text[:2000]}"
    if _PAPER_KEYWORDS.search(combined):
        scores[ContentType.PAPER] += 2
    if _TUTORIAL_KEYWORDS.search(combined):
        scores[ContentType.TUTORIAL] += 2
    if _COURSE_KEYWORDS.search(combined):
        scores[ContentType.COURSE] += 2
    if _NEWS_KEYWORDS.search(combined):
        scores[ContentType.NEWS] += 2
    if _TOOL_KEYWORDS.search(combined):
        scores[ContentType.TOOL] += 1

    return scores


def classify(parsed: ParsedEmail) -> ContentType:
    """Assign a ContentType to a parsed email using heuristic rules.

    Args:
        parsed: A ParsedEmail with clean text and extracted links.

    Returns:
        The best-matching ContentType, or UNKNOWN if no signal is found.
    """
    link_domains = {link.domain for link in parsed.links}
    subject = parsed.raw_email.subject

    scores = _score(parsed.clean_text, subject, link_domains)

    best_type = max(scores, key=lambda ct: scores[ct])
    if scores[best_type] == 0:
        return ContentType.UNKNOWN

    return best_type
