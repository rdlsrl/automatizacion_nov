from __future__ import annotations

import unittest

from drilling_knowledge.review import ReviewDecisionAction, ReviewPolicyCatalogLoader, ReviewTargetType


class ReviewPolicyLoaderTests(unittest.TestCase):
    def test_loads_seeded_review_policies(self) -> None:
        catalog = ReviewPolicyCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review")

        assertion = catalog.policy_for("assertion_manual_review")
        proposal = catalog.policy_for("proposal_manual_review")
        self.assertEqual(assertion.allowed_target_types, (ReviewTargetType.ASSERTION,))
        self.assertIn("high_impact_conflict", assertion.allowed_reasons)
        self.assertEqual(assertion.allowed_actions, (ReviewDecisionAction.APPROVE, ReviewDecisionAction.REJECT))
        self.assertEqual(proposal.allowed_target_types, (ReviewTargetType.PROPOSAL,))

    def test_catalog_serialization_is_stable(self) -> None:
        first = ReviewPolicyCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review")
        second = ReviewPolicyCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/review")

        self.assertEqual(first.as_serializable(), second.as_serializable())