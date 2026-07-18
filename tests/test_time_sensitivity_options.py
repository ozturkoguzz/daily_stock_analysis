from src.analyzer import time_sensitivity_options


def test_options_localized():
    assert time_sensitivity_options("en") == "Act now / Today / This week / Not urgent"
    assert time_sensitivity_options("zh") == "立即行动/今日内/本周内/不急"
