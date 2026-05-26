from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent_office.models import RuntimeType


TOKEN_FIELDS = [
    "input_tokens",
    "cached_input_tokens",
    "cache_creation_input_tokens",
    "cache_creation_5m_input_tokens",
    "cache_creation_1h_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
]


CODEX_CREDIT_RATES = {
    "gpt-5.5": {"input": 125.0, "cached": 12.5, "output": 750.0},
    "gpt-5.4": {"input": 62.5, "cached": 6.25, "output": 375.0},
    "gpt-5.4-mini": {"input": 18.75, "cached": 1.875, "output": 113.0},
    "gpt-5.3-codex": {"input": 43.75, "cached": 4.375, "output": 350.0},
    "gpt-5.2": {"input": 43.75, "cached": 4.375, "output": 350.0},
}


CLAUDE_USD_RATES = {
    "opus-4-7": {"input": 5.0, "cache_5m": 6.25, "cache_1h": 10.0, "cache_read": 0.5, "output": 25.0},
    "opus-4-6": {"input": 5.0, "cache_5m": 6.25, "cache_1h": 10.0, "cache_read": 0.5, "output": 25.0},
    "opus-4-5": {"input": 5.0, "cache_5m": 6.25, "cache_1h": 10.0, "cache_read": 0.5, "output": 25.0},
    "opus-4-1": {"input": 15.0, "cache_5m": 18.75, "cache_1h": 30.0, "cache_read": 1.5, "output": 75.0},
    "opus-4": {"input": 15.0, "cache_5m": 18.75, "cache_1h": 30.0, "cache_read": 1.5, "output": 75.0},
    "sonnet-4-6": {"input": 3.0, "cache_5m": 3.75, "cache_1h": 6.0, "cache_read": 0.3, "output": 15.0},
    "sonnet-4-5": {"input": 3.0, "cache_5m": 3.75, "cache_1h": 6.0, "cache_read": 0.3, "output": 15.0},
    "sonnet-4": {"input": 3.0, "cache_5m": 3.75, "cache_1h": 6.0, "cache_read": 0.3, "output": 15.0},
    "haiku-4-5": {"input": 1.0, "cache_5m": 1.25, "cache_1h": 2.0, "cache_read": 0.1, "output": 5.0},
    "haiku-3-5": {"input": 0.8, "cache_5m": 1.0, "cache_1h": 1.6, "cache_read": 0.08, "output": 4.0},
}


def blank_tokens() -> dict[str, int]:
    return {field: 0 for field in TOKEN_FIELDS}


def _add_tokens(target: dict[str, int], tokens: dict[str, int]) -> None:
    for field in TOKEN_FIELDS:
        target[field] += int(tokens.get(field) or 0)


def _rate_for_codex_model(model: str) -> dict[str, float] | None:
    normalized = model.lower().replace("_", "-")
    if normalized in CODEX_CREDIT_RATES:
        return CODEX_CREDIT_RATES[normalized]
    for key, rate in CODEX_CREDIT_RATES.items():
        if key in normalized:
            return rate
    return None


def _rate_for_claude_model(model: str) -> dict[str, float] | None:
    normalized = model.lower().replace("_", "-").replace(".", "-")
    for key, rate in CLAUDE_USD_RATES.items():
        if key in normalized:
            return rate
    return None


def _billable_amount(runtime_type: RuntimeType, model: str, tokens: dict[str, int]) -> float:
    if runtime_type == RuntimeType.CODEX:
        rate = _rate_for_codex_model(model)
        if rate is None:
            return 0.0
        cached_input = tokens["cached_input_tokens"]
        base_input = max(tokens["input_tokens"] - cached_input, 0)
        return (
            (base_input / 1_000_000) * rate["input"]
            + (cached_input / 1_000_000) * rate["cached"]
            + (tokens["output_tokens"] / 1_000_000) * rate["output"]
        )

    if runtime_type == RuntimeType.CLAUDE_CODE:
        rate = _rate_for_claude_model(model)
        if rate is None:
            return 0.0
        cache_5m = tokens["cache_creation_5m_input_tokens"]
        cache_1h = tokens["cache_creation_1h_input_tokens"]
        if cache_5m == 0 and cache_1h == 0:
            cache_5m = tokens["cache_creation_input_tokens"]
        return (
            (tokens["input_tokens"] / 1_000_000) * rate["input"]
            + (cache_5m / 1_000_000) * rate["cache_5m"]
            + (cache_1h / 1_000_000) * rate["cache_1h"]
            + (tokens["cache_read_input_tokens"] / 1_000_000) * rate["cache_read"]
            + (tokens["output_tokens"] / 1_000_000) * rate["output"]
        )

    return 0.0


@dataclass
class UsageBucket:
    tokens: dict[str, int] = field(default_factory=blank_tokens)
    model_tokens: dict[str, dict[str, int]] = field(default_factory=dict)
    model_request_counts: dict[str, int] = field(default_factory=dict)
    model_session_keys: dict[str, set[str]] = field(default_factory=dict)
    request_count: int = 0
    session_keys: set[str] = field(default_factory=set)

    def add(self, model: str | None, tokens: dict[str, int], session_key: str, request_count: int = 1) -> None:
        model_name = model or "unknown"
        _add_tokens(self.tokens, tokens)
        self.request_count += request_count
        self.session_keys.add(session_key)
        if model_name not in self.model_tokens:
            self.model_tokens[model_name] = blank_tokens()
            self.model_request_counts[model_name] = 0
            self.model_session_keys[model_name] = set()
        _add_tokens(self.model_tokens[model_name], tokens)
        self.model_request_counts[model_name] += request_count
        self.model_session_keys[model_name].add(session_key)

    def to_payload(
        self,
        runtime_type: RuntimeType,
        billable_unit: str,
        budget_amount: float | None = None,
    ) -> dict[str, object]:
        model_breakdown = []
        billable_amount = 0.0
        for model, tokens in sorted(self.model_tokens.items()):
            model_amount = _billable_amount(runtime_type, model, tokens)
            billable_amount += model_amount
            model_breakdown.append(
                {
                    "model": model,
                    **tokens,
                    "billable_unit": billable_unit,
                    "billable_amount": round(model_amount, 6),
                    "request_count": self.model_request_counts.get(model, 0),
                    "session_count": len(self.model_session_keys.get(model, set())),
                }
            )

        payload: dict[str, object] = {
            **self.tokens,
            "billable_unit": billable_unit,
            "billable_amount": round(billable_amount, 6),
            "request_count": self.request_count,
            "session_count": len(self.session_keys),
            "model_breakdown": model_breakdown,
        }
        if budget_amount is not None:
            payload["budget_amount"] = budget_amount
            payload["budget_used_ratio"] = round(billable_amount / budget_amount, 6) if budget_amount > 0 else 0.0
        return payload


def usage_period_bounds(
    now: datetime,
    timezone_name: str,
    week_start_day: int,
    week_start_hour: int,
) -> dict[str, datetime]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")

    local_now = now.astimezone(timezone)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_anchor = local_now.replace(hour=week_start_hour, minute=0, second=0, microsecond=0)
    day_offset = (week_anchor.weekday() - week_start_day) % 7
    week_start = week_anchor - timedelta(days=day_offset)
    if week_start > local_now:
        week_start -= timedelta(days=7)
    return {
        "today": today_start.astimezone(UTC),
        "week": week_start.astimezone(UTC),
    }


def period_payload(
    period: str,
    bucket: UsageBucket,
    runtime_type: RuntimeType,
    billable_unit: str,
    start_at: datetime,
    end_at: datetime,
    budget_amount: float | None = None,
) -> dict[str, object]:
    payload = bucket.to_payload(runtime_type, billable_unit, budget_amount)
    payload["period"] = period
    payload["start_at"] = start_at.isoformat()
    payload["end_at"] = end_at.isoformat()
    return payload
