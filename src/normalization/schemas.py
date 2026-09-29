"""Pydantic schemas for cross-judge score normalization and the Normalization Lab."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class JudgeStats(BaseModel):
    judge_id: str
    username: str
    evaluations_count: int
    mean_raw_score: float
    std_dev_raw_score: float
    min_raw_score: float
    max_raw_score: float
    is_zero_variance: bool
    status_label: str  # e.g., "Normal", "Zero Variance", "Harsh Grader", "Lenient Grader"


class ProjectJudgeScoreDetail(BaseModel):
    judge_id: str
    judge_username: str
    raw_score: float
    z_score: float
    normalized_score: float


class NormalizedProjectResult(BaseModel):
    project_id: str
    project_title: str
    team_name: str
    track_title: Optional[str] = None
    evaluations_count: int
    raw_score: float
    raw_rank: int
    normalized_z_score: float
    normalized_score: float
    normalized_rank: int
    rank_delta: int  # raw_rank - normalized_rank (positive = improved rank, negative = fell in rank)
    judge_details: List[ProjectJudgeScoreDetail] = []


class NormalizationLabResponse(BaseModel):
    event_id: str
    event_title: str
    total_projects: int
    total_evaluations: int
    global_mean_score: float
    global_std_dev: float
    judges_stats: List[JudgeStats]
    results: List[NormalizedProjectResult]
    algorithm_summary: Dict[str, Any]
