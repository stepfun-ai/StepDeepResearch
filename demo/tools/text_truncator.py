"""文本截断工具模块

提供统一的文本截断功能，优化为默认使用句子或段落边界截断策略。
"""

import re
from dataclasses import dataclass

DEFAULT_SUFFIX = " ... [Total Length {original_length}({original_lines} lines) > {max_length}, truncated to {truncated_length}({truncated_lines} lines)]"

def truncate_text(
    text: str,
    max_length: int,
    truncate_suffix: str = DEFAULT_SUFFIX,
    min_ratio: float = 0.7,
) -> str:
    """截断文本到指定长度，默认使用句子或段落边界策略

    Args:
        text: 要截断的文本
        max_length: 最大长度
        suffix: 截断后添加的后缀
        min_ratio: 最小保留比例，用于判断截断点是否合理

    Returns:
        截断后的文本
    """
    if not text or len(text) <= max_length:
        return text

    # 先截取到最大长度
    truncated = text[:max_length]

    # 找到合适的截断点，默认策略：优先段落边界，其次句子边界
    cutoff_point = -1

    # 优先尝试段落边界
    para_boundary = truncated.rfind("\n\n")
    if para_boundary > max_length * min_ratio:
        cutoff_point = para_boundary
    else:
        # 退回到句子边界
        cutoff_point = _find_sentence_boundary(truncated, max_length * min_ratio)

    suffix = truncate_suffix.format(
        original_length=len(text),
        max_length=max_length,
        truncated_length=len(truncated),
        original_lines=text.count("\n") + 1,
        truncated_lines=truncated.count("\n") + 1,
    )
    # 如果找到了合适的截断点
    if cutoff_point > 0:
        # 对于段落边界，不需要包含换行符
        if cutoff_point == truncated.rfind("\n\n"):
            return text[:cutoff_point] + "\n\n" + suffix
        else:
            # 对于句子边界，包含句号等标点
            return text[: cutoff_point + 1] + (
                " " + suffix if not text[cutoff_point].isspace() else suffix
            )

    # 如果没有找到合适的截断点，硬截断
    return truncated + suffix


def _find_sentence_boundary(text: str, min_position: float) -> int:
    """使用正则表达式查找句子边界

    Args:
        text: 文本
        min_position: 最小位置（低于此位置的边界不考虑）

    Returns:
        句子边界位置，如果没有找到返回 -1
    """
    # 使用正则表达式查找各种句子结束标记
    # 包括中英文句号、感叹号、问号、换行符
    sentence_end_pattern = r"[。.！!？?\n]"

    # 找到所有句子结束标记的位置
    matches = list(re.finditer(sentence_end_pattern, text))

    # 从后向前查找第一个满足最小位置要求的标记
    for match in reversed(matches):
        if match.start() >= min_position:
            return match.start()

    return -1


def clean_text_whitespace(text: str, max_consecutive_newlines: int = 3) -> str:
    """清理文本中的多余空白字符

    Args:
        text: 要清理的文本
        max_consecutive_newlines: 最大连续换行数

    Returns:
        清理后的文本
    """
    if not text:
        return text

    # 移除多余的换行符
    newline_pattern = r"\n{" + str(max_consecutive_newlines + 1) + ",}"
    replacement = "\n" * max_consecutive_newlines
    text = re.sub(newline_pattern, replacement, text)

    # 移除多余的空格和制表符（保留单个空格）
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def clean_markdown_content(text: str) -> str:
    """清理 Markdown 内容中的噪音

    Args:
        text: Markdown 格式的文本

    Returns:
        清理后的文本
    """
    if not text:
        return text

    # 统一分隔线格式
    text = re.sub(r"(-{3,}|={3,}|\*{3,})\n+", "---\n", text)

    # 清理图片链接中的过长URL（保留图片说明文字）
    text = re.sub(r"!\[([^\]]*)\]\([^\)]{100,}\)", r"![📷 \1]", text)

    # 清理过长的纯URL链接
    text = re.sub(r"https?://[^\s\)]{100,}", "[长链接已省略]", text)

    return text


@dataclass
class FormatResult:
    content: str
    is_clean_text_whitespace: bool
    is_clean_markdown: bool
    is_truncated: bool


def format_content(
    content: str,
    max_length: int = 10240,
    truncate_suffix: str = DEFAULT_SUFFIX,
    min_ratio: float = 0.8,
) -> FormatResult:
    """格式化内容文本，支持自动保存完整内容

    Args:
        content: 内容文本
        max_length: 最大长度
        truncate_suffix: 截断后缀
        min_ratio: 最小保留比例

    Returns:
        str: 格式化后的内容
    """
    result = FormatResult(
        content=content,
        is_clean_text_whitespace=False,
        is_clean_markdown=False,
        is_truncated=False,
    )

    # 清理空白字符
    content = clean_text_whitespace(content)
    result.is_clean_text_whitespace = len(content) < len(result.content)
    result.content = content

    # 清理 Markdown 噪音
    content = clean_markdown_content(content)
    result.is_clean_markdown = len(content) < len(result.content)
    result.content = content

    content = truncate_text(
        content,
        max_length,
        truncate_suffix=truncate_suffix,
        min_ratio=min_ratio,
    )
    result.is_truncated = len(content) < len(result.content)
    result.content = content

    return result
