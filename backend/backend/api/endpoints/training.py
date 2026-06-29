"""Training dataset API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.services.training_dataset_service import get_training_dataset_service

router = APIRouter(prefix="/api/v1/training", tags=["training"])


@router.get("/dataset/summary")
async def get_training_dataset_summary() -> dict[str, Any]:
    """Return metadata about the loaded OSINT training dataset."""
    return get_training_dataset_service().get_summary()


@router.get("/dataset/examples/{example_id}")
async def get_training_dataset_example(example_id: int) -> dict[str, Any]:
    """Return one training example by example_id."""
    example = get_training_dataset_service().get_example(example_id)
    if example is None:
        raise HTTPException(status_code=404, detail="Training example not found")
    return example
