"""Âm Hán-Việt cho tên địa điểm, từ trường kVietnamese của Unihan (unicode.org)."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_CJK = re.compile(r"[㐀-鿿豈-﫿]")


# Âm Hán-Việt bổ sung cho chữ thường gặp trong tên ga/địa danh mà Unihan không có (kể cả qua chữ phồn thể).
EXTRA_READINGS: dict[str, str] = {
    "北": "bắc", "蔡": "thái", "浜": "banh", "张": "trương", "华": "hoa", "龙": "long", "马": "mã", "陆": "lục",
    "赵": "triệu", "巷": "hạng", "颛": "chuyên", "桥": "kiều", "菉": "lục", "葭": "gia", "夏": "hạ",
}


def load_unihan(path: Path, variants: Path | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Bảng chữ → âm Hán-Việt từ kVietnamese.

    variants: Unihan_Variants.txt — chữ giản thể chưa có âm thì mượn âm của chữ phồn thể (kTraditionalVariant).
    extra: âm bổ sung, chỉ điền chữ còn thiếu.
    """
    table: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or "\tkVietnamese\t" not in line:
                continue
            code, _, value = line.rstrip("\n").split("\t", 2)
            reading = value.split()[0] if value.split() else ""
            if reading:
                table[chr(int(code[2:], 16))] = reading
    if variants is not None and variants.exists():
        borrowed: dict[str, str] = {}
        with open(variants, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or "\tkTraditionalVariant\t" not in line:
                    continue
                code, _, value = line.rstrip("\n").split("\t", 2)
                simp = chr(int(code[2:], 16))
                if simp in table or simp in borrowed:
                    continue
                for trad_code in value.split():
                    trad = chr(int(trad_code.split("<")[0][2:], 16))
                    if trad in table:
                        borrowed[simp] = table[trad]
                        break
        table.update(borrowed)
    for ch, reading in (extra or {}).items():
        table.setdefault(ch, reading)
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
