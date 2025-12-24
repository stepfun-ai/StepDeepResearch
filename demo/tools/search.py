import os

import aiohttp
from loguru import logger
from typing_extensions import NotRequired, TypedDict


class SearchResultItem(TypedDict):
    url: str
    position: int
    title: str
    time: str
    snippet: str
    content: str


class SearchResult(TypedDict):
    query: str
    category: NotRequired[str]
    results: list[SearchResultItem]


_DEFAULT_SEARCH_URL = os.getenv("STEP_SEARCH_API_BASE", "https://api.stepfun.com") + "/v1/search"
# Prefer the dedicated search key; fall back to legacy STEP_API_KEY for compatibility.
_DEFAULT_AUTH_BEARER = os.getenv("STEP_SEARCH_API_KEY") or os.getenv("STEP_API_KEY", "")


async def search(
        query: str,
        topk: int = 10,
        base_url: str = _DEFAULT_SEARCH_URL,
        auth_bearer: str = _DEFAULT_AUTH_BEARER,
) -> SearchResult:
    """Execute search request.
    
    Args:
        query: Search query.
        topk: Number of results to return.
        base_url: Search API URL.
        auth_bearer: Authorization Bearer token.
        
    Returns:
        SearchResult: Search results, returns empty list in results on error.
    """
    """
    New API response format:
    {
        "query": "python",
        "category": "programming",
        "results": [
            {
                "url": "https://github.com/...",
                "position": 1,
                "title": "...",
                "time": "2017-02-13T20:34:32",
                "snippet": "...",
                "content": "..."
            },
            ...
        ]
    }
    """
    # Limit topk to range [1, 20]
    topk = max(1, min(topk, 20))
    
    # Build request parameters
    request_params = {
        "query": query,
        "n": topk,
    }

    logger.debug(f"Searching with query: {query}, topk: {topk}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    base_url,
                    json=request_params,
                    headers={
                        "Authorization": f"Bearer {auth_bearer}",
                        "Content-Type": "application/json",
                    },
            ) as response:
                if not response.ok:
                    error_text = await response.text()
                    logger.warning(f"Search API error: {response.status} - {error_text}")
                    return {
                        "query": query,
                        "results": [],
                    }
                api_result = await response.json()
                if "error" in api_result:
                    logger.warning(f"Search API returned error: {api_result['error']}")

                return api_result
    except aiohttp.ClientError as e:
        logger.warning(f"Search request failed: {e}")
        return {
            "query": query,
            "results": [],
        }
    except Exception as e:
        logger.exception(f"Unexpected error during search: {e}")
        return {
            "query": query,
            "results": [],
        }
