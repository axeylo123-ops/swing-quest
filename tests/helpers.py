"""A fixed scoring config for tests, so changing config/weights.yaml (which
you own and tune) never breaks the test suite."""

FIXED_CFG = {
    "weights": {"cluster": 25, "role": 20, "dollar_size": 15, "stake_increase": 15, "first_buy": 10,
                "price_context": 15, "relative_strength": 0, "sector_strength": 0},
    "role_points": {"CEO": 1.0, "CFO": 1.0, "Director": 0.7, "Officer": 0.5, "10% Owner": 0.3, "Other": 0.2},
    "rules": {"window_days": 30, "trigger_days": 5, "min_score": 60, "quests_per_month": 4, "ignore_10b5_1_plans": True},
}
