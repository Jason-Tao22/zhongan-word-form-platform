from __future__ import annotations

import re


DOCVARIABLE_PATTERN = re.compile(r"\bDOCVARIABLE\b\s+[A-Za-z0-9_]+", re.IGNORECASE)
WORD_FIELD_PATTERN = re.compile(
    r"""
    \b(?:
        DOCVARIABLE\s+[A-Za-z0-9_]+
        |PAGE
        |NUMPAGES
        |SECTIONPAGES
        |PAGEREF
        |MERGEFIELD(?:\s+[A-Za-z0-9_./:-]+)?
        |DOCPROPERTY(?:\s+[A-Za-z0-9_./:-]+)?
        |FORMTEXT
        |FORMCHECKBOX
        |FORMDROPDOWN
        |REF(?:\s+[A-Za-z0-9_./:-]+)?
    )\b
    (?:\s+\\\*\s*MERGEFORMAT\b)?
    """,
    re.IGNORECASE | re.VERBOSE,
)
MERGEFORMAT_PATTERN = re.compile(r"\\\*\s*MERGEFORMAT\b", re.IGNORECASE)


def strip_legacy_field_codes(text: str) -> str:
    cleaned = text or ""
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = WORD_FIELD_PATTERN.sub("", cleaned)
    cleaned = MERGEFORMAT_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()
