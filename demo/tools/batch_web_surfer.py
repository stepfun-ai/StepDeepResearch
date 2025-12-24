import json
from typing import Annotated, Literal

from loguru import logger

from cortex.model.definition import ContentBlockType
from cortex.tools.function_tool import FunctionTool
from .batch_open import batch_open, format_open_results
from .batch_search import batch_search, format_search_results


def _ensure_list(value: list[str] | str | None) -> list[str]:
    """Ensure value is a list, compatible with LLM passing JSON string."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        # Try to parse JSON string
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
        # If not a JSON array, treat as single query item
        return [value] if value.strip() else []
    return []


async def batch_web_surfer(
        action: Annotated[Literal["batch_search", "batch_open"], "要执行的批量操作类型"],
        queries: Annotated[list[str] | None, "batch_search 时必须提供，要搜索的查询内容列表"] = None,
        urls: Annotated[list[str] | None, "batch_open 时必须提供，要打开的网址列表"] = None,
        topk: Annotated[int, "batch_search 时可选，总共返回的搜索结果数量，范围 1-200"] = 50,
):
    """批量 Web 浏览器工具，支持批量搜索和批量打开网页

    批量搜索功能：
    - 同时执行多个搜索查询，提高搜索效率
    - 自动使用 reranker 对结果进行智能排序和过滤（如果配置可用）
    - 返回总共 topk 个最相关的搜索结果

    批量打开功能：
    - 并行打开多个 URL，快速获取多个网页内容
    - 自动处理失败的 URL，提供错误信息
    - 支持内容过长时自动保存到临时文件

    示例用法：
    1. 批量搜索：
       action="batch_search", queries=["Python教程", "机器学习入门"], topk=20

    2. 批量打开：
       action="batch_open", urls=["https://example1.com", "https://example2.com"]
    """

    # Handle parameters, compatible with LLM passing JSON string
    queries_list = _ensure_list(queries)
    urls_list = _ensure_list(urls)

    match action:
        case "batch_search":
            if not queries_list:
                raise ValueError(
                    "batch_search action requires a list of queries"
                )

            # Execute batch search
            raw_result = await batch_search(querys=queries_list, topk=topk)

            # Format results
            formatted_result = format_search_results(raw_result)

        case "batch_open":
            if not urls_list:
                raise ValueError("batch_open action requires a list of URLs")

            # Execute batch open
            raw_result = await batch_open(urls=urls_list)

            # Format results
            formatted_result = format_open_results(raw_result)

        case _:
            raise ValueError(
                f"Invalid action parameter: {action}, must be 'batch_search' or 'batch_open'"
            )
    result = [
        {
            "type": ContentBlockType.TOOLRESULT.value,
            "content": [
                {
                    "type": ContentBlockType.TEXT.value,
                    ContentBlockType.TEXT.value: formatted_result,
                }
            ]
        }
    ]
    return result


def create_batch_web_surfer_tool():
    """Create batch_web_surfer tool.

    Returns:
        FunctionTool: batch_web_surfer tool instance.
    """
    function_tool = FunctionTool(
        name="batch_web_surfer",
        func=batch_web_surfer,
        description="""批量 Web 浏览器工具，支持批量搜索和批量打开网页

        批量搜索功能：
        - 同时执行多个搜索查询，提高搜索效率
        - 自动使用 reranker 对结果进行智能排序和过滤（如果配置可用）
        - 返回总共 topk 个最相关的搜索结果

        批量打开功能：
        - 并行打开多个 URL，快速获取多个网页内容
        - 自动处理失败的 URL，提供错误信息
        - 支持内容过长时自动保存到临时文件

        示例用法：
        1. 批量搜索：
           action="batch_search", queries=["Python教程", "机器学习入门"], topk=20

        2. 批量打开：
           action="batch_open", urls=["https://example1.com", "https://example2.com"]
        """,
    )

    logger.info("batch_web_surfer tool registered successfully")
    return function_tool
