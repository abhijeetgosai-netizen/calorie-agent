"""USDA / Open Food Facts clients against mocked HTTP (shape of the real APIs)."""

import httpx

from calorie_agent.nutrition.off import OpenFoodFactsClient
from calorie_agent.nutrition.usda import USDAClient

USDA_PAYLOAD = {
    "foods": [
        {  # wrong food ranked first by the API — must be rejected by matching
            "description": "Chicken, rotisserie, original seasoning",
            "foodNutrients": [{"nutrientId": 1008, "value": 180, "unitName": "KCAL"}],
        },
        {
            "description": "Egg, whole, cooked, hard-boiled",
            "foodNutrients": [
                {"nutrientId": 1008, "value": 155, "unitName": "KCAL"},
                {"nutrientId": 1008, "value": 649, "unitName": "kJ"},
                {"nutrientId": 1003, "value": 12.6, "unitName": "G"},
                {"nutrientId": 1004, "value": 10.6, "unitName": "G"},
                {"nutrientId": 1005, "value": 1.12, "unitName": "G"},
            ],
        },
    ]
}

OFF_PAYLOAD = {
    "products": [
        {
            "product_name": "Greek yogurt plain",
            "nutriments": {
                "energy-kcal_100g": 97,
                "proteins_100g": 9,
                "carbohydrates_100g": 3.9,
                "fat_100g": 5,
            },
        },
    ]
}


def client(payload, seen=None):
    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(req)
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_usda_picks_matching_food_and_kcal_unit():
    seen = []
    m = await USDAClient("KEY", client(USDA_PAYLOAD, seen), 0.5).search("egg whole boiled")
    assert m is not None and m.match_name.startswith("Egg")
    assert m.per100g.kcal == 155 and m.per100g.protein_g == 12.6
    assert seen[0].url.params["api_key"] == "KEY"


async def test_usda_no_match_returns_none():
    assert await USDAClient("K", client(USDA_PAYLOAD), 0.5).search("chapati roti") is None


async def test_usda_http_error_returns_none():
    bad = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    assert await USDAClient("K", bad, 0.5).search("egg") is None


async def test_off_parses_nutriments():
    m = await OpenFoodFactsClient(client(OFF_PAYLOAD), 0.5).search("greek yogurt")
    assert m is not None and m.per100g.kcal == 97 and m.source == "off"
