# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""공시 원문 zip 읽기 — OpenDART 공시서류원본파일(document.xml) 을 받아 둔 zip 을 글로 바꾼다. 받는 코드는 넣지 않았다(README).

원본 disclosure/document.py 에서 읽는 부분(path_of · xml_to_text · read_text)만 옮겼다. 받기(fetch)·호출 수 세기·키 읽기는 뺐다.
API(받는 쪽에서 쓸 것): GET https://opendart.fss.or.kr/api/document.xml?crtfc_key=<키>&rcept_no=<14자리> → zip(정상) 또는 status/message(오류)
  오류 코드(개발가이드): 013 데이터 없음 · 014 파일 없음 · 020 한도 초과 · 800 시스템 점검 · 900 정의되지 않은 오류
  공시 뒤 약 15분이 지나야 원문이 반영된다(FAQ). 개인 키는 하루 20,000건 한도.
저장 자리: data/disclosure/원문/<YYYYMMDD>/<접수번호>.zip  (접수번호 앞 8자리 = 날짜 폴더)
"""
from __future__ import annotations

import html
import io
import re
import zipfile

from ep09_paths import DATA

DOC_DIR = DATA / "disclosure" / "원문"


def path_of(rcp: str):
    return DOC_DIR / rcp[:8] / f"{rcp}.zip"


# ---------- 읽기 ----------
def xml_to_text(x: str) -> str:
    """DART 원문 XML → 글. 표는 칸을 ' | ' 로, 줄은 줄바꿈으로."""
    x = re.sub(r"(?is)<(script|style).*?</\1>", "", x)
    x = re.sub(r"(?i)</(TD|TH|TE|TU)>", " | ", x)
    x = re.sub(r"(?i)</TR>|<BR\s*/?>|</P>|</TITLE>|</SECTION-\d>", "\n", x)
    x = re.sub(r"<[^>]+>", "", x)
    x = html.unescape(x).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip(" |") for ln in x.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def read_text(rcp: str) -> str:
    """받아 둔 zip 안의 문서들을 글로 이어 붙인다(첫 파일이 본문)."""
    with zipfile.ZipFile(io.BytesIO(path_of(rcp).read_bytes())) as z:
        parts = []
        for name in sorted(z.namelist()):
            raw = z.read(name)
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    s = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                s = raw.decode("utf-8", "replace")
            parts.append(f"=== {name} ===\n" + xml_to_text(s))
    return "\n".join(parts)
