from src.report_language import translate_status


def test_translate_known_status_to_en():
    assert translate_status("放量下跌", "en") == "High volume, falling"
    assert translate_status("缩量回调", "en") == "Shrinking-volume pullback"
    assert translate_status("超卖", "en") == "Oversold"


def test_translate_passthrough_zh_and_unknown():
    assert translate_status("放量下跌", "zh") == "放量下跌"      # zh unchanged
    assert translate_status("something", "en") == "something"   # unknown unchanged
    assert translate_status(None, "en") is None
