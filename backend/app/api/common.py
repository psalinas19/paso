"""Shapes shared by more than one group of endpoints."""

from pydantic import BaseModel


class UsageSummary(BaseModel):
    month_spend_usd: float
    budget_usd: float
    checks_this_month: int
