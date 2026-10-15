"""Intent classification accuracy + guardrail refusal rate."""

import asyncio

import pytest

from evals.conftest import CONCURRENCY, THRESHOLDS, load, save_result
from evals.metrics import accuracy, confusion

pytestmark = pytest.mark.eval


async def _classify_all(llm, texts: list[str]) -> list[str]:
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(t: str) -> str:
        async with sem:
            return (await llm.classify(t)).intent

    return await asyncio.gather(*(one(t) for t in texts))


async def test_intent_accuracy(real_llm):
    rows = load("intents")
    preds = await _classify_all(real_llm, [r["text"] for r in rows])
    pairs = list(zip(preds, [r["intent"] for r in rows], strict=True))
    acc = accuracy(pairs)
    details = [
        {"text": r["text"], "expected": r["intent"], "predicted": p}
        for r, p in zip(rows, preds, strict=True)
        if p != r["intent"]
    ]
    path = save_result("intents", {"accuracy": acc, "confusion": confusion(pairs)}, details)
    assert acc >= THRESHOLDS["intent_accuracy"], f"accuracy {acc:.1%}; see {path}"


async def test_guardrails_refuse(real_llm):
    rows = load("guardrails")
    preds = await _classify_all(real_llm, [r["text"] for r in rows])
    ok = [p in r["allowed"] for r, p in zip(rows, preds, strict=True)]
    rate = sum(ok) / len(ok)
    details = [
        {"text": r["text"], "allowed": r["allowed"], "predicted": p}
        for r, p, good in zip(rows, preds, ok, strict=True)
        if not good
    ]
    path = save_result("guardrails", {"refusal_rate": rate}, details)
    assert rate >= THRESHOLDS["guardrail_refusal_rate"], f"refusal {rate:.1%}; see {path}"
