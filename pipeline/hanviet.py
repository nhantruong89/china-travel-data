"""Âm Hán-Việt cho tên địa điểm, từ trường kVietnamese của Unihan (unicode.org)."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_CJK = re.compile(r"[㐀-鿿豈-﫿]")


EXTRA_FILE = Path(__file__).with_name("hanviet_extra.tsv")


def load_extra(path: Path) -> dict[str, str]:
    """Bảng bổ sung dạng "chữ<TAB>âm" (dòng bắt đầu bằng # là chú thích)."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        ch, reading = line.split("\t")
        out[ch] = reading.strip()
    return out


# Âm Hán-Việt bổ sung cho chữ thường gặp trong tên ga/địa danh mà Unihan không có (kể cả qua chữ phồn thể).
EXTRA_READINGS: dict[str, str] = {
    "北": "bắc", "蔡": "thái", "浜": "banh", "张": "trương", "华": "hoa", "龙": "long", "马": "mã", "陆": "lục",
    "赵": "triệu", "巷": "hạng", "颛": "chuyên", "桥": "kiều", "菉": "lục", "葭": "gia", "夏": "hạ",
    **load_extra(EXTRA_FILE),
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


# "y" cuối âm tiết đứng ngay sau phụ âm viết được cả "i" (Lý/Lí, Mỹ/Mĩ, Kỳ/Kì): gộp về "i".
# "uy", "quy", "ay"… không đổi vì "y" đứng sau nguyên âm.
_FINAL_Y = re.compile(r"(?<=[bcdghklmnprstvx])y\b")


def fold(s: str) -> str:
    """Chữ thường, bỏ dấu, đ → d, "Lý" → "li" (khớp cách app chuẩn hoá truy vấn)."""
    s = s.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", s)
    plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()
    return _FINAL_Y.sub("i", plain)


# --- Bảng phiên âm Hán-Việt ---
# kVietnamese của Unihan phần lớn là âm Nôm (园 "vườn", 里 "lịa", 东 thiếu…), không dùng làm âm Hán-Việt chính được.
# Bảng phiên âm (mỗi chữ giản thể một âm Hán-Việt) của cộng đồng dịch Trung–Việt, lấy từ
# github.com/ryanphung/chinese-hanviet-cognates (inputs/phienam.txt, commit cố định trong CI).
PHIENAM_URL = ("https://raw.githubusercontent.com/ryanphung/chinese-hanviet-cognates/"
               "5f79922e2223105547e9ad7d2819949dd508407b/inputs/phienam.txt")

_ONSETS = ("ngh", "ng", "nh", "ch", "gh", "gi", "kh", "ph", "qu", "th", "tr", "b", "c", "d", "đ", "g", "h", "k",
           "l", "m", "n", "p", "r", "s", "t", "v", "x", "")
_FINALS = ("ch", "ng", "nh", "c", "i", "m", "n", "o", "p", "t", "u", "y", "")
_VOWELS = set("aăâeêioôơuưy")


def is_syllable(word: str) -> bool:
    """Một âm tiết tiếng Việt viết đúng (để bỏ dòng rác như "connect", "mian3")."""
    w = unicodedata.normalize("NFD", word.lower())
    base = unicodedata.normalize("NFC", "".join(c for c in w if c not in "\u0300\u0301\u0303\u0309\u0323"))
    if not base or not all(c.isalpha() for c in base):
        return False
    for onset in _ONSETS:
        if not base.startswith(onset):
            continue
        rest = base[len(onset):]
        for final in _FINALS:
            if rest.endswith(final):
                nucleus = rest[: len(rest) - len(final)] if final else rest
                if 1 <= len(nucleus) <= 3 and all(c in _VOWELS for c in nucleus):
                    return True
    return False


def load_phienam(path: Path) -> dict[str, str]:
    """"chữ=âm" mỗi dòng; chỉ giữ một chữ, một âm tiết hợp lệ; dòng đầu tiên của mỗi chữ thắng."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" not in line:
            continue
        ch, reading = (x.strip() for x in line.split("=", 1))
        if len(ch) != 1 or not _CJK.match(ch) or ch in out or not is_syllable(reading):
            continue
        out[ch] = reading.lower()
    return out


# Âm sửa tay, thắng mọi bảng: chữ giản thể mà bảng phiên âm đọc theo chữ cổ cùng hình (广 "nghiễm" ≠ 廣 "quảng"),
# hoặc âm không thông dụng trong tên địa điểm.
OVERRIDES: dict[str, str] = {
    "广": "quảng", "宁": "ninh", "钱": "tiền", "台": "đài", "缘": "duyên", "儿": "nhi", "济": "tế", "厂": "xưởng",
    "价": "giá", "机": "cơ", "爷": "gia", "腊": "lạp", "蜡": "lạp", "橱": "trù", "干": "can", "厅": "sảnh",
    "廳": "sảnh", "办": "biện", "菲": "phi", "埔": "phố", "洱": "nhĩ", "禅": "thiền", "聂": "nhiếp", "玫": "mai",
    "瑰": "khôi", "贾": "giả", "鲍": "bào", "碱": "kiềm", "麪": "diện", "综": "tổng", "蒋": "tưởng", "蔣": "tưởng",
    "允": "doãn", "佑": "hựu", "梵": "phạn", "咖": "ca", "啡": "phi", "哑": "á", "礁": "tiêu", "锡": "tích",
}


def build_table(unihan: Path | None, phienam: Path | None) -> dict[str, str]:
    """Âm Hán-Việt cho từng chữ: sửa tay > bảng phiên âm > Unihan (kể cả mượn phồn thể) > bảng bổ sung."""
    table: dict[str, str] = {}
    if unihan is not None and unihan.exists():
        table = load_unihan(unihan, variants=unihan.with_name("Unihan_Variants.txt"), extra=EXTRA_READINGS)
    else:
        table = dict(EXTRA_READINGS)
    if phienam is not None and phienam.exists():
        table.update(load_phienam(phienam))
    table.update(OVERRIDES)
    return table
