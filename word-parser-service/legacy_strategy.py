from __future__ import annotations

from dataclasses import dataclass

from word_parser import ParsedTable


@dataclass
class LegacySelection:
    tables: list[ParsedTable]
    blocks: list[dict] | None
    mode: str
    note: str | None = None


def choose_legacy_representation(
    html_blocks: list[dict],
    html_tables: list[ParsedTable],
    text_tables: list[ParsedTable],
) -> LegacySelection:
    if html_tables and not text_tables:
        return LegacySelection(html_tables, html_blocks, "html")
    if text_tables and not html_tables:
        return LegacySelection(text_tables, None, "text")
    if not html_tables and not text_tables:
        return LegacySelection([], None, "none")

    html_fragment_score = _fragment_score(html_tables)
    text_fragment_score = _fragment_score(text_tables)

    if _should_prefer_text(html_tables, text_tables, html_fragment_score, text_fragment_score):
        return LegacySelection(
            text_tables,
            None,
            "text",
            "旧版 .doc 的 HTML 结构过碎，已切换为文本分段模式",
        )
    return LegacySelection(html_tables, html_blocks, "html")


def _should_prefer_text(
    html_tables: list[ParsedTable],
    text_tables: list[ParsedTable],
    html_fragment_score: float,
    text_fragment_score: float,
) -> bool:
    if not text_tables:
        return False
    if (
        len(html_tables) >= 40
        and len(text_tables) <= len(html_tables) * 0.8
        and _tiny_table_ratio(html_tables) >= 0.35
    ):
        return True
    if html_fragment_score >= 0.32 and len(text_tables) < len(html_tables):
        return True
    if html_fragment_score - text_fragment_score >= 0.18 and len(text_tables) <= len(html_tables):
        return True
    return False


def _fragment_score(tables: list[ParsedTable]) -> float:
    if not tables:
        return 0.0
    tiny = sum(1 for table in tables if len(table.rows) <= 2)
    narrow = sum(1 for table in tables if table.col_count <= 2)
    return (tiny / len(tables)) * 0.7 + (narrow / len(tables)) * 0.3


def _tiny_table_ratio(tables: list[ParsedTable]) -> float:
    if not tables:
        return 0.0
    return sum(1 for table in tables if len(table.rows) <= 2) / len(tables)
