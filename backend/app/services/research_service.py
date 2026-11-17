"""Tavily web-search integration for NEXUS AI STUDIO."""

import httpx
from urllib.parse import urlsplit

from app.core.config import settings


TAVILY_SEARCH_URL = "https" + "://" + "api.tavily.com" + "/search"


async def search_web(query: str, max_results: int = 5) -> dict:
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
        "search_depth": "basic",
        "topic": "general",
        "max_results": max(1, min(max_results, 5)),
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
        return {
            "status": "error",
            "reason": "The web-search request timed out.",
            "results": [],
        }

    except httpx.HTTPStatusError as error:
        status_code = error.response.status_code

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

    except (httpx.HTTPError, ValueError):
        return {
            "status": "error",
            "reason": "Could not retrieve or parse Tavily search results.",
            "results": [],
        }

    results = []

    for item in data.get("results", [])[:5]:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()

        parsed_url = urlsplit(url)
        if (
            not title
            or parsed_url.scheme not in {"https", "http"}
            or not parsed_url.netloc
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            continue
            continue

        results.append({
            "title": title[:300],
            "url": url[:2000],
            "content": content[:3000],
            "score": item.get("score"),
            "published_date": item.get("published_date"),
        })

    return {
        "status": "success",
        "query": clean_query,
        "results": results,
        "sources_found": len(results),
    }
