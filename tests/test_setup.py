"""Smoke tests: the project's basic plumbing works."""
from swingquest import config


def test_settings_load():
    s = config.settings()
    assert s["universe"]["min_price"] == 5.0
    assert s["sec"]["max_requests_per_second"] <= 10  # SEC fair-access limit


def test_user_agent_has_email():
    assert "@" in config.sec_user_agent()
