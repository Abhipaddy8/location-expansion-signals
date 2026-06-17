"""Shared fixture bodies for tests."""

from pathlib import Path

_FIX = Path(__file__).parent / "fixtures"

GREENHOUSE_BODY = (_FIX / "greenhouse_intercom.json").read_text()
NEWS_BODY = (_FIX / "news_intercom_berlin.xml").read_text()
