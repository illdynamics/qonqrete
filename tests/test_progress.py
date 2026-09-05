"""Tests for the canonical progress calculator (qq/progress.py)."""
import unittest
from qq.progress import (
    calculate_progress,
    _lifecycle_score,
    _normalize_weights,
    _clamp,
)


class TestLifecycleScore(unittest.TestCase):
    """Test the lifecycle_score mapping for various statuses."""

    def test_planned_is_zero(self):
        self.assertEqual(_lifecycle_score("planned"), 0.0)
        self.assertEqual(_lifecycle_score("queued"), 0.0)
        self.assertEqual(_lifecycle_score("not_started"), 0.0)

    def test_building_default(self):
        """Without briq ratio, building defaults to ~0.45 (0.10 + 0.50*0.35)."""
        score = _lifecycle_score("building")
        self.assertAlmostEqual(score, 0.275, delta=0.1)

    def test_building_with_ratio(self):
        score = _lifecycle_score("building", briq_completion_ratio=0.5)
        self.assertAlmostEqual(score, 0.35, delta=0.05)

    def test_ready_for_review(self):
        self.assertEqual(_lifecycle_score("ready_for_review"), 0.70)
        self.assertEqual(_lifecycle_score("built"), 0.70)
        self.assertEqual(_lifecycle_score("build_complete"), 0.70)

    def test_reviewing(self):
        self.assertEqual(_lifecycle_score("reviewing"), 0.80)
        self.assertEqual(_lifecycle_score("validating"), 0.80)
        self.assertEqual(_lifecycle_score("inspection"), 0.80)

    def test_repair_needed(self):
        self.assertEqual(_lifecycle_score("repair_needed"), 0.65)
        self.assertEqual(_lifecycle_score("failed"), 0.65)
        self.assertEqual(_lifecycle_score("validation_failed"), 0.65)

    def test_accepted_is_one(self):
        self.assertEqual(_lifecycle_score("done"), 1.00)
        self.assertEqual(_lifecycle_score("accepted"), 1.00)
        self.assertEqual(_lifecycle_score("complete"), 1.00)
        self.assertEqual(_lifecycle_score("fully_done"), 1.00)
        self.assertEqual(_lifecycle_score("success"), 1.00)

    def test_unknown_lowercase(self):
        """Status is normalized to lowercase."""
        self.assertEqual(_lifecycle_score("PLANNED"), 0.0)
        self.assertEqual(_lifecycle_score("DONE"), 1.00)

    def test_none_is_zero(self):
        self.assertEqual(_lifecycle_score(None), 0.0)


class TestNormalizeWeights(unittest.TestCase):
    """Test group weight normalization."""

    def test_empty_groups(self):
        self.assertEqual(_normalize_weights([]), [])

    def test_equal_weights(self):
        groups = [
            {"id": "g1"},
            {"id": "g2"},
            {"id": "g3"},
        ]
        result = _normalize_weights(groups)
        self.assertAlmostEqual(result[0]["normalized_weight_pct"], 33.33, delta=0.5)
        self.assertAlmostEqual(result[1]["normalized_weight_pct"], 33.33, delta=0.5)
        self.assertAlmostEqual(result[2]["normalized_weight_pct"], 33.34, delta=0.5)

    def test_explicit_weights_normalize(self):
        groups = [
            {"id": "g1", "progress_weight_pct": 30},
            {"id": "g2", "progress_weight_pct": 70},
        ]
        result = _normalize_weights(groups)
        self.assertAlmostEqual(result[0]["normalized_weight_pct"], 30.0, delta=0.1)
        self.assertAlmostEqual(result[1]["normalized_weight_pct"], 70.0, delta=0.1)

    def test_explicit_weights_sum_rebalance(self):
        groups = [
            {"id": "g1", "progress_weight_pct": 50},
            {"id": "g2", "progress_weight_pct": 25},
        ]
        result = _normalize_weights(groups)
        # Should rebalance to 100: g1=66.67, g2=33.33
        self.assertAlmostEqual(result[0]["normalized_weight_pct"], 66.67, delta=0.5)
        self.assertAlmostEqual(result[1]["normalized_weight_pct"], 33.33, delta=0.5)


class TestProgressBasics(unittest.TestCase):
    """Basic progress calculator tests."""

    def test_no_groups_no_nan(self):
        """Empty groups produces sane progress, no NaN."""
        snap = calculate_progress(groups=[])
        self.assertFalse(snap.displayed_pct != snap.displayed_pct)  # not NaN
        self.assertGreaterEqual(snap.displayed_pct, 0)
        self.assertLessEqual(snap.displayed_pct, 100)
        self.assertGreaterEqual(snap.accepted_pct, 0)
        self.assertLessEqual(snap.accepted_pct, 100)

    def test_planned_group_zero_contribution(self):
        groups = [
            {"id": "g1", "title": "Group 1", "status": "planned",
             "briqs": [{"status": "pending"}]},
        ]
        snap = calculate_progress(groups=groups, active_agent="qlarifier")
        # build_review working will be 0 since lifecycle_score=0
        # But clarification_phase might be small
        self.assertEqual(snap.components.build_review_working_pct, 0.0)
        self.assertEqual(snap.components.build_review_accepted_pct, 0.0)
        self.assertLess(snap.displayed_pct, 25)  # Only clarification phase at most

    def test_building_group_contributes_partial(self):
        groups = [
            {"id": "g1", "title": "Group 1", "status": "building",
             "briqs": [{"status": "done"}, {"status": "in_progress"}]},
        ]
        snap = calculate_progress(groups=groups, active_agent="construqtor",
                                  clarification_complete=True, planning_complete=True)
        self.assertGreater(snap.working_pct, 20)
        self.assertLess(snap.working_pct, 90)
        self.assertEqual(snap.accepted_pct, 20.0)  # Only cla+pln, no accepted

    def test_ready_for_review_contributes_70_percent_of_group(self):
        groups = [
            {"id": "g1", "title": "Group 1", "status": "ready_for_review",
             "progress_weight_pct": 100, "briqs": [{"status": "done"}]},
        ]
        snap = calculate_progress(groups=groups, active_agent="construqtor",
                                  clarification_complete=True, planning_complete=True)
        # Lifecycle score 0.70 → working contribution = 100 * 0.70 = 70% of build_review
        # Overall: 5 + 15 + 75*0.70 = 72.5
        self.assertAlmostEqual(snap.working_pct, 72.5, delta=1)
        # Accepted: only cla+pln (20)
        self.assertAlmostEqual(snap.accepted_pct, 20.0, delta=1)

    def test_reviewing_contributes_80_percent(self):
        groups = [
            {"id": "g1", "title": "Group 1", "status": "reviewing",
             "progress_weight_pct": 100, "briqs": [{"status": "done"}]},
        ]
        snap = calculate_progress(groups=groups, active_agent="inspeqtor",
                                  clarification_complete=True, planning_complete=True)
        # LS 0.80: 5 + 15 + 75*0.80 = 80.0
        self.assertAlmostEqual(snap.working_pct, 80.0, delta=1)

    def test_repair_needed_dips_to_65(self):
        groups = [
            {"id": "g1", "title": "Group 1", "status": "repair_needed",
             "progress_weight_pct": 100, "briqs": [{"status": "needs_repair"}]},
        ]
        snap = calculate_progress(groups=groups, active_agent="construqtor",
                                  clarification_complete=True, planning_complete=True)
        # LS 0.65: 5 + 15 + 75*0.65 = 68.75
        self.assertAlmostEqual(snap.working_pct, 68.75, delta=1)

    def test_accepted_contributes_100(self):
        groups = [
            {"id": "g1", "title": "Group 1", "status": "done",
             "progress_weight_pct": 100, "briqs": [{"status": "done"}]},
        ]
        snap = calculate_progress(groups=groups, active_agent="inspeqtor",
                                  clarification_complete=True, planning_complete=True,
                                  finalization_complete=True)
        self.assertAlmostEqual(snap.working_pct, 100.0, delta=0.5)
        self.assertAlmostEqual(snap.accepted_pct, 100.0, delta=0.5)

    def test_fully_done_is_100(self):
        groups = [
            {"id": "g1", "title": "Group 1", "status": "ready_for_review",
             "progress_weight_pct": 100, "briqs": [{"status": "done"}]},
        ]
        snap = calculate_progress(groups=groups, final_verdict="FULLY_DONE",
                                  run_status="done")
        self.assertEqual(snap.displayed_pct, 100.0)
        self.assertEqual(snap.accepted_pct, 100.0)
        self.assertEqual(snap.working_pct, 100.0)
        self.assertEqual(snap.confidence, "final")

    def test_quality_score_separate_from_completion(self):
        """InspeQtor quality score should not override completion progress."""
        groups = [
            {"id": "g1", "title": "Group 1", "status": "building",
             "progress_weight_pct": 100, "briqs": [{"status": "done"}, {"status": "in_progress"}]},
        ]
        snap = calculate_progress(groups=groups, active_agent="construqtor",
                                  inspeqtor_score=95.0,
                                  clarification_complete=True, planning_complete=True)
        # Quality score of 95 should NOT make working_pct 95
        self.assertNotEqual(snap.working_pct, 95.0)
        self.assertEqual(snap.inspeqtor_quality_pct, 95.0)
        self.assertEqual(snap.quality_confidence, "high")
        # Working should reflect actual lifecycle, not quality score
        self.assertLess(snap.working_pct, 90)

    def test_progress_pct_equals_displayed_pct(self):
        """Backward compatibility: progress_pct == displayed_pct."""
        groups = [
            {"id": "g1", "title": "Group 1", "status": "building",
             "progress_weight_pct": 100, "briqs": [{"status": "done"}]},
        ]
        snap = calculate_progress(groups=groups, active_agent="construqtor",
                                  clarification_complete=True, planning_complete=True)
        d = snap.to_dict()
        self.assertEqual(d["progress_pct"], d["displayed_pct"])

    def test_no_negative_progress(self):
        snap = calculate_progress(groups=[])
        self.assertGreaterEqual(snap.displayed_pct, 0)
        self.assertGreaterEqual(snap.accepted_pct, 0)
        self.assertGreaterEqual(snap.working_pct, 0)

    def test_no_over_100_progress(self):
        groups = [
            {"id": "g1", "title": "Group 1", "status": "done",
             "progress_weight_pct": 100, "briqs": [{"status": "done"}]},
        ]
        snap = calculate_progress(groups=groups, clarification_complete=True,
                                  planning_complete=True, finalization_complete=True)
        self.assertLessEqual(snap.displayed_pct, 100)
        self.assertLessEqual(snap.accepted_pct, 100)
        self.assertLessEqual(snap.working_pct, 100)

    def test_clamp_helper(self):
        self.assertEqual(_clamp(50), 50)
        self.assertEqual(_clamp(-10), 0)
        self.assertEqual(_clamp(150), 100)
        self.assertEqual(_clamp(0), 0)
        self.assertEqual(_clamp(100), 100)

    def test_mixed_groups_weighted(self):
        """Test multiple groups with different statuses and weights."""
        groups = [
            {"id": "g1", "title": "Foundation", "status": "done",
             "progress_weight_pct": 20, "briqs": [{"status": "done"}] * 3},
            {"id": "g2", "title": "Core", "status": "ready_for_review",
             "progress_weight_pct": 50, "briqs": [{"status": "done"}] * 5},
            {"id": "g3", "title": "Polish", "status": "planned",
             "progress_weight_pct": 30, "briqs": [{"status": "pending"}] * 2},
        ]
        snap = calculate_progress(groups=groups, active_agent="construqtor",
                                  clarification_complete=True, planning_complete=True)
        # g1 (20% weight, done → LS 1.0): contributes 20
        # g2 (50% weight, ready_for_review → LS 0.70): contributes 35
        # g3 (30% weight, planned → LS 0.0): contributes 0
        # build_review ratio: (20+35+0)/100 = 0.55
        # working: 5 + 15 + 75*0.55 = 61.25
        # accepted: 5 + 15 + 75*0.20 = 35.0 (only g1)
        self.assertAlmostEqual(snap.working_pct, 61.25, delta=1)
        self.assertAlmostEqual(snap.accepted_pct, 35.0, delta=1)
        self.assertGreater(snap.working_pct, snap.accepted_pct)

    def test_snapshot_to_dict(self):
        snap = calculate_progress(groups=[])
        d = snap.to_dict()
        self.assertIn("accepted_pct", d)
        self.assertIn("working_pct", d)
        self.assertIn("displayed_pct", d)
        self.assertIn("progress_pct", d)
        self.assertIn("confidence", d)
        self.assertIn("phase", d)
        self.assertIn("components", d)
        self.assertIn("groups", d)
        self.assertIsInstance(d["groups"], list)


if __name__ == "__main__":
    unittest.main()
