"""Âm Hán-Việt cho tên địa điểm, từ trường kVietnamese của Unihan (unicode.org)."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_CJK = re.compile(r"[㐀-鿿豈-﫿]")


def load_unihan(path: Path) -> dict[str, str]:
    table: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or "\tkVietnamese\t" not in line:
                continue
            code, _, value = line.rstrip("\n").split("\t", 2)
            reading = value.split()[0] if value.split() else ""
            if reading:
                table[chr(int(code[2:], 16))] = reading
    return table


def to_hanviet(text: str, table: dict[str, str]) -> str | None:
    """外滩 → "Ngoại Than". Chữ Hán không có trong bảng và ký tự khác giữ nguyên. None nếu không chữ nào có âm."""
    tokens: list[str] = []
    buf = ""
    found = False
    for ch in text:
        if _CJK.match(ch):
            if buf.strip():
                tokens.append(buf.strip())
            buf = ""
            reading = table.get(ch)
            if reading:
                found = True
                tokens.append(reading[:1].upper() + reading[1:])
            else:
                tokens.append(ch)
        else:
            buf += ch
    if buf.strip():
        tokens.append(buf.strip())
    return " ".join(tokens) if found else None


def fold(s: str) -> str:
    """Chữ thường, bỏ dấu, đ → d (khớp cách app chuẩn hoá truy vấn)."""
    s = s.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", s)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()
