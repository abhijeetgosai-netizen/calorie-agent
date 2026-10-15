from evals.metrics import accuracy, confusion, f1, mape, match_items


def test_accuracy_and_confusion():
    pairs = [("log_food", "log_food"), ("help", "off_topic"), ("help", "off_topic")]
    assert accuracy(pairs) == 1 / 3
    assert confusion(pairs) == {"off_topic": {"help": 2}}


def test_match_items_uses_aliases_and_search_term():
    pred = [
        {"name": "chawal", "search_term": "rice white cooked", "grams": 150},
        {"name": "pickle", "search_term": "pickle", "grams": 10},
    ]
    exp = [{"names": ["rice"], "grams": 160}, {"names": ["dal"], "grams": 200}]
    pairs, fp, fn = match_items(pred, exp)
    assert len(pairs) == 1 and fp == 1 and fn == 1
    assert f1(1, 1, 1) == 0.5


def test_mape():
    assert abs(mape([(110, 100), (90, 100)]) - 0.10) < 1e-9
