import unittest

from backend.services.investigation_policy import (
    InvestigationResultCache,
    ProviderCallBudget,
    ProviderCallLimitExceeded,
    request_cache_key,
)


class ProviderCallBudgetTests(unittest.TestCase):
    def test_reservations_are_atomic_and_expose_remaining_budget(self) -> None:
        budget = ProviderCallBudget(maximum=3)
        budget.reserve("social.instagram", 2)

        with self.assertRaises(ProviderCallLimitExceeded):
            budget.reserve("search.serpapi", 2)

        self.assertEqual(budget.used, 2)
        self.assertEqual(budget.remaining, 1)
        self.assertEqual(budget.snapshot()["skipped"][0]["capability"], "search.serpapi")

    def test_try_reserve_does_not_raise(self) -> None:
        budget = ProviderCallBudget(maximum=1)

        self.assertTrue(budget.try_reserve("github", 1))
        self.assertFalse(budget.try_reserve("phone", 1))


class InvestigationResultCacheTests(unittest.TestCase):
    def test_cache_returns_a_copy_and_uses_stable_hashed_keys(self) -> None:
        cache = InvestigationResultCache(ttl_seconds=60, max_entries=2)
        key = request_cache_key({"username": "target", "platform": "github"})
        original = {"results": [1]}
        cache.set(key, original)

        hit = cache.get(key)
        self.assertIsNotNone(hit)
        hit.value["results"].append(2)

        second = cache.get(key)
        self.assertEqual(second.value, {"results": [1]})
        self.assertEqual(len(key), 64)
        self.assertNotIn("target", key)

    def test_disabled_cache_never_stores(self) -> None:
        cache = InvestigationResultCache(ttl_seconds=0, max_entries=1)
        cache.set("key", {"value": 1})

        self.assertIsNone(cache.get("key"))


if __name__ == "__main__":
    unittest.main()
