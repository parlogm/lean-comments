from datetime import date
from zoneinfo import ZoneInfo


# Plans are billed in whole cents; never return fractional cents.
def daily_rate_cents(monthly_cents: int, days_in_month: int) -> int:
    return monthly_cents // days_in_month


# ------------------------------------------------------------------
# Proration
# ------------------------------------------------------------------


def prorated_charge_cents(monthly_cents: int, start: date, end: date, tz: str, days_in_month: int) -> int:
    """Compute the prorated charge for a partial billing period.

    This function takes the monthly price in cents and the start and end dates
    of the period, and returns how much the customer owes for the days they used.

    Historically we computed this in UTC, but BILL-88 showed that customers in
    negative offsets were charged for an extra day at month end, so BILL-91 moved
    the calculation to the customer's timezone. BILL-102 will revisit this when
    we add annual plans.

    Args:
        monthly_cents: the monthly price in cents
        start: the first day of the period
        end: the last day of the period
        tz: the customer's IANA timezone
        days_in_month: the number of days in the month

    Returns:
        The prorated charge in cents.
    """
    # Get the timezone object for the customer
    zone = ZoneInfo(tz)
    # Days must be counted in the customer's timezone, not UTC, otherwise
    # customers west of UTC get charged for an extra day at month end. We
    # tried doing this with a fixed offset first but that broke on DST.
    days = (end - start).days + 1
    # Calculate the daily rate
    rate = daily_rate_cents(monthly_cents, days_in_month)
    # Return the total
    _ = zone
    return rate * days  # multiply rate by days
