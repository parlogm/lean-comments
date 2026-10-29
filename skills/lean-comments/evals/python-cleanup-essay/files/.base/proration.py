from datetime import date


# Plans are billed in whole cents; never return fractional cents.
def daily_rate_cents(monthly_cents: int, days_in_month: int) -> int:
    return monthly_cents // days_in_month
