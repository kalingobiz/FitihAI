# Module 06 — Ethiopian Calendar

## 1. Purpose
Most Ethiopian legal documents are dated in the Ethiopian calendar (E.C., ዓ.ም).
A missed hearing or response deadline can decide a case, so dates must be exact.
This module converts dates between the Ethiopian and Gregorian calendars in
code, rather than trusting an AI to do the arithmetic.

## 2. Scope
**In scope:** E.C. → Gregorian, Gregorian → E.C., leap-year rules for Pagume, and
formatting with Amharic month names. It also turns the deadlines the AI
extracted into both calendars.
**Out of scope:** finding dates in the document (the AI does that, module 05),
and Ethiopian time-of-day (the 12-hour clock starting at 6 a.m.).

## 3. Files
| File | Role |
|---|---|
| `fitihai/ethiopian_calendar.py` | Conversion functions and month names |
| `fitihai/pipeline.py` | `resolve_deadline()` applies them to AI-extracted deadlines |

## 4. Interfaces
| Function | Example |
|---|---|
| `ethiopian_to_gregorian(year, month, day) -> date` | `(2017, 1, 1)` → `2024-09-11` |
| `gregorian_to_ethiopian(date) -> (year, month, day)` | `2026-09-26` → `(2019, 1, 16)` |
| `format_ethiopian(y, m, d) -> str` | `(2019, 1, 16)` → `"መስከረም 16, 2019 ዓ.ም"` |
| `resolve_deadline(Deadline, today=None) -> DeadlineOut` | Fills `gregorian_date` (ISO) and `ethiopian_date` (formatted) |

Months: 1 መስከረም, 2 ጥቅምት, 3 ኅዳር, 4 ታኅሣሥ, 5 ጥር, 6 የካቲት, 7 መጋቢት, 8 ሚያዝያ,
9 ግንቦት, 10 ሰኔ, 11 ሐምሌ, 12 ነሐሴ, 13 ጳጉሜ.

## 5. Design and flow
- The Ethiopian year has 12 months of 30 days plus Pagume (ጳጉሜ), which has 5 days,
  or 6 days in a leap year. An E.C. year `y` is a leap year when `y % 4 == 3`.
- **E.C. → Gregorian** uses the Julian Day Number:
  `JDN = 1724221 − 1 + 365·(y−1) + ⌊y/4⌋ + 30·(m−1) + d`, where `1724221` is the JDN of
  Meskerem 1, year 1 (Amete Mihret era). The result is converted to a Python `date`.
- **Gregorian → E.C.** finds the Ethiopian New Year on or before the date (it falls
  on 11 or 12 September), then counts days: `month = days // 30 + 1`, `day = days % 30 + 1`.
- **Deadline resolution rules**
  | AI extracted | Result |
  |---|---|
  | `calendar = ethiopian`, full Y/M/D | Gregorian ISO date + formatted E.C. |
  | `calendar = gregorian`, full Y/M/D | Formatted E.C. + ISO date |
  | `calendar = relative` ("within 15 days") | Not converted: the starting day is unknown |
  | `unknown` or incomplete parts | Left as written |

## 6. Configuration
None.

## 7. Data, privacy and security
Pure computation. No data is stored or sent anywhere.

## 8. Error handling
- An invalid month (outside 1–13) or day (outside 1–30), or Pagume day 6 in a
  non-leap year, raises `ValueError`.
- `resolve_deadline` catches the error and leaves the date as written. A
  misread OCR date is never turned into a confident but wrong date.

## 9. Testing
- `tests/test_core.py::test_ethiopian_calendar`: known New Year dates (2016 E.C. →
  12 Sep 2023, 2017 → 11 Sep 2024) and the Pagume leap-year check.
- `test_analyze_document`: an E.C. deadline is converted end to end.
- During development, 20,000 random dates were converted both ways with no
  mismatches.

## 10. Limitations and next steps
- Ethiopian time of day ("ከጠዋቱ 3 ሰዓት" = 9 a.m.) is not converted yet. Hearing
  times are often written this way, so this is worth adding.
- Relative deadlines could be resolved if the user tells us the date they received
  the document. Add a "When did you receive this?" prompt.
- Offer calendar reminders (Telegram message or `.ics` file) for extracted deadlines.
