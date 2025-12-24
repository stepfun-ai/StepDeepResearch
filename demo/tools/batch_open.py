import asyncio
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from loguru import logger

from demo.tools.open import OpenResult, open
from demo.tools.text_truncator import format_content

# 批量打开结果临时文件目录
BATCH_OPEN_TMP_DIR = Path("/tmp/web_surfer/batch_open")


def _generate_unique_name() -> str:
    """生成唯一文件名"""
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


class BatchOpenResult(TypedDict):
    """批量打开 URL 的结果结构"""

    open_results: list[OpenResult]
    message: str
    success_count: int
    failure_count: int


async def batch_open(urls: list[str]) -> BatchOpenResult:
    """
    批量打开多个 URL，并行获取网页内容。

    Args:
        urls: 要打开的 URL 列表

    Returns:
        BatchOpenResult: 包含所有 URL 打开结果的字典
    """

    async def open_with_catch(url: str) -> OpenResult:
        """用于捕获打开失败的打开函数"""
        try:
            return await open(url)
        except Exception as e:
            logger.error(f"Failed to open URL {url}: {e}\n{traceback.format_exc()}")
            return OpenResult(
                code=-1,
                message=f"Failed to open URL: {str(e)}",
                page={"url": url},  # type: ignore
            )

    # 并行打开所有 URL
    open_results = await asyncio.gather(*[open_with_catch(url) for url in urls])

    # 统计成功和失败的数量
    success_count = sum(1 for result in open_results if result.get("code", -1) == 0)
    failure_count = len(open_results) - success_count

    logger.info(
        f"批量打开完成: 共 {len(urls)} 个 URL, "
        f"成功 {success_count} 个, 失败 {failure_count} 个"
    )

    return BatchOpenResult(
        open_results=list(open_results),
        message=f"批量打开完成: 成功 {success_count}/{len(urls)}",
        success_count=success_count,
        failure_count=failure_count,
    )


def format_open_results(result: BatchOpenResult) -> str:
    """格式化批量打开结果为对 agent 友好的 XML 格式

    Args:
        result: 批量打开的结果

    Returns:
        格式化后的批量网页内容 XML 文本
    """
    open_results = result["open_results"]

    lines: list[str] = []

    # 开始批量结果的 XML 结构
    lines.append("<batch_open_results>")

    # 添加批量操作的元信息
    lines.append("<batch_metadata>")
    lines.append(f"<total_urls>{len(open_results)}</total_urls>")
    lines.append(f"<success_count>{result['success_count']}</success_count>")
    lines.append(f"<failure_count>{result['failure_count']}</failure_count>")
    lines.append("</batch_metadata>")

    # 如果没有任何结果
    if not open_results:
        lines.append("<no_urls>没有提供任何 URL！</no_urls>")
    else:
        _save_unique_name = _generate_unique_name()
        # 格式化每个 URL 的打开结果
        for idx, open_result in enumerate(open_results, 1):
            lines.append(f'<url_result index="{idx}">')

            # 检查是否有错误
            if open_result.get("code", 0) != 0:
                lines.append("<error>")
                lines.append(f"<code>{open_result.get('code', 'unknown')}</code>")
                if message := open_result.get("message"):
                    lines.append(f"<message>{message}</message>")
                if page := open_result.get("page"):
                    if url := page.get("url"):
                        lines.append(f"<failed_url>{url}</failed_url>")
                lines.append("</error>")
            else:
                # 获取页面数据
                page = open_result.get("page")
                if not page:
                    lines.append("<no_content>未能获取页面内容</no_content>")
                else:
                    # 添加页面元信息
                    lines.append("<page_metadata>")
                    if url := page.get("url"):
                        lines.append(f"<url>{url}</url>")
                    if host := page.get("host"):
                        lines.append(f"<host>{host}</host>")
                    if site := page.get("site"):
                        lines.append(f"<site>{site}</site>")
                    lines.append("</page_metadata>")

                    # 页面标题
                    if title := page.get("title"):
                        lines.append(f"<title>{title.strip()}</title>")

                    # 页面摘要
                    if snippet := page.get("snippet"):
                        lines.append("<snippet>")
                        snippet_result = format_content(snippet, max_length=200)
                        lines.append(snippet_result.content)
                        lines.append("</snippet>")

                    # 页面主要内容（Markdown格式）
                    markdown = page.get("markdown", "")
                    if markdown and markdown.strip():
                        lines.append("<content>")

                        # 批量处理时使用较小的内容长度限制
                        format_result = format_content(
                            markdown,
                            max_length=4096,
                            min_ratio=0.8,
                        )
                        lines.append(format_result.content)

                        # 如果内容被截断，保存完整内容到临时文件
                        if format_result.is_truncated:
                            BATCH_OPEN_TMP_DIR.mkdir(parents=True, exist_ok=True)
                            tmp_file = BATCH_OPEN_TMP_DIR / f"{_save_unique_name}_page_{idx}.md"
                            tmp_file.write_text(markdown, encoding="utf-8")
                            lines.append(
                                f"<full_content_file>内容因过长被截断，完整内容请查看临时文件：{tmp_file}</full_content_file>"
                            )

                        lines.append("</content>")

                    # 如果没有 markdown 但有其他信息
                    elif not title and not snippet:
                        lines.append("<no_content>页面内容为空</no_content>")

            lines.append("</url_result>")

    lines.append("</batch_open_results>")

    return "\n".join(lines)