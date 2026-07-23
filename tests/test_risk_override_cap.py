"""A mild single-step risk downgrade (downgrade_one, non-high) must not flip a neutral
HOLD to a full SELL — that over-reacts (INV-3, the JPM strong-bull -> sell bug). A SELL
still requires a veto, a high-severity flag, or a two-step downgrade."""
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.risk_override import build_risk_override_plan


def _ctx(adjustment, *, high=False, veto=False):
    ctx = AgentContext(query="q", stock_code="JPM")
    ctx.add_opinion(AgentOpinion(
        agent_name="risk", signal="hold",
        raw_data={"signal_adjustment": adjustment, "veto_buy": veto},
    ))
    if high:
        ctx.risk_flags.append({"severity": "high", "type": "test"})
    return ctx


def test_mild_downgrade_one_does_not_flip_hold_to_sell():
    plan = build_risk_override_plan(_ctx("downgrade_one"), current_signal="hold")
    assert plan.target_signal == "hold"
    assert plan.will_apply is False


def test_downgrade_one_still_takes_buy_to_hold():
    plan = build_risk_override_plan(_ctx("downgrade_one"), current_signal="buy")
    assert plan.target_signal == "hold"
    assert plan.will_apply is True


def test_high_severity_flag_still_reaches_sell_from_hold():
    plan = build_risk_override_plan(_ctx("downgrade_one", high=True), current_signal="hold")
    assert plan.target_signal == "sell"


def test_two_step_downgrade_still_reaches_sell_from_hold():
    plan = build_risk_override_plan(_ctx("downgrade_two"), current_signal="hold")
    assert plan.target_signal == "sell"
