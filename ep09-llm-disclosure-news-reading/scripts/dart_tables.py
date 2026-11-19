# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""DART XML · xforms HTML 표 읽기 — 원본 scripts/extract_fields.py 에서 5단계(정정 표 읽기)에 쓰는 부분만 옮겼다.

옮긴 것: raw_of · Cell · Table · TableParser · clean · norm_label · build_grid · split_correction_dart · split_correction_xforms (내용 그대로).
"""
from __future__ import annotations

import io
import re
import zipfile
from html.parser import HTMLParser

from ep09_paths import DATA

DOC_DIR = DATA / "disclosure" / "원문"


# ================================================================ 원문 읽기
def raw_of(rcp: str) -> str:
    p = DOC_DIR / rcp[:8] / f"{rcp}.zip"
    with zipfile.ZipFile(io.BytesIO(p.read_bytes())) as z:
        name = sorted(z.namelist())[0]                       # 첫 파일 = 본문(이번 종류는 모두 파일 하나)
        b = z.read(name)
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


class Cell:
    __slots__ = ("text", "val", "code", "rs", "cs", "r", "c", "th")

    def __init__(self, val=False, code="", rs=1, cs=1, th=False):
        self.text, self.val, self.code, self.rs, self.cs, self.th = "", val, code, rs, cs, th
        self.r = self.c = 0


class Table:
    def __init__(self, pre: str):
        self.rows: list[list[Cell]] = []
        self.pre = pre                                       # 표 바로 앞 글(단위 줄·표 제목)


class TableParser(HTMLParser):
    """DART XML · xforms HTML 공통 — 표(행·칸)와 표 밖 글을 모은다. 값 칸 표시: TE/TU(DART) 또는 span.xforms_input(xforms)."""

    def __init__(self, xforms: bool):
        super().__init__(convert_charrefs=True)
        self.xforms = xforms
        self.tables: list[Table] = []
        self.stack: list[Table] = []
        self.cell: Cell | None = None
        self.outside: list[str] = []
        self.hide = 0                                        # display:none 묶음 깊이(숨은 글 버림)
        self.skip = 0                                        # style·script

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("style", "script"):
            self.skip += 1
            return
        if tag == "table":
            pre = " ".join(self.outside)[-300:]
            t = Table(pre)
            self.tables.append(t)
            self.stack.append(t)
            self.outside = []
            return
        if not self.stack:
            if tag in ("br", "p", "div", "title"):
                self.outside.append("\n")
            return
        t = self.stack[-1]
        if tag == "tr":
            t.rows.append([])
        elif tag in ("td", "th", "te", "tu"):
            if not t.rows:
                t.rows.append([])
            rs = int(re.sub(r"\D", "", a.get("rowspan", "1")) or 1)
            cs = int(re.sub(r"\D", "", a.get("colspan", "1")) or 1)
            code = a.get("acode") or a.get("aunit") or ""
            self.cell = Cell(val=tag in ("te", "tu"), code=code, rs=max(1, rs), cs=max(1, cs), th=tag == "th")
            t.rows[-1].append(self.cell)
        elif tag == "span" and self.cell is not None and "xforms_input" in a.get("class", ""):
            self.cell.val = True
        elif tag == "br" and self.cell is not None:
            self.cell.text += " "
        elif tag == "p" and self.cell is not None and self.cell.text:
            self.cell.text += " "

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip = max(0, self.skip - 1)
        elif tag == "table" and self.stack:
            self.stack.pop()
            self.cell = None
        elif tag in ("td", "th", "te", "tu"):
            self.cell = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.cell is not None:
            self.cell.text += data
        elif not self.stack:
            s = data.strip()
            if s:
                self.outside.append(s)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ").replace("　", " ")).strip()


NUM_HEAD = re.compile(r"^\s*(?:[-ㆍ·※▶■□○●*]+\s*)*(?:\(?\d+(?:-\d+)*[.)]\s*|[가-하][.)]\s+|\(\d+\)\s*|[①-⑳]\s*)*(?:[-ㆍ·]\s*)*")


def norm_label(s: str) -> str:
    """칸 이름 맞추기용: 앞 번호('1.', '7-1.', '가.', '-')를 떼고 공백을 모두 지운다."""
    return re.sub(r"[\s\[\]【】<>「」]+", "", NUM_HEAD.sub("", clean(s)))



def build_grid(t: Table):
    G = {}
    for r, row in enumerate(t.rows):
        c = 0
        for cell in row:
            while (r, c) in G:
                c += 1
            cell.r, cell.c = r, c
            for dr in range(cell.rs):
                for dc in range(cell.cs):
                    G[(r + dr, c + dc)] = cell
            c += cell.cs
    return G


def split_correction_dart(x: str):
    m = re.search(r"(?is)<CORRECTION\b.*?</CORRECTION>", x)
    if not m:
        return "", x
    return m.group(0), x[:m.start()] + x[m.end():]


def split_correction_xforms(x: str):
    i = x.find('id="LIB_LC000"')
    if i < 0 or "정정" not in x[i:i + 3000]:
        return "", x
    j = x.find('class="xforms_title"', i)
    if j < 0:
        return "", x
    return x[i:j], x[:i] + x[j:]
