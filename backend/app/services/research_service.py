"""Tavily web-search integration for NEXUS AI STUDIO."""

import ipaddress
import logging
import math
import re
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)
TAVILY_SEARCH_URL = "https" + "://" + "api.tavily.com" + "/search"
SOURCE_PRIORITY = {
    "official": 0,
    "academic_or_research": 1,
    "established_news": 2,
    "other": 3,
}
SOURCE_ROLE_PRIORITY = {"primary": 0, "secondary": 1}
QUERY_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "for",
    "from", "how", "in", "into", "is", "it", "of", "on", "or", "that",
    "the", "their", "this", "to", "was", "were", "what", "when", "where",
    "which", "who", "why", "with",
}


def _source_type(domain: str) -> str:
    official_domains = {
        "gov.uk", "gov.au", "gc.ca", "govt.nz", "who.int", "un.org",
        "europa.eu", "unicef.org", "icj-cij.org", "oecd.org",
        "worldbank.org", "imf.org", "wto.org", "ilo.org", "unesco.org",
        "unhcr.org", "iaea.org",
    }
    if (
        domain.endswith(".gov")
        or domain.endswith(".gov.uk")
        or any(domain == item or domain.endswith(f".{item}") for item in official_domains)
    ):
        return "official"
    research_domains = {
        "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "nature.com", "science.org",
    }
    if domain.endswith(".edu") or any(
        domain == item or domain.endswith(f".{item}")
        for item in research_domains
    ):
        return "academic_or_research"
    news_domains = {"reuters.com", "apnews.com", "bbc.com", "bbc.co.uk"}
    if any(domain == item or domain.endswith(f".{item}") for item in news_domains):
        return "established_news"
    return "other"


def _source_role(title: str, url: str, source_type: str) -> str:
    title_lower = title.lower()
    parsed_url = urlsplit(url)
    path = parsed_url.path.lower()
    hostname = (parsed_url.hostname or "").lower()
    if (
        "research.un.org" in hostname
        or re.search(r"\b(story|stories|overview|history of)\b", title_lower)
        or (
            re.search(r"\bguide(s)?\b", title_lower)
            and (
                "library" in title_lower
                or "research" in title_lower
                or hostname.startswith("guides.")
                or (source_type == "academic_or_research" and "/guide" in path)
            )
        )
        or "encyclopedia" in title_lower
    ):
        return "secondary"

    primary_indicators = (
        "charter", "treaty", "resolution", "official records", "full text",
        "transcript", "document",
    )
    if source_type == "official" and any(
        indicator in title_lower or indicator in path
        for indicator in primary_indicators
    ):
        return "primary"
    return "secondary"


def _normalize_source(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None

    title = " ".join(str(item.get("title") or "").split())
    url = str(item.get("url") or "").strip()
    excerpt = str(item.get("content") or item.get("excerpt") or "").strip()
    if any(ord(character) <= 0x20 for character in url):
        return None
    try:
        parsed_url = urlsplit(url)
    except ValueError:
        return None
    if (
        not title
        or parsed_url.scheme.lower() not in {"https", "http"}
        or not parsed_url.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
    ):
        return None

    domain = parsed_url.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(domain)
    except ValueError:
        address = None
    if domain == "localhost" or (address and not address.is_global):
        return None

    normalized_url = urlunsplit((
        parsed_url.scheme.lower(),
        parsed_url.netloc.lower(),
        parsed_url.path or "/",
        parsed_url.query,
        "",
    ))
    score = item.get("score", item.get("relevance"))
    try:
        relevance = float(score) if score is not None else None
    except (TypeError, ValueError):
        relevance = None
    if relevance is not None and not math.isfinite(relevance):
        relevance = None

    published = str(item.get("published_date") or "").strip() or None
    source_type = _source_type(domain)
    source_role = _source_role(title, normalized_url, source_type)
    hostname = (urlsplit(normalized_url).hostname or "").lower()
    is_reference_guide = (
        source_role == "secondary"
        and (
            "research.un.org" in hostname
            or (
                re.search(r"\bguide(s)?\b", title, re.IGNORECASE)
                and (
                    "library" in title.lower()
                    or "research" in title.lower()
                    or hostname.startswith("guides.")
                )
            )
        )
    )
    return {
        "title": title[:300],
        "url": normalized_url[:2000],
        "domain": domain,
        "excerpt": excerpt[:2000],
        "published_date": published[:100] if published else None,
        "source_type": source_type,
        "source_role": source_role,
        "source_kind": (
            "reference_guide"
            if is_reference_guide
            else "document_or_record"
            if source_role == "primary"
            else "secondary_publication"
        ),
        "relevance": relevance,
    }


def _query_terms(value: str) -> set[str]:
    terms = {
        token for token in re.findall(r"[a-z0-9]{2,}", value.lower())
        if token not in QUERY_STOP_WORDS
    }
    if "united" in terms and "nations" in terms:
        terms.difference_update({"united", "nations"})
        terms.add("united_nations")
    return terms


def _topic_relevance(query: str, source: dict) -> float:
    query_terms = _query_terms(query)
    if not query_terms:
        return 0.0

    text = f"{source.get('title', '')} {source.get('excerpt', '')}".lower()
    source_terms = _query_terms(text)
    if "united_nations" in query_terms and re.search(r"\bun\b", text):
        source_terms.add("united_nations")
    matched = query_terms.intersection(source_terms)
    return len(matched) / len(query_terms)


def _publication_day(source: dict) -> int:
    published = source.get("published_date")
    if not published:
        return 0
    try:
        return date.fromisoformat(str(published)[:10]).toordinal()
    except ValueError:
        return 0


def _prepare_sources(
    items: object,
    max_results: int,
    query: str = "",
) -> list[dict]:
    if not isinstance(items, list):
        return []
    sources_by_url = {}
    for item in items:
        source = _normalize_source(item)
        if source is None:
            continue
        topic_relevance = _topic_relevance(query, source) if query else 1.0
        if query and topic_relevance == 0:
            continue
        source["topic_relevance"] = topic_relevance
        existing = sources_by_url.get(source["url"])
        if existing is None:
            sources_by_url[source["url"]] = source
        else:
            if len(source["excerpt"]) > len(existing["excerpt"]):
                existing["excerpt"] = source["excerpt"]
            if source.get("relevance") is not None:
                existing["relevance"] = max(
                    existing.get("relevance") or 0,
                    source["relevance"],
                )
            if not existing.get("published_date") and source.get("published_date"):
                existing["published_date"] = source["published_date"]
            existing["topic_relevance"] = max(
                existing["topic_relevance"],
                topic_relevance,
            )

    sources = sorted(
        sources_by_url.values(),
        key=lambda source: (
            SOURCE_ROLE_PRIORITY.get(source.get("source_role"), 1),
            SOURCE_PRIORITY.get(source.get("source_type"), 3),
            -source.get("topic_relevance", 0.0),
            -(source.get("relevance") or 0.0),
            -_publication_day(source),
        ),
    )[:max(1, min(max_results, 10))]
    for source_id, source in enumerate(sources, start=1):
        source["id"] = source_id
    return sources


async def search_web(
    query: str,
    max_results: int = 5,
    relevance_query: str | None = None,
) -> dict:
    """Search the web and return a bounded set of source records."""

    api_key = settings.tavily_api_key.strip()

    if not api_key:
        return {
            "status": "unavailable",
            "reason": "TAVILY_API_KEY is not configured.",
            "results": [],
        }

    clean_query = " ".join(query.split())[:390]

    if not clean_query:
        return {
            "status": "unavailable",
            "reason": "The research query is empty.",
            "results": [],
        }

    payload = {
        "query": clean_query,
        "search_depth": "advanced",
        "topic": "general",
        "max_results": max(1, min(max_results, 10)),
        "include_answer": False,
        "include_raw_content": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        timeout = httpx.Timeout(25.0, connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                TAVILY_SEARCH_URL,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

    except httpx.TimeoutException:
        logger.warning("Tavily search timed out (query_chars=%d).", len(clean_query))
        return {
            "status": "error",
            "reason": "The web-search request timed out.",
            "results": [],
        }

    except httpx.HTTPStatusError as error:
        status_code = error.response.status_code
        logger.warning("Tavily search returned HTTP %d.", status_code)

        if status_code == 401:
            reason = "Tavily rejected the API key. Check TAVILY_API_KEY."
        elif status_code == 429:
            reason = "Tavily rate limit or usage limit reached."
        else:
            reason = f"Tavily returned HTTP {status_code}."

        return {
            "status": "error",
            "reason": reason,
            "results": [],
        }

    except (httpx.HTTPError, ValueError) as error:
        logger.warning("Tavily search failed (%s).", type(error).__name__)
        return {
            "status": "error",
            "reason": "Could not retrieve or parse Tavily search results.",
            "results": [],
        }

    if not isinstance(data, dict):
        logger.warning("Tavily returned a non-object response.")
        return {
            "status": "error",
            "reason": "Tavily returned an invalid response.",
            "results": [],
        }
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        logger.warning("Tavily response did not contain a results list.")
        return {
            "status": "error",
            "reason": "Tavily returned an invalid results field.",
            "results": [],
        }
    results = _prepare_sources(
        raw_results,
        max_results,
        query=relevance_query or clean_query,
    )
    logger.info(
        "Tavily search completed (query_chars=%d, candidates=%d, accepted=%d).",
        len(clean_query),
        len(raw_results),
        len(results),
    )

    return {
        "status": "success",
        "query": clean_query,
        "results": results,
        "sources_found": len(results),
    }
