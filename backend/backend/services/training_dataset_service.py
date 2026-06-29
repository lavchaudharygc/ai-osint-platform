"""AI training dataset loader for OSINT correlation examples."""

from functools import lru_cache
from pathlib import Path
from typing import Any
import json

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_CANDIDATES = [
    REPO_ROOT / "final osint .json",
    REPO_ROOT / "final osint.json",
    REPO_ROOT / "final_osint.json",
    REPO_ROOT / "backend" / "data" / "ai_training" / "final_osint.json",
]


class TrainingDatasetService:
    """Load and summarize OSINT teammate training examples from JSON."""

    def __init__(self, dataset_path: Path | None = None) -> None:
        self.dataset_path = dataset_path or self.find_dataset_path()

    @staticmethod
    def find_dataset_path() -> Path | None:
        for path in DATASET_CANDIDATES:
            if path.exists():
                return path
        return None

    def is_configured(self) -> bool:
        return self.dataset_path is not None and self.dataset_path.exists()

    def load_examples(self) -> list[dict[str, Any]]:
        if not self.is_configured():
            return []
        with self.dataset_path.open(encoding="utf-8") as dataset_file:
            data = json.load(dataset_file)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            examples = data.get("examples") or data.get("data") or data.get("items") or []
            if isinstance(examples, list):
                return [item for item in examples if isinstance(item, dict)]
        return []

    def get_summary(self) -> dict[str, Any]:
        examples = self.load_examples()
        categories = sorted({str(example.get("category")) for example in examples if example.get("category")})
        confidence_tiers = sorted(
            {str(example.get("confidence_tier")) for example in examples if example.get("confidence_tier")}
        )
        return {
            "configured": self.is_configured(),
            "dataset_path": str(self.dataset_path.relative_to(REPO_ROOT)) if self.dataset_path else None,
            "total_examples": len(examples),
            "categories": categories,
            "confidence_tiers": confidence_tiers,
        }

    def get_example(self, example_id: int) -> dict[str, Any] | None:
        for example in self.load_examples():
            if example.get("example_id") == example_id:
                return example
        return None

    def find_examples_for_category(self, category: str, limit: int = 3) -> list[dict[str, Any]]:
        normalized = category.lower().strip()
        matches = [
            example
            for example in self.load_examples()
            if normalized in str(example.get("category", "")).lower()
        ]
        return matches[:limit]

    def build_correlation_context(self, positive_match_count: int) -> dict[str, Any]:
        category = "SAME USERNAME - SAME PERSON" if positive_match_count else "NO MATCH / LOW CONFIDENCE"
        examples = self.find_examples_for_category(category, limit=2)
        return {
            "dataset": self.get_summary(),
            "suggested_category": category,
            "reference_example_ids": [example.get("example_id") for example in examples],
        }


@lru_cache
def get_training_dataset_service() -> TrainingDatasetService:
    return TrainingDatasetService()
