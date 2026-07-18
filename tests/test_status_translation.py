from src.report_language import translate_status


def test_translate_known_status_to_en():
    assert translate_status("放量下跌", "en") == "High volume, falling"
    assert translate_status("缩量回调", "en") == "Shrinking-volume pullback"
    assert translate_status("超卖", "en") == "Oversold"


def test_translate_passthrough_zh_and_unknown():
    assert translate_status("放量下跌", "zh") == "放量下跌"      # zh unchanged
    assert translate_status("something", "en") == "something"   # unknown unchanged
    assert translate_status(None, "en") is None


def test_translate_trend_status_enum_values_to_en():
    assert translate_status("强势多头", "en") == "Strong bullish"
    assert translate_status("多头排列", "en") == "Bullish alignment"
    assert translate_status("弱势多头", "en") == "Weak bullish"
    assert translate_status("盘整", "en") == "Consolidation"
    assert translate_status("弱势空头", "en") == "Weak bearish"
    assert translate_status("空头排列", "en") == "Bearish alignment"
    assert translate_status("强势空头", "en") == "Strong bearish"


def test_translate_buy_signal_enum_values_to_en():
    assert translate_status("强烈买入", "en") == "Strong buy"
    assert translate_status("买入", "en") == "Buy"
    assert translate_status("持有", "en") == "Hold"
    assert translate_status("观望", "en") == "Watch"
    assert translate_status("卖出", "en") == "Sell"
    assert translate_status("强烈卖出", "en") == "Strong sell"


def test_translate_ma_alignment_phrases_to_en():
    assert translate_status("强势多头排列，均线发散上行", "en") == (
        "Strong bullish alignment, MAs diverging upward"
    )
    assert translate_status("多头排列 MA5>MA10>MA20", "en") == (
        "Bullish alignment: MA5 > MA10 > MA20"
    )
    assert translate_status("弱势多头，MA5>MA10 但 MA10≤MA20", "en") == (
        "Weak bullish: MA5 > MA10, but MA10 ≤ MA20"
    )
    assert translate_status("强势空头排列，均线发散下行", "en") == (
        "Strong bearish alignment, MAs diverging downward"
    )
    assert translate_status("空头排列 MA5<MA10<MA20", "en") == (
        "Bearish alignment: MA5 < MA10 < MA20"
    )
    assert translate_status("弱势空头，MA5<MA10 但 MA10≥MA20", "en") == (
        "Weak bearish: MA5 < MA10, but MA10 ≥ MA20"
    )
    assert translate_status("均线缠绕，趋势不明", "en") == "MAs intertwined, trend unclear"
