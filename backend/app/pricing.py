from __future__ import annotations

from datetime import date

from .config import Settings
from .models import PriceBreakdown


def rental_days(start: date, end: date) -> int:
    """Inclusive day count: picking up and returning same day = 1 day."""
    return (end - start).days + 1


def rental_cents_for(
    price_per_day_cents: int, price_per_week_cents: int, days: int
) -> int:
    """Daily total, discounted by the owner's weekly rate for 7+ day rentals
    (whole weeks at the weekly rate + leftover days), never above days x day."""
    rental = price_per_day_cents * days
    if price_per_week_cents > 0 and days >= 7:
        tiered = (days // 7) * price_per_week_cents + (days % 7) * price_per_day_cents
        rental = min(rental, tiered)
    return rental


def price_booking(
    settings: Settings, price_per_day_cents: int, deposit_cents: int, start: date, end: date,
    price_per_week_cents: int = 0,
) -> PriceBreakdown:
    days = rental_days(start, end)
    rental = rental_cents_for(price_per_day_cents, price_per_week_cents, days)
    fee = max(round(rental * settings.service_fee_pct), settings.service_fee_min_cents)
    protection = settings.protection_fee_cents
    return PriceBreakdown(
        days=days,
        price_per_day_cents=price_per_day_cents,
        rental_cents=rental,
        service_fee_cents=fee,
        protection_fee_cents=protection,
        total_cents=rental + fee + protection,
        deposit_cents=deposit_cents,
    )
