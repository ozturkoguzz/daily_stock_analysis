# -*- coding: utf-8 -*-
"""
SkillRouter — rule-based skill selection.

Selects which trading skills to apply based on:
1. User-explicit request (highest priority)
2. Market regime detection from technical data in ``AgentContext``
3. Centralised default fallback
"""

from __future__ import annotations

import logging
from typing import List, Optional

from src.agent.protocols import AgentContext
from src.agent.skills.defaults import (
    get_default_router_skill_ids,
    get_regime_skill_ids,
)

logger = logging.getLogger(__name__)

# Distance from the 20-day mean, in percent, at which measured price position
# overrides the model's own trend label. Chosen so ordinary chop stays
# `sideways` while a genuine breakout cannot be filed as directionless.
_BIAS_OVERRIDE_PCT = 5.0


def _measured_bias_ma20(raw: dict, stock_code: str):
    """Price distance from MA20 in percent, measured -- never self-reported.

    The technical agent's opinion JSON carries signal/confidence/trend_score/
    ma_alignment and nothing else, so bias_ma20 is not in `raw` despite
    analyze_trend computing it. Fall back to the tool, which is pure Python
    with no LLM call. Returns None when it cannot be established, in which
    case the caller keeps the existing label-based logic.
    """
    try:
        return float(raw["bias_ma20"])
    except (KeyError, TypeError, ValueError):
        pass
    if not stock_code:
        return None
    try:
        from src.agent.tools.analysis_tools import _handle_analyze_trend

        value = _handle_analyze_trend(str(stock_code)).get("bias_ma20")
        return None if value is None else float(value)
    except Exception:
        logger.warning("[SkillRouter] bias_ma20 lookup failed for %s",
                       stock_code, exc_info=True)
        return None


class SkillRouter:
    """Select applicable skills for a given analysis context."""

    def select_skills(
        self,
        ctx: AgentContext,
        max_count: int = 3,
    ) -> List[str]:
        requested_skills = ctx.meta.get("skills_requested") or ctx.meta.get("strategies_requested", [])
        if requested_skills:
            logger.info("[SkillRouter] user-requested skills: %s", requested_skills)
            return requested_skills[:max_count]

        routing_mode = self._get_routing_mode()
        if routing_mode == "manual":
            selected = self._get_manual_skills(max_count=max_count)
            logger.info("[SkillRouter] manual mode — using skills: %s", selected)
            return selected

        available_skills = self._get_available_skills()
        skill_catalog = available_skills or None
        available_ids = {skill.name for skill in available_skills}
        regime = self._detect_regime(ctx)
        if regime:
            selected = get_regime_skill_ids(
                regime,
                skill_catalog,
                max_count=max_count,
                available_skill_ids=available_ids or None,
            )
            if selected:
                logger.info("[SkillRouter] regime=%s -> skills: %s", regime, selected)
                return selected

        default_skills = get_default_router_skill_ids(
            skill_catalog,
            max_count=max_count,
            available_skill_ids=available_ids or None,
        )
        logger.info("[SkillRouter] using default skills: %s", default_skills)
        return default_skills

    def select_strategies(
        self,
        ctx: AgentContext,
        max_count: int = 3,
    ) -> List[str]:
        """Compatibility wrapper for legacy strategy-based callers."""
        return self.select_skills(ctx, max_count=max_count)

    def _detect_regime(self, ctx: AgentContext) -> Optional[str]:
        for op in ctx.opinions:
            if op.agent_name != "technical":
                continue
            raw = op.raw_data or {}

            ma_alignment = str(raw.get("ma_alignment", "")).lower()
            try:
                trend_score = float(raw.get("trend_score", 50))
            except (TypeError, ValueError):
                trend_score = 50.0
            volume_status = str(raw.get("volume_status", "")).lower()

            # Measured position beats self-assessment. ma_alignment and
            # trend_score are written by the technical agent about its own
            # read; bias_ma20 is computed from price. When price sits far from
            # its 20-day mean, that is the fact, whatever the label says.
            # GEHC (2026-07-30) was +12.5% above MA20 at its 20-day high and
            # still routed `sideways`, landing a textbook breakout on the
            # documented no-edge stand-aside skill.
            bias_ma20 = _measured_bias_ma20(raw, getattr(ctx, "stock_code", ""))
            if bias_ma20 is not None and abs(bias_ma20) >= _BIAS_OVERRIDE_PCT:
                decided = "trending_up" if bias_ma20 > 0 else "trending_down"
                logger.info(
                    "[SkillRouter] bias_ma20=%.1f%% overrides ma_alignment=%r -> %s",
                    bias_ma20, ma_alignment, decided)
                return decided

            if ma_alignment == "bullish" and trend_score >= 70:
                return "trending_up"
            if ma_alignment == "bearish" and trend_score <= 30:
                return "trending_down"
            if ma_alignment == "neutral" or 35 <= trend_score <= 65:
                return "sideways"
            if volume_status == "heavy" and 30 < trend_score < 70:
                return "volatile"

        if ctx.meta.get("sector_hot"):
            return "sector_hot"
        return None

    @staticmethod
    def _get_routing_mode() -> str:
        try:
            from src.config import get_config

            config = get_config()
            return getattr(config, "agent_skill_routing", "auto")
        except Exception:
            logger.warning("Failed to get routing mode, falling back to auto", exc_info=True)
            return "auto"

    @staticmethod
    def _get_available_ids() -> set:
        return {skill.name for skill in SkillRouter._get_available_skills()}

    @staticmethod
    def _get_available_skills() -> list:
        try:
            from src.agent.factory import _SKILL_MANAGER_PROTOTYPE

            if _SKILL_MANAGER_PROTOTYPE is not None:
                return list(_SKILL_MANAGER_PROTOTYPE.list_skills())

            from src.agent.factory import get_skill_manager

            sm = get_skill_manager()
            return list(sm.list_skills())
        except Exception:
            logger.warning("Failed to get available skills", exc_info=True)
            return []

    @classmethod
    def _get_manual_skills(cls, max_count: int) -> List[str]:
        configured: List[str] = []
        try:
            from src.config import get_config

            config = get_config()
            configured = [
                skill_id
                for skill_id in getattr(config, "agent_skills", []) or []
                if isinstance(skill_id, str) and skill_id
            ]
        except Exception:
            logger.warning("Failed to get manual skills config", exc_info=True)
            configured = []

        available_skills = cls._get_available_skills()
        skill_catalog = available_skills or None
        available = {skill.name for skill in available_skills}
        selected = [skill_id for skill_id in configured if skill_id in available][:max_count]
        if selected:
            return selected

        return get_default_router_skill_ids(
            skill_catalog,
            max_count=max_count,
            available_skill_ids=available or None,
        )


StrategyRouter = SkillRouter
_DEFAULT_STRATEGIES = tuple(get_default_router_skill_ids())
_DEFAULT_SKILLS = _DEFAULT_STRATEGIES
