import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger
from typing import TypedDict
import asyncio

from demo.tools.search import SearchResult, search
from demo.tools.text_truncator import format_content


# 批量搜索结果临时文件目录
BATCH_SEARCH_TMP_DIR = Path("/tmp/web_surfer/batch_search")


def _generate_cite_index(query_idx: int, item_idx: int, url: str) -> str:
    """生成唯一的引用索引"""
    hash_input = f"{query_idx}_{item_idx}_{url}"
    return f"web_{hashlib.md5(hash_input.encode()).hexdigest()[:8]}"


class BatchSearchResult(TypedDict):
    search_results: list[SearchResult]
    message: str


def _deduplicate_results(search_results: list[SearchResult]) -> None:
    """对搜索结果进行 URL 去重（原地修改）

    Args:
        search_results: 搜索结果列表
    """
    seen_urls: set[str] = set()
    for search_result in search_results:
        results = search_result.get("results", [])
        filtered_results = []
        for item in results:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                filtered_results.append(item)
        search_result["results"] = filtered_results


def _rerank(search_results: list[SearchResult], topk: int) -> None:
    """对搜索结果进行重排序（原地修改）

    分配策略：
    - 基础配额：每个查询分配 topk / N 个结果
    - 动态补偿：如果某个查询结果不足配额，剩余配额分配给其他查询

    Args:
        search_results: 搜索结果列表
        topk: 总共需要的结果数量
    """
    n_queries = len(search_results)
    base_quota = topk // n_queries
    remaining = topk

    # 第一轮：按基础配额分配
    actual_counts = []
    for search_result in search_results:
        available = len(search_result.get("results", []))
        take = min(available, base_quota)
        actual_counts.append(take)
        remaining -= take

    # 第二轮：将剩余配额分配给有更多结果的查询
    if remaining > 0:
        for i, search_result in enumerate(search_results):
            if remaining <= 0:
                break
            available = len(search_result.get("results", []))
            extra = min(available - actual_counts[i], remaining)
            if extra > 0:
                actual_counts[i] += extra
                remaining -= extra

    # 应用配额
    for i, search_result in enumerate(search_results):
        results = search_result.get("results", [])
        search_result["results"] = results[:actual_counts[i]]
        logger.debug(
            f"{search_result['query']}: {len(results)} available, "
            f"taking {actual_counts[i]} results"
        )


async def batch_search(
    querys: list[str],
    topk: int = 50,
) -> BatchSearchResult:
    """
    用户输入 N 个查询，返回共 topk 个搜索结果。

    分配策略：
    - 基础配额：每个查询分配 topk / N 个结果
    - 动态补偿：如果某个查询结果不足配额，剩余配额分配给其他查询

    例如：6 个查询，topk=60，每个查询基础配额 10 条
    如果某个查询只有 5 条结果，剩余 5 条配额会分给其他查询

    Args:
        querys: 查询列表
        topk: 返回的总结果数量，默认 50

    Returns:
        BatchSearchResult: 批量搜索结果
    """
    # 并行执行所有搜索
    search_results = await asyncio.gather(
        *[search(query, topk=topk) for query in querys]
    )

    # URL 去重
    _deduplicate_results(search_results)

    # 重排序
    _rerank(search_results, topk)

    return BatchSearchResult(
        search_results=search_results,
        message="success",
    )


def _generate_unique_name() -> str:
    """生成唯一文件名"""
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def format_search_results(result: BatchSearchResult) -> str:
    """格式化批量搜索结果为对 agent 友好的 XML 格式

    Args:
        result: 批量搜索结果

    Returns:
        格式化后的批量搜索结果 XML 文本
    """
    search_results = result["search_results"]

    lines: list[str] = []

    # 开始批量搜索结果的 XML 结构
    lines.append("<batch_search_results>")

    # 添加批量搜索的元信息
    lines.append("<batch_metadata>")
    total_items = sum(len(r.get("results", [])) for r in search_results)
    lines.append(f"共 {len(search_results)} 个查询，{total_items} 个搜索结果")
    lines.append("</batch_metadata>")

    # 如果没有任何搜索结果
    if not search_results:
        lines.append("<no_queries>没有执行任何搜索查询！</no_queries>")
    else:
        _save_unique_name = _generate_unique_name()
        # 格式化每个查询的搜索结果
        for query_idx, r in enumerate(search_results, 1):
            lines.append(f'<query_result index="{query_idx}">')

            results = r.get("results", [])
            
            # 添加查询元信息
            lines.append("<query_metadata>")
            lines.append(f"<query>{r['query']}</query>")
            lines.append(f"<result_count>{len(results)}</result_count>")
            lines.append("</query_metadata>")

            # 如果这个查询没有搜索结果
            if not results:
                lines.append(
                    f"<no_results_found>查询 '{r['query']}' 没有发现搜索结果！</no_results_found>"
                )
            else:
                lines.append("<items>")
                # 格式化每个搜索结果项
                for item_idx, item in enumerate(results, 1):
                    # 提取核心信息
                    title = item.get("title", "无标题")
                    url = item.get("url", "")
                    snippet = item.get("snippet", "")
                    content = item.get("content", "")
                    time = item.get("time", "")

                    # 从 URL 提取 site
                    site = ""
                    if url:
                        try:
                            parsed = urlparse(url)
                            site = parsed.netloc
                        except Exception:
                            pass

                    # 生成引用索引
                    cite_index = _generate_cite_index(query_idx, item_idx, url)

                    # 构建结果项
                    lines.append(f'<item index="{item_idx}">')
                    lines.append(f"<cite_index>{cite_index}</cite_index>")
                    lines.append(f"<title>{title}</title>")
                    lines.append(f"<url>{url}</url>")

                    if site:
                        lines.append(f"<site>{site}</site>")
                    if time:
                        lines.append(f"<published_time>{time}</published_time>")

                    # 添加摘要
                    if snippet:
                        lines.append("<snippet>")
                        snippet_result = format_content(snippet, max_length=300)
                        lines.append(snippet_result.content)
                        lines.append("</snippet>")

                    # 如果有详细内容，处理内容
                    if content and content.strip() and content != snippet:
                        lines.append("<content>")
                        format_result = format_content(
                            content,
                            max_length=1024,
                            min_ratio=0.8,
                        )
                        lines.append(format_result.content)

                        # 如果内容被截断，保存完整内容到临时文件
                        if format_result.is_truncated:
                            BATCH_SEARCH_TMP_DIR.mkdir(parents=True, exist_ok=True)
                            tmp_file = BATCH_SEARCH_TMP_DIR / f"{_save_unique_name}-query_{query_idx}-item_{item_idx}.md"
                            tmp_file.write_text(content, encoding="utf-8")
                            lines.append(
                                f"<full_content_file>内容因过长被截断，完整内容请查看临时文件：{tmp_file}</full_content_file>"
                            )

                        lines.append("</content>")
                    lines.append("</item>")
                lines.append("</items>")

            lines.append("</query_result>")

    lines.append("</batch_search_results>")

    return "\n".join(lines)
