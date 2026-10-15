"""Pure metric functions (unit-tested in tests/test_eval_metrics.py)."""

from collections import Counter
from statistics import mean

from calorie_agent.nutrition.matching import tokens


def accuracy(pairs: list[tuple[str, str]]) -> float:
    return sum(p == e for p, e in pairs) / len(pairs) if pairs else 0.0


def confusion(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """{expected: {predicted: count}} — only the mistakes."""
    out: dict[str, Counter] = {}
    for pred, exp in pairs:
        if pred != exp:
            out.setdefault(exp, Counter())[pred] += 1
    return {k: dict(v) for k, v in out.items()}


def match_items(
    predicted: list[dict], expected: list[dict]
) -> tuple[list[tuple[dict, dict]], int, int]:
    """Greedy match by alias tokens in name/search_term. Returns (pairs, fp, fn)."""
    remaining = list(predicted)
    pairs = []
    for exp in expected:
        aliases = set().union(*(tokens(n) for n in exp["names"]))
        hit = next(
            (p for p in remaining if aliases & tokens(f"{p['name']} {p.get('search_term', '')}")),
            None,
        )
        if hit is not None:
            pairs.append((hit, exp))
            remaining.remove(hit)
    return pairs, len(remaining), len(expected) - len(pairs)


def f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0:
        return 0.0
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    return 2 * precision * recall / (precision + recall)


def ape(pred: float, true: float) -> float:
    """Absolute percentage error."""
    return abs(pred - true) / true if true else float("inf")


def mape(values: list[tuple[float, float]]) -> float:
    return mean(ape(p, t) for p, t in values) if values else float("inf")
