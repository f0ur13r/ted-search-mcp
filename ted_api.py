"""Small, dependency-free client for the public TED Search API v3."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
RETURN_FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "publication-date",
    "notice-type",
    "classification-cpv",
    "place-of-performance",
    "description-proc",
    "deadline-receipt-tender-date-lot",
    "estimated-value-proc",
    "estimated-value-cur-proc",
    "procedure-identifier",
    "links",
]


class TedApiError(RuntimeError):
    """A useful, model-safe error returned by TED or the network."""


def _date(value: str, name: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%Y%m%d")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO date in YYYY-MM-DD format") from exc


def _quoted(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("free_text_query cannot be blank")
    if len(cleaned) > 500:
        raise ValueError("free_text_query must be 500 characters or fewer")
    return '"' + cleaned.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_expert_query(
    date_from: str,
    date_to: str,
    country: str | None = None,
    cpv_codes: list[str] | None = None,
    free_text_query: str | None = None,
) -> str:
    """Build a constrained TED expert query from safe, typed inputs."""
    start = _date(date_from, "date_from")
    end = _date(date_to, "date_to")
    if start > end:
        raise ValueError("date_from must be on or before date_to")

    clauses = [f"publication-date >= {start}", f"publication-date <= {end}"]
    if country:
        country = country.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", country):
            raise ValueError("country must be a three-letter code such as DEU")
        clauses.append(f"place-of-performance IN ({country})")

    if cpv_codes:
        normalized = []
        for cpv in cpv_codes:
            value = str(cpv).strip().replace("-", "")
            if not re.fullmatch(r"\d{2,8}\*?", value):
                raise ValueError(
                    "each CPV code must contain 2-8 digits, optionally followed by *"
                )
            normalized.append(value)
        clauses.append(f"classification-cpv IN ({','.join(dict.fromkeys(normalized))})")

    if free_text_query:
        clauses.append(f"FT ~ {_quoted(free_text_query)}")
    return " AND ".join(clauses)


def _localized(value: Any, preferred: tuple[str, ...] = ("deu", "eng")) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return next((str(item) for item in value if item), None)
    if isinstance(value, dict):
        for language in preferred:
            if language in value:
                return _localized(value[language], ())
        for item in value.values():
            result = _localized(item, ())
            if result:
                return result
    return str(value)


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return list(dict.fromkeys(str(item) for item in values if item is not None))


def _ted_url(raw: dict[str, Any], publication_number: str | None) -> str | None:
    html = raw.get("links", {}).get("html", {})
    for language in ("DEU", "ENG"):
        if html.get(language):
            return html[language]
    if html:
        return next(iter(html.values()))
    if publication_number:
        return f"https://ted.europa.eu/en/notice/-/detail/{publication_number}"
    return None


def normalize_notice(raw: dict[str, Any]) -> dict[str, Any]:
    number = raw.get("publication-number")
    description = _localized(raw.get("description-proc"))
    return {
        "publication_number": number,
        "procedure_identifier": raw.get("procedure-identifier"),
        "title": _localized(raw.get("notice-title")),
        "buyer": _localized(raw.get("buyer-name")),
        "publication_date": raw.get("publication-date"),
        "submission_deadlines": _list(raw.get("deadline-receipt-tender-date-lot")),
        "notice_type": raw.get("notice-type"),
        "cpv_codes": _list(raw.get("classification-cpv")),
        "places_of_performance": _list(raw.get("place-of-performance")),
        "description": description,
        "estimated_value": raw.get("estimated-value-proc"),
        "estimated_value_currency": raw.get("estimated-value-cur-proc"),
        "ted_url": _ted_url(raw, number),
    }


def search_ted(
    date_from: str,
    date_to: str,
    country: str | None = None,
    cpv_codes: list[str] | None = None,
    free_text_query: str | None = None,
    max_results: int = 50,
    *,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    """Search TED once and return normalized notices (maximum 250)."""
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise ValueError("max_results must be an integer")
    if not 1 <= max_results <= 250:
        raise ValueError("max_results must be between 1 and 250")

    query = build_expert_query(date_from, date_to, country, cpv_codes, free_text_query)
    payload = {
        "query": query,
        "fields": RETURN_FIELDS,
        "page": 1,
        "limit": max_results,
        "scope": "ALL",
        "paginationMode": "PAGE_NUMBER",
        "onlyLatestVersions": True,
    }
    request = Request(
        TED_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "ted-search-mcp/0.1"},
        method="POST",
    )
    try:
        with opener(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise TedApiError(f"TED returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise TedApiError(f"Could not reach TED: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TedApiError("TED returned an invalid JSON response") from exc

    notices = [normalize_notice(item) for item in body.get("notices", [])]
    return {
        "query": query,
        "returned_count": len(notices),
        "total_matching_count": body.get("totalNoticeCount"),
        "timed_out": bool(body.get("timedOut", False)),
        "notices": notices,
    }
