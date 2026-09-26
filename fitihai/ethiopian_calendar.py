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
