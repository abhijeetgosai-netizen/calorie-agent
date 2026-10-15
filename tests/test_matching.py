from calorie_agent.nutrition.matching import best_match, match_score


def test_exact_tokens_score_high():
    assert match_score("egg whole boiled", "Egg, whole, cooked, hard-boiled") >= 2 / 3


def test_wrong_food_rejected():
    # The classic failure: "roti" must not match rotisserie chicken.
    assert best_match("chapati roti", ["Chicken, rotisserie, meat only"], 0.5) is None


def test_picks_best_candidate():
    cands = ["Rice crackers", "Rice, white, long-grain, cooked", "Cake"]
    assert best_match("rice white cooked", cands, 0.5) == 1
