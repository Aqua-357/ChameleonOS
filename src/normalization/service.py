"""Cross-judge score normalization service.

Implements a deterministic, mathematically documented normalization algorithm:
1. Criterion-weighted raw score aggregation per judge-project pair.
2. Individual judge distribution calibration (mean and standard deviation).
3. Zero-variance handling (judges who score every project identically get z = 0.0).
4. Standardized z-score calculation with global benchmark rescaling.
5. Unequal judge count handling via standardized sample aggregation.
6. Deterministic tie-breaking hierarchy.
7. Rank shift (delta) tracking between raw and normalized distributions.
"""

import math
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.events.models import Event
from src.judging.models import JudgeScore, Rubric, RubricCriterion
from src.judging.service import get_or_create_default_rubric
from src.normalization.schemas import (
    JudgeStats,
    NormalizationLabResponse,
    NormalizedProjectResult,
    ProjectJudgeScoreDetail,
)
from src.submissions.models import Project


EPSILON = 1e-6


def calculate_normalization(db: Session, event_id: str) -> NormalizationLabResponse:
    """
    Execute full cross-judge score normalization for an event.
    Deterministic, transparent, and handles all edge cases.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    rubric = get_or_create_default_rubric(db, event_id)
    criteria_weights = {c.id: float(c.weight) for c in rubric.criteria}

    # Fetch submitted projects for this event
    projects = db.query(Project).filter(
        Project.event_id == event_id,
        Project.is_submitted.is_(True),
    ).order_by(Project.id).all()

    # Fetch all non-null scores for these projects
    project_ids = [p.id for p in projects]
    scores = db.query(JudgeScore).filter(
        JudgeScore.project_id.in_(project_ids),
        JudgeScore.score.isnot(None),
    ).all() if project_ids else []

    # --------------------------------------------------------------------------
    # Step 1: Compute Raw Weighted Project Score per (judge, project) pair: R_{j, p}
    # --------------------------------------------------------------------------
    # Group scores by (judge_id, project_id)
    judge_project_scores: Dict[Tuple[str, str], List[JudgeScore]] = {}
    for s in scores:
        key = (s.judge_id, s.project_id)
        if key not in judge_project_scores:
            judge_project_scores[key] = []
        judge_project_scores[key].append(s)

    # Calculate weighted score for each (judge_id, project_id)
    raw_evaluations: Dict[Tuple[str, str], float] = {}
    judge_to_scores: Dict[str, List[float]] = {}
    all_raw_eval_scores: List[float] = []

    for (jid, pid), s_list in judge_project_scores.items():
        weighted_sum = 0.0
        total_weight = 0.0
        for s in s_list:
            w = criteria_weights.get(s.criterion_id, 1.0)
            weighted_sum += float(s.score) * w
            total_weight += w

        r_jp = (weighted_sum / total_weight) if total_weight > 0 else 0.0
        raw_evaluations[(jid, pid)] = r_jp
        all_raw_eval_scores.append(r_jp)

        if jid not in judge_to_scores:
            judge_to_scores[jid] = []
        judge_to_scores[jid].append(r_jp)

    # Global population parameters
    if all_raw_eval_scores:
        global_mean = sum(all_raw_eval_scores) / len(all_raw_eval_scores)
        global_variance = sum((x - global_mean) ** 2 for x in all_raw_eval_scores) / len(all_raw_eval_scores)
        global_std = math.sqrt(global_variance)
        if global_std < EPSILON:
            global_std = 1.5  # Fallback standard deviation if all judges scored identically
    else:
        global_mean = 5.0
        global_std = 1.5

    # --------------------------------------------------------------------------
    # Step 2: Calibrate Each Judge's Distribution (Mean, Std Dev, Variance)
    # --------------------------------------------------------------------------
    judge_stats_map: Dict[str, Dict[str, Any]] = {}
    judge_stats_list: List[JudgeStats] = []

    # Map judge_id to username
    judge_users = {s.judge_id: s.judge.username if s.judge else s.judge_id for s in scores}

    for jid, j_scores in judge_to_scores.items():
        k = len(j_scores)
        mu_j = sum(j_scores) / k
        var_j = sum((x - mu_j) ** 2 for x in j_scores) / k
        sigma_j = math.sqrt(var_j)

        is_zero_variance = (sigma_j < EPSILON) or (k <= 1)

        # Grader persona classification
        if is_zero_variance:
            status_label = "Zero Variance (Uniform)"
        elif mu_j < (global_mean - 0.75 * global_std):
            status_label = "Harsh Grader"
        elif mu_j > (global_mean + 0.75 * global_std):
            status_label = "Lenient Grader"
        else:
            status_label = "Well-Calibrated"

        stats_dict = {
            "judge_id": jid,
            "username": judge_users.get(jid, jid),
            "evaluations_count": k,
            "mean_raw_score": round(mu_j, 3),
            "std_dev_raw_score": round(sigma_j, 3),
            "min_raw_score": round(min(j_scores), 2),
            "max_raw_score": round(max(j_scores), 2),
            "is_zero_variance": is_zero_variance,
            "status_label": status_label,
            "_mu": mu_j,
            "_sigma": sigma_j,
        }
        judge_stats_map[jid] = stats_dict
        judge_stats_list.append(
            JudgeStats(
                judge_id=stats_dict["judge_id"],
                username=stats_dict["username"],
                evaluations_count=stats_dict["evaluations_count"],
                mean_raw_score=stats_dict["mean_raw_score"],
                std_dev_raw_score=stats_dict["std_dev_raw_score"],
                min_raw_score=stats_dict["min_raw_score"],
                max_raw_score=stats_dict["max_raw_score"],
                is_zero_variance=stats_dict["is_zero_variance"],
                status_label=stats_dict["status_label"],
            )
        )

    judge_stats_list.sort(key=lambda j: j.username)

    # --------------------------------------------------------------------------
    # Step 3: Compute Standardized z-scores and Rescaled Scores per Project
    # --------------------------------------------------------------------------
    project_results_raw: List[Dict[str, Any]] = []

    for project in projects:
        # Find all judges who evaluated this project
        evaluating_judges = [
            jid for (jid, pid) in raw_evaluations.keys() if pid == project.id
        ]

        judge_details: List[ProjectJudgeScoreDetail] = []
        raw_list: List[float] = []
        z_list: List[float] = []

        for jid in evaluating_judges:
            r_jp = raw_evaluations[(jid, project.id)]
            raw_list.append(r_jp)

            j_info = judge_stats_map.get(jid)
            if j_info and not j_info["is_zero_variance"]:
                # Standard z-score: (score - mean) / std_dev
                z_jp = (r_jp - j_info["_mu"]) / j_info["_sigma"]
            else:
                # Handle zero variance judge:
                # When a judge scores every project identically, their variance is zero.
                # Standard score is assigned z = 0.0 (neutral / average).
                z_jp = 0.0

            # Rescale to global benchmark scale
            norm_jp = global_mean + (z_jp * global_std)

            judge_details.append(
                ProjectJudgeScoreDetail(
                    judge_id=jid,
                    judge_username=judge_users.get(jid, jid),
                    raw_score=round(r_jp, 2),
                    z_score=round(z_jp, 3),
                    normalized_score=round(norm_jp, 2),
                )
            )
            z_list.append(z_jp)

        eval_count = len(evaluating_judges)
        if eval_count > 0:
            avg_raw = sum(raw_list) / eval_count
            avg_z = sum(z_list) / eval_count
            final_normalized = global_mean + (avg_z * global_std)
        else:
            avg_raw = 0.0
            avg_z = 0.0
            final_normalized = 0.0

        project_results_raw.append({
            "project_id": project.id,
            "project_title": project.title,
            "team_name": project.team.name if project.team else "Solo",
            "track_title": project.track.title if project.track else "General",
            "evaluations_count": eval_count,
            "raw_score": round(avg_raw, 2),
            "normalized_z_score": round(avg_z, 3),
            "normalized_score": round(final_normalized, 2),
            "judge_details": judge_details,
        })

    # --------------------------------------------------------------------------
    # Step 4: Deterministic Tie-Breaking & Rank Assignment
    # --------------------------------------------------------------------------
    # Raw ranking: (-raw_score, -evaluations_count, project_id)
    project_results_raw.sort(
        key=lambda x: (-x["raw_score"], -x["evaluations_count"], x["project_id"])
    )
    for raw_rank, item in enumerate(project_results_raw, start=1):
        item["raw_rank"] = raw_rank

    # Normalized ranking: (-normalized_score, -raw_score, -evaluations_count, project_id)
    project_results_raw.sort(
        key=lambda x: (
            -round(x["normalized_score"], 4),
            -round(x["raw_score"], 4),
            -x["evaluations_count"],
            x["project_id"],
        )
    )

    final_results: List[NormalizedProjectResult] = []
    for norm_rank, item in enumerate(project_results_raw, start=1):
        item["normalized_rank"] = norm_rank
        # rank_delta = raw_rank - normalized_rank
        # Positive: improved rank (e.g. was 5, now 2 => delta +3)
        # Negative: fell in rank (e.g. was 2, now 4 => delta -2)
        item["rank_delta"] = item["raw_rank"] - norm_rank

        final_results.append(
            NormalizedProjectResult(
                project_id=item["project_id"],
                project_title=item["project_title"],
                team_name=item["team_name"],
                track_title=item["track_title"],
                evaluations_count=item["evaluations_count"],
                raw_score=item["raw_score"],
                raw_rank=item["raw_rank"],
                normalized_z_score=item["normalized_z_score"],
                normalized_score=item["normalized_score"],
                normalized_rank=item["normalized_rank"],
                rank_delta=item["rank_delta"],
                judge_details=item["judge_details"],
            )
        )

    # --------------------------------------------------------------------------
    # Step 5: Package Explanation & Response
    # --------------------------------------------------------------------------
    algorithm_summary = {
        "method": "Cross-Judge Z-Score Normalization with Global Benchmark Rescaling",
        "formula_standardization": "z_{j, p} = (R_{j, p} - \\mu_j) / \\sigma_j",
        "formula_rescaling": "S_{norm} = \\mu_{global} + (\\bar{z}_p \\times \\sigma_{global})",
        "zero_variance_rule": "When a judge assigns identical scores (\\sigma_j = 0), z_{j, p} = 0.0 (neutral impact).",
        "missing_scores_rule": "Handled per criterion by proportional weight redistribution.",
        "unequal_judges_rule": "Evaluations are averaged in standardized z-space, preventing judge count bias.",
        "tie_breaking_hierarchy": [
            "1. Normalized Score (descending)",
            "2. Raw Score (descending)",
            "3. Total Evaluation Count (descending)",
            "4. Lexicographical Project Identifier (ascending, strictly deterministic)",
        ],
    }

    return NormalizationLabResponse(
        event_id=event.id,
        event_title=event.title,
        total_projects=len(projects),
        total_evaluations=len(scores),
        global_mean_score=round(global_mean, 2),
        global_std_dev=round(global_std, 2),
        judges_stats=judge_stats_list,
        results=final_results,
        algorithm_summary=algorithm_summary,
    )
