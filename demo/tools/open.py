import asyncio
import os
from typing import Optional
from urllib.parse import urlparse

import aiofiles
import aiohttp
import megfile
from loguru import logger
from markitdown import MarkItDown
from typing_extensions import TypedDict


# Default proxy and timeout configuration
_DEFAULT_PROXY = os.getenv("HTTP_PROXY", "")
_OPEN_URL_TIMEOUT = 30


class Page(TypedDict, total=False):
    """Page content structure"""
    url: str
    host: str
    title: str
    snippet: str
    markdown: str
    site: str
    finished_at: str
    time_cost: str
    region: str


class OpenResult(TypedDict):
    """Open API return result"""
    code: int
    message: str
    page: Page


def _make_error_result(code: int, message: str, url: str) -> OpenResult:
    """Create error result"""
    return OpenResult(
        code=code,
        message=message,
        page=Page(url=url),
    )


async def _download_http(url: str, timeout: int = _OPEN_URL_TIMEOUT) -> bytes:
    """Download content via HTTP with proxy support"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
            proxy=_DEFAULT_PROXY if _DEFAULT_PROXY else None,
        ) as response:
            response.raise_for_status()
            return await response.read()


def _download_s3(url: str) -> bytes:
    """Download content from S3"""
    with megfile.smart_open(url, "rb") as f:
        return f.read()


async def _get_url_content_bytes(url: str, timeout: int = _OPEN_URL_TIMEOUT) -> bytes:
    """Get URL content as bytes, supports S3, HTTP, and local files"""
    if megfile.is_s3(url):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _download_s3, url)
    elif url.startswith("http://") or url.startswith("https://"):
        return await _download_http(url, timeout=timeout)
    else:
        # Local file
        async with aiofiles.open(url, "rb") as f:
            return await f.read()


def _parse_content_to_markdown(content_bytes: bytes, url: str) -> str:
    """Parse content to markdown format"""
    from io import BytesIO
    
    md = MarkItDown()
    # Convert bytes to BytesIO stream
    stream = BytesIO(content_bytes)
    result = md.convert_stream(stream, file_extension=None)
    return result.text_content


async def open(url: str) -> OpenResult:
    """Open a URL and retrieve its content
    
    Args:
        url: URL to open, supports HTTP/HTTPS, S3, and local file paths
        
    Returns:
        OpenResult: Web page content result
    """
    parsed_url = urlparse(url)
    host = parsed_url.netloc if parsed_url.netloc else ""
    
    try:
        # Get content bytes
        content_bytes = await _get_url_content_bytes(url)
        
        # Parse to markdown
        markdown_content = _parse_content_to_markdown(content_bytes, url)
        
        # Construct success result
        return OpenResult(
            code=0,
            message="",
            page=Page(
                url=url,
                host=host,
                markdown=markdown_content,
            ),
        )
    except aiohttp.ClientError as e:
        logger.warning(f"Open URL request failed: {e}")
        return _make_error_result(-1, f"Request failed: {str(e)}", url)
    except Exception as e:
        logger.exception(f"Unexpected error during open URL: {e}")
        return _make_error_result(-1, f"Unexpected error: {str(e)}", url)
