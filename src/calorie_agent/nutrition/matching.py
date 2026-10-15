"""Decide whether a database search hit actually matches what the user ate."""

import re

_STOP = {"and", "or", "with", "the", "a", "of", "raw", "cooked", "ns", "nfs", "as", "to", "in"}


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    out = set()
    for w in words:
        if w in _STOP or len(w) < 2:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 3 else w)  # naive singularize
    return out


def match_score(query: str, candidate: str) -> float:
    """Fraction of query tokens present in the candidate description (0..1)."""
    q, c = tokens(query), tokens(candidate)
    if not q:
        return 0.0
    return len(q & c) / len(q)


def best_match(query: str, candidates: list[str], threshold: float) -> int | None:
    """Index of the best candidate above threshold; ties keep the earlier (higher-ranked) one."""
    best_i, best_s = None, threshold - 1e-9
    for i, cand in enumerate(candidates):
        s = match_score(query, cand)
        if s > best_s:
            best_i, best_s = i, s
    return best_i
