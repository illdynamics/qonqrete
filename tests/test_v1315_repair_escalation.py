import pytest
from worqer.construqtor import choose_repair_level

def test_choose_repair_level_escalates_to_level_4():
    config = {"repair_escalation": {"enabled": True, "max_level": 4, "bump_policy": "on_same_class_repeat"}}
    prior_records = []
    
    # Attempt 1: Base level 2
    level, reason = choose_repair_level(
        config=config,
        attempt_index=1,
        failure_class="required_output_missing",
        failure_fingerprint="abc",
        prior_attempt_records=prior_records
    )
    assert level == 2
    prior_records.append({"failure_class": "required_output_missing", "failure_fingerprint": "abc", "repair_level": level})

    # Attempt 2: Should escalate to 3
    level, reason = choose_repair_level(
        config=config,
        attempt_index=2,
        failure_class="required_output_missing",
        failure_fingerprint="abc",
        prior_attempt_records=prior_records
    )
    assert level == 3
    prior_records.append({"failure_class": "required_output_missing", "failure_fingerprint": "abc", "repair_level": level})

    # Attempt 3: Should escalate to 4
    level, reason = choose_repair_level(
        config=config,
        attempt_index=3,
        failure_class="required_output_missing",
        failure_fingerprint="abc",
        prior_attempt_records=prior_records
    )
    assert level == 4
    prior_records.append({"failure_class": "required_output_missing", "failure_fingerprint": "abc", "repair_level": level})

    # Attempt 4: Caps at 4
    level, reason = choose_repair_level(
        config=config,
        attempt_index=4,
        failure_class="required_output_missing",
        failure_fingerprint="abc",
        prior_attempt_records=prior_records
    )
    assert level == 4
    prior_records.append({"failure_class": "required_output_missing", "failure_fingerprint": "abc", "repair_level": level})

    # Attempt 5: Caps at 4
    level, reason = choose_repair_level(
        config=config,
        attempt_index=5,
        failure_class="required_output_missing",
        failure_fingerprint="abc",
        prior_attempt_records=prior_records
    )
    assert level == 4
