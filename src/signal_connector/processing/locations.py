"""Location parsing + canonicalization. Free-text ATS location strings are messy;
this turns them into a canonical Location and decides what is *remote* (not a physical
expansion) vs a real metro presence.
"""

from __future__ import annotations

import re

from signal_connector.models import Location

# A job tagged remote/distributed is NOT evidence of a physical location.
REMOTE_MARKERS = re.compile(r"\b(remote|anywhere|distributed|work from home|wfh|virtual)\b", re.I)

# Common US state abbreviations + a few country hints for region/country backfill.
_US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA",
    "ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
    "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC",
}
_COUNTRY_HINTS = {
    "germany": "DE", "deutschland": "DE", "uk": "GB", "united kingdom": "GB", "england": "GB",
    "india": "IN", "ireland": "IE", "usa": "US", "united states": "US", "us": "US",
}


def is_remote(raw: str) -> bool:
    return bool(REMOTE_MARKERS.search(raw or ""))


def parse_location(raw: str) -> Location | None:
    """Parse 'Austin, TX' / 'Berlin, Germany' / 'Hyderabad, Telangana, IN' → Location.

    Returns None for remote/unparseable strings (caller drops these).
    """
    if not raw or is_remote(raw):
        return None
    # take the first physical location if several are bundled with ; or /
    first = re.split(r"[;/]| or ", raw)[0].strip()
    parts = [p.strip() for p in first.split(",") if p.strip()]
    if not parts:
        return None

    city = parts[0]
    region: str | None = None
    country: str | None = None

    rest = parts[1:]
    for token in rest:
        upper = token.upper()
        low = token.lower()
        if upper in _US_STATES:
            region = upper
            country = country or "US"
        elif low in _COUNTRY_HINTS:
            country = _COUNTRY_HINTS[low]
        elif len(token) == 2 and upper.isalpha():
            country = country or upper
        else:
            region = region or token
    return Location(city=city, region=region, country=country)


def canonical_city(raw: str) -> str | None:
    loc = parse_location(raw)
    return loc.city.lower() if loc else None
