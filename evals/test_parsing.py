"""Food extraction quality: item F1 and portion (grams) error."""

import asyncio

import pytest

from evals.conftest import CONCURRENCY, THRESHOLDS, load, save_result
from evals.metrics import ape, f1, match_items

pytestmark = pytest.mark.eval


async def test_parsing(real_llm):
    rows = load("parsing")
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(text: str):
        async with sem:
            return await real_llm.parse_meal(text, allow_clarification=False)

    meals = await asyncio.gather(*(one(r["text"]) for r in rows))
    tp = fp = fn = 0
    gram_errors, details = [], []
    for row, meal in zip(rows, meals, strict=True):
        pred = [i.model_dump() for i in meal.items]
        pairs, row_fp, row_fn = match_items(pred, row["items"])
        tp, fp, fn = tp + len(pairs), fp + row_fp, fn + row_fn
        errs = [ape(p["grams"], e["grams"]) for p, e in pairs]
        gram_errors += errs
        if row_fp or row_fn or any(e > THRESHOLDS["parse_grams_mape"] for e in errs):
            details.append({"text": row["text"], "expected": row["items"], "predicted": pred})
    score = f1(tp, fp, fn)
    grams_mape = sum(gram_errors) / len(gram_errors) if gram_errors else float("inf")
    path = save_result(
        "parsing", {"f1": score, "tp": tp, "fp": fp, "fn": fn, "grams_mape": grams_mape}, details
    )
    assert score >= THRESHOLDS["parse_f1"], f"F1 {score:.2f}; see {path}"
    assert grams_mape <= THRESHOLDS["parse_grams_mape"], f"grams MAPE {grams_mape:.1%}; see {path}"
