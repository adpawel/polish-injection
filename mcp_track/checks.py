"""Language-tolerant matchers for the utility checkers (numbers and dates written the English or the Polish way)."""

import re

NUMBER = re.compile(r"\d(?:[\d   ,.']*\d)?")
MONTHS = {
    1: ["january", "jan", "stycznia", "styczeń", "styczen"], 2: ["february", "feb", "lutego", "luty"],
    3: ["march", "mar", "marca", "marzec"], 4: ["april", "apr", "kwietnia", "kwiecień", "kwiecien"],
    5: ["may", "maja", "maj"], 6: ["june", "jun", "czerwca", "czerwiec"], 7: ["july", "jul", "lipca", "lipiec"],
    8: ["august", "aug", "sierpnia", "sierpień"], 9: ["september", "sep", "września", "wrzesień"],
    10: ["october", "oct", "października", "październik"], 11: ["november", "nov", "listopada", "listopad"],
    12: ["december", "dec", "grudnia", "grudzień"],
}


def _readings(token: str) -> set[float]:
    """All plausible values of a number token: 1,234.56 / 1.234,56 / 1 234,56 / 1234,56 / 1234.56."""
    token = re.sub(r"[   ']", "", token).strip(".,")
    readings = set()
    for thousands, decimal in ((",", "."), (".", ",")):
        candidate = token.replace(thousands, "").replace(decimal, ".")
        try:
            readings.add(float(candidate))
        except ValueError:
            pass
    return readings


def numbers(text: str) -> set[float]:
    values = set()
    for match in NUMBER.finditer(text or ""):
        values |= _readings(match.group())
    return values


def has_number(text: str, value: float, tolerance: float = 0.011) -> bool:
    return any(abs(v - value) <= tolerance for v in numbers(text))


def has_integer(text: str, value: int) -> bool:
    return re.search(rf"(?<![\d.,]){value}(?![\d]|[.,]\d)", text or "") is not None


def has_date(text: str, iso: str) -> bool:
    """ISO date or the day with the month as a word or number (20 March, March 20, 20 marca, 20.03.2026, 20/03)."""
    text = (text or "").lower()
    year, month, day = (int(p) for p in iso.split("-"))
    if iso in text:
        return True
    if re.search(rf"(?<!\d)0?{day}[./]0?{month}(?:[./](?:20)?{year % 100})?(?!\d)", text):
        return True
    names = "|".join(map(re.escape, MONTHS[month]))
    return re.search(rf"(?<!\d)0?{day}(?:st|nd|rd|th)?\.?\s+(?:{names})\b|\b(?:{names})\s+0?{day}(?!\d)", text) is not None


def contains_any(text: str, options: list[str]) -> bool:
    text = (text or "").lower()
    return any(option.lower() in text for option in options)
