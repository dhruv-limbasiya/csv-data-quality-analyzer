from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List
import logging

from app.database import get_db
from app.models.user import User
from app.models.dataset import Dataset
from app.models.analysis import Analysis
from app.auth import get_current_user
from app.schemas.analysis import (
    AnalysisResponse,
    AnalysisListResponse,
)
from app.services.quality_service import analyze_dataset_quality

logger = logging.getLogger("csv_analyzer.analyses")

router = APIRouter(tags=["Quality Analysis"])


@router.post(
    "/api/datasets/{dataset_id}/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run data quality analysis on a dataset",
    description="Analyzes an uploaded dataset for missing values, duplicates, format errors, statistics, and computes a composite quality score.",
)
def run_dataset_analysis(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Execute quality analysis against an authorized dataset and persist the results."""
    # 1. Verify dataset exists
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} was not found."
        )

    # 2. Verify ownership
    if dataset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this dataset."
        )

    # 3. Verify source file exists on disk
    file_path = Path(dataset.file_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source CSV file for dataset {dataset_id} was not found on disk."
        )

    # 4. Perform analysis without modifying source file
    try:
        results = analyze_dataset_quality(file_path, dataset.file_size_bytes)
    except Exception as exc:
        logger.error(f"Error analyzing dataset {dataset_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze dataset: {str(exc)}"
        )

    # 5. Persist analysis results in PostgreSQL
    analysis = Analysis(
        dataset_id=dataset.id,
        user_id=current_user.id,
        overall_score=results["overall_score"],
        summary_stats=results["summary_stats"],
        column_scores=results["column_scores"],
        issues=results["issues"],
        recommendations=results["recommendations"],
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    logger.info(
        f"Analysis id={analysis.id} completed for dataset id={dataset.id} "
        f"(score={analysis.overall_score}, {len(analysis.issues)} issues detected)"
    )

    return AnalysisResponse.model_validate(analysis)


@router.get(
    "/api/datasets/{dataset_id}/analyses",
    response_model=AnalysisListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get all analyses for a dataset",
    description="Returns analysis history for a specific dataset owned by the current user.",
)
def get_dataset_analyses(
    dataset_id: int,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve historical quality analyses for an authorized dataset, with pagination."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} was not found."
        )

    if dataset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this dataset."
        )

    base_query = db.query(Analysis).filter(Analysis.dataset_id == dataset.id)
    total = base_query.count()
    analyses = (
        base_query
        .order_by(Analysis.created_at.desc())
        .offset(max(0, skip))
        .limit(max(1, min(100, limit)))
        .all()
    )

    return AnalysisListResponse(total=total, items=analyses)


@router.get(
    "/api/analyses/{analysis_id}",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a specific analysis by ID",
    description="Retrieves a complete analysis record by ID. Verifies ownership through the associated user and dataset.",
)
def get_analysis_by_id(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve an individual analysis record by ID, enforcing user ownership."""
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with ID {analysis_id} was not found."
        )

    if analysis.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this analysis."
        )

    return AnalysisResponse.model_validate(analysis)
