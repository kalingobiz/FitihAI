"""Ethiopian (Ge'ez) calendar <-> Gregorian conversion.

Most Ethiopian legal documents are dated in the Ethiopian calendar (E.C.), so
deadlines have to be converted before they are useful to anyone else (NGO
case workers, diaspora users, calendar reminders).
"""

from __future__ import annotations

from datetime import date

_ETHIOPIAN_EPOCH_JDN = 1724221  # JDN of Meskerem 1, year 1 (Amete Mihret)

MONTHS_AM = [
    "መስከረም", "ጥቅምት", "ኅዳር", "ታኅሣሥ", "ጥር", "የካቲት", "መጋቢት",
    "ሚያዝያ", "ግንቦት", "ሰኔ", "ሐምሌ", "ነሐሴ", "ጳጉሜ",
]


def _jdn_to_gregorian(jdn: int) -> date:
    return date.fromordinal(jdn - 1721425)


def ethiopian_to_gregorian(year: int, month: int, day: int) -> date:
    if not (1 <= month <= 13) or not (1 <= day <= 30):
        raise ValueError("invalid Ethiopian date")
    if month == 13 and day > (6 if year % 4 == 3 else 5):
        raise ValueError("Pagume has only 5 days (6 in a leap year)")
    jdn = _ETHIOPIAN_EPOCH_JDN - 1 + 365 * (year - 1) + year // 4 + 30 * (month - 1) + day
    return _jdn_to_gregorian(jdn)


def gregorian_to_ethiopian(d: date) -> tuple[int, int, int]:
    # The Ethiopian year starts on Sep 11 or 12 (Gregorian), 7-8 years behind.
    year = d.year - 7
    new_year = ethiopian_to_gregorian(year, 1, 1)
    if d < new_year:
        year -= 1
        new_year = ethiopian_to_gregorian(year, 1, 1)
    n = (d - new_year).days
    return year, n // 30 + 1, n % 30 + 1


def format_ethiopian(year: int, month: int, day: int) -> str:
    return f"{MONTHS_AM[month - 1]} {day}, {year} ዓ.ም"


# ---- Ethiopian time of day ---------------------------------------------------------
# Ethiopian hours are counted from 6 a.m. (day) and 6 p.m. (night):
#   day   ("ጠዋት", "ቀን", "ከሰዓት")      1 ሰዓት = 07:00 … 6 ሰዓት = 12:00 … 12 ሰዓት = 18:00
#   night ("ምሽት", "ማታ", "ሌሊት")      1 ሰዓት = 19:00 … 6 ሰዓት = 00:00 … 12 ሰዓት = 06:00


def ethiopian_time_to_24h(hour: int, minute: int = 0, period: str = "day") -> str:
    """Convert an Ethiopian clock time to international 24-hour time ("HH:MM")."""
    if not (1 <= hour <= 12) or not (0 <= minute <= 59):
        raise ValueError("Ethiopian hour must be 1-12 and minute 0-59")
    if period not in ("day", "night"):
        raise ValueError("period must be 'day' or 'night'")
    offset = 6 if period == "day" else 18
    return f"{(hour + offset) % 24:02d}:{minute:02d}"
