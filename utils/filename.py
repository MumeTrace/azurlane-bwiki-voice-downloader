"""Deterministic Windows/Linux-safe path component handling."""

from __future__ import annotations

import hashlib
import unicodedata


DEFAULT_MAX_COMPONENT_LENGTH = 100
WINDOWS_REPLACEMENTS = str.maketrans(
    {
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "／",
        "\\": "＼",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
)
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def short_hash(value: str, length: int = 8) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _replace_controls(value: str) -> str:
    return "".join("＿" if unicodedata.category(char).startswith("C") else char for char in value)


def _is_windows_reserved(value: str) -> bool:
    first_segment = value.split(".", 1)[0]
    return first_segment.upper() in WINDOWS_RESERVED_NAMES


def safe_component(
    value: str,
    *,
    max_length: int = DEFAULT_MAX_COMPONENT_LENGTH,
    fallback: str = "未命名",
) -> str:
    if max_length < 12:
        raise ValueError("max_length 至少应为 12")
    original = value
    cleaned = unicodedata.normalize("NFC", value).translate(WINDOWS_REPLACEMENTS)
    cleaned = _replace_controls(cleaned).rstrip(" .")
    if cleaned in {"", ".", ".."}:
        cleaned = f"{fallback}_{short_hash(original)}"
    if _is_windows_reserved(cleaned):
        cleaned = f"_{cleaned}"
    if len(cleaned) > max_length:
        digest = short_hash(original)
        prefix_length = max_length - len(digest) - 1
        cleaned = f"{cleaned[:prefix_length].rstrip(' .')}_{digest}"
    return cleaned.rstrip(" .") or f"{fallback}_{short_hash(original)}"


def unique_stem(
    text: str,
    used_casefolded: set[str],
    *,
    max_length: int = DEFAULT_MAX_COMPONENT_LENGTH,
) -> str:
    base = safe_component(text, max_length=max_length, fallback="无台词")
    candidate = base
    suffix_number = 1
    while candidate.casefold() in used_casefolded:
        suffix_number += 1
        suffix = f"_{suffix_number}"
        trimmed = base[: max_length - len(suffix)].rstrip(" .")
        candidate = f"{trimmed}{suffix}"
    used_casefolded.add(candidate.casefold())
    return candidate

