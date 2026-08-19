"""Load review policies and decision codes from seed data."""

from __future__ import annotations

import json
from pathlib import Path

from drilling_knowledge.review.domain import ReviewDecisionAction, ReviewPolicy, ReviewPolicyCatalog, ReviewTargetType


class ReviewPolicyCatalogLoader:
    @classmethod
    def load(cls, root_path: str | Path) -> ReviewPolicyCatalog:
        root = Path(root_path)
        payload = json.loads((root / "seeds" / "initial_review_policies.json").read_text(encoding="utf-8"))
        version = str(payload["policy_version"]).strip()
        if not version:
            raise ValueError("Review policy seed requires a non-empty policy_version")
        policies = tuple(
            sorted(
                (
                    ReviewPolicy(
                        queue_type=item["queue_type"],
                        allowed_target_types=tuple(ReviewTargetType(value) for value in item["allowed_target_types"]),
                        allowed_reasons=tuple(item["allowed_reasons"]),
                        allowed_actions=tuple(ReviewDecisionAction(value) for value in item["allowed_actions"]),
                        escalation_policy=item["escalation_policy"],
                    )
                    for item in payload["queue_policies"]
                ),
                key=lambda policy: policy.queue_type,
            )
        )
        return ReviewPolicyCatalog(policies)