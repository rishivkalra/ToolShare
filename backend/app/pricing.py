from __future__ import annotations

from datetime import date

from .config import Settings
from .models import PriceBreakdown


def rental_days(start: date, end: date) -> int:
    """Inclusive day count: picking up and returning same day = 1 day."""
    return (end - start).days + 1


def price_booking(
    settings: Settings, price_per_day_cents: int, deposit_cents: int, start: date, end: date
) -> PriceBreakdown:
    days = rental_days(start, end)
    rental = price_per_day_cents * days
    fee = max(round(rental * settings.service_fee_pct), settings.service_fee_min_cents)
    return PriceBreakdown(
        days=days,
        price_per_day_cents=price_per_day_cents,
        rental_cents=rental,
        service_fee_cents=fee,
        total_cents=rental + fee,
        deposit_cents=deposit_cents,
    )
