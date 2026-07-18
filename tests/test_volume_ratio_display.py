from src.analyzer import format_volume_ratio


def test_prefers_real_realtime_ratio():
    assert format_volume_ratio(2.1, 1.58, "5d") == "2.1"


def test_falls_back_to_5d_with_honest_label():
    assert format_volume_ratio(None, 1.58, "5d") == "1.58 (5d)"
    assert format_volume_ratio("N/A", 1.58, "5d") == "1.58 (5d)"


def test_na_when_neither_available():
    assert format_volume_ratio(None, None, "5d") == "N/A"
