# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 채점기 (2026-11-16). 결정적 코드만 — 모델·외부 API 를 부르지 않는다.

정답: data/ep09/sample_A_정답.csv · sample_B.csv (scripts/ep09_sample.py 가 만든 것)

── 실험 A (공시 원문에서 값 뽑기) ──────────────────────────────────────────────
답 파일(JSONL, 한 줄 = 문서 하나):
  {"rcept_no": "2026...", "answer": {"<칸>": 값, ...}}      # 칸 이름은 구조화 열 이름(aqpln_stk_ostk) 또는 질문 이름 둘 다 받음
  ("answer" 없이 {"rcept_no"|"접수번호": ..., "<칸>": 값, ...} 처럼 펼쳐 써도 됨)
정규화(답 쪽):
  숫자  쉼표·공백·단위 글자(원·주·%·%p·회·명…) 떼기 · 한글 단위 환산(조·억·천만·백만·십만·만·천, "1조 2,000억" 식 합산)
        · 음수 표기(-, −, △, ▲, 괄호) · 숫자형(JSON number)은 그대로.
  날짜  2026년 4월 8일 / 2026-04-08 / 2026.4.8 / 20260408 → 20260408.  두 자리 연도(26.04.08)는 관용 점수에서만 인정.
  분류  공백을 뺀 글자 비교.
  답 없음 = 키 없음 · null · "" · "-" · "없음" · "해당없음" · "모름" · "미정" 등(NO_ANSWER).
칸마다 따로 내는 것(정답 칸에 값이 있는 칸):
  결과 범주        정답 / 오답 / 답 없음   (엄격 기준과 관용 기준 두 벌)
  값 일치(엄격)    정규화한 값이 정확히 같음
  값 일치(관용)    엄격 일치, 또는 숫자: 상대 오차 ≤ 0.5%(단위가 %·%p 면 절대 차 ≤ 0.05) — 반올림 허용
                   날짜: 두 자리 연도 인정 · 분류: 한쪽이 다른 쪽을 포함('제3자배정' ⊂ '제3자배정증자')
  단위(자릿수) 일치  |답/정답| 이 10^±0.5 안(같은 자릿수). 정답 0 이면 답도 0 일 때만.
  부호 일치        부호가 같음(0 은 0 끼리)
  오답 갈래        부호만 틀림 · 자릿수만 틀림(답 = 정답×10^k, k≠0 → 단위 환산 오류, k 를 적음) · 반올림 차이(관용에선 정답)
                   · 값 다름 · 답 해석 못 함(숫자·날짜로 못 읽음)
정답 칸이 빈 칸(지어내기 측정): 답 없음 = '비움'(맞음) · 0 을 채움 · 값을 채움(지어내기).  비율은 '값을 채움'과 '0 포함' 둘 다.
문서 단위: 값 있는 칸이 전부 정답(엄격/관용) · 거기에 빈 칸도 전부 비움.
구간: 비율마다 윌슨 95% 구간. 오류가 0 인 칸은 미리 정한 대로 "오류율 95% 상한 3/n" 도 적는다.

── 실험 B (뉴스 제목으로 방향 판단) ──────────────────────────────────────────
답 파일: JSONL {"id": "<srno_code>", "answer": "오름|내림|모름"} 또는 CSV(id,answer).
  오름 = 오름·상승·up / 내림 = 내림·하락·down / 모름 = 모름·중립·판단불가·null / 그 밖 = 형식 밖(따로 셈, 모름처럼 취급).
정답: post5·post30 의 부호. 수익률 0(변화 없음)은 방향이 없어 기본 적중률의 분모에서 뺀다(뺀 수를 적고, 0 을 오답으로 친 값도 나란히).
내는 것(구간 앞/뒤 × 갈래, 틀 제목(sample_B 의 제목_반복수 ≥ 10)을 뺀 줄, 일반 기사 뒤 + 시세 중계 뒤 합침):
  답한 것 중 적중률(모름 제외) · 전체 대비 적중률(모름 = 못 맞힘) · 모름 비율 · 답 분포
  기준선: 전부 '오름' · 전부 '내림' · 무작위(해석값 50% + 고정 시드 1,000회 모의의 2.5~97.5%)
  표본 수와 윌슨 95% 구간 · 일반 기사 앞 대 뒤 차이(%p, 정규 근사 95% 구간)

쓰기(이 폴더에서):
  python -X utf8 scripts/ep09_grade.py selftest                     # 가짜 답으로 채점기 자체 시험
  python -X utf8 scripts/ep09_grade.py a --answers <답.jsonl> --name <실행이름>
  python -X utf8 scripts/ep09_grade.py b --answers <답.jsonl|csv> --name <실행이름>
  → data/ep09/채점/<실행이름>_A_칸.csv · _A_칸별.csv · _A_종류별.csv · _A_문서.csv · _A_요약.md / _B_건.csv · _B_요약.md
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
EP09 = DATA / "ep09"
OUT = EP09 / "채점"
TEST = EP09 / "자체시험"
SEED = 20261116
REL_TOL = Decimal("0.005")          # 관용: 상대 오차 0.5%
PCT_TOL = Decimal("0.05")           # 관용: 단위가 %·%p 인 칸의 절대 차
TEMPLATE_MIN = 10                   # B: 같은 글자 제목이 이만큼 이상이면 '틀 제목'(목록·안내 기사)
NO_ANSWER = {"", "-", "－", "−", "–", "없음", "해당없음", "해당사항없음", "모름", "미정", "미기재", "기재없음", "null", "none", "nan", "n/a", "na", "해당사항 없음", "알수없음"}
UNIT_TAIL = re.compile(r"(퍼센트포인트|%포인트|퍼센트|%p|％|%|원/주|원|주식|주|회차|회|명|개|배|건|일)$")
KUNIT = {"조": 10 ** 12, "억": 10 ** 8, "천만": 10 ** 7, "백만": 10 ** 6, "십만": 10 ** 5, "만": 10 ** 4, "천": 10 ** 3}
TOKEN = re.compile(r"(\d+(?:\.\d+)?)(조|억|천만|백만|십만|만|천)?")


# ================================================================ 정규화
def is_blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return re.sub(r"\s+", "", str(v)).lower().rstrip(".") in NO_ANSWER


def parse_num(v) -> Decimal | None:
    """답 → Decimal. 못 읽으면 None(답 없음과는 다르다 — 호출 쪽에서 is_blank 를 먼저 본다)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else Decimal(repr(v))
    s = re.sub(r"\s+", "", str(v)).replace(",", "").replace("＋", "+")
    s = re.sub(r"^(약|총|금|제)", "", s)
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    while s and s[0] in "-−–－△▲+":
        if s[0] != "+":
            neg = not neg if s[0] in "-−–－" else True
        s = s[1:]
    for _ in range(2):                                         # "12.5%p", "3,000백만원", "100주식" 꼬리 단위
        s2 = UNIT_TAIL.sub("", s)
        if s2 == s:
            break
        s = s2
    if not s:
        return None
    try:
        if re.fullmatch(r"\d+(\.\d+)?|\.\d+", s) or re.fullmatch(r"\d+(\.\d+)?[eE][+-]?\d+", s):
            x = Decimal(s)
        else:
            pos, x, seen = 0, Decimal(0), False
            for m in TOKEN.finditer(s):
                if m.start() != pos:
                    return None
                x += Decimal(m.group(1)) * KUNIT.get(m.group(2), 1)
                pos, seen = m.end(), True
            if not seen or pos != len(s):
                return None
    except InvalidOperation:
        return None
    return -x if neg and x != 0 else x


def parse_date(v) -> tuple[str | None, bool]:
    """답 → (YYYYMMDD, 두 자리 연도였나). 못 읽으면 (None, False)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        v = str(int(v))
    s = str(v).strip()
    m = re.fullmatch(r"\s*(\d{4})(\d{2})(\d{2})\s*", s) or re.search(r"(?<!\d)(\d{4})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})(?!\d)", s)
    short = False
    if not m:
        m = re.search(r"(?<!\d)(\d{2})[-./](\d{1,2})[-./](\d{1,2})(?!\d)", s)
        short = bool(m)
    if not m:
        return None, False
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if short:
        y += 2000
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None, False
    return f"{y:04d}{mo:02d}{d:02d}", short


def squash(s) -> str:
    return re.sub(r"[\s()（）·ㆍ]+", "", str(s))


def scale_k(a: Decimal, t: Decimal) -> int | None:
    """답 = 정답 × 10^k (k ≠ 0, |k| ≤ 15) 이면 k."""
    if a == 0 or t == 0:
        return None
    for k in range(-15, 16):
        if k and a == t.scaleb(k):
            return k
    return None


def grade_cell(tp: str, unit: str, truth: str, ans, present: bool) -> dict:
    """정답 칸에 값이 있는 칸 하나를 채점."""
    r = {"엄격": "오답", "관용": "오답", "자릿수일치": "", "부호일치": "", "오답갈래": "", "답_정규": "", "배수_k": ""}
    if not present or is_blank(ans):
        r.update(엄격="답없음", 관용="답없음")
        return r
    if tp == "num":
        t, a = Decimal(truth), parse_num(ans)
        if a is None:
            r["오답갈래"] = "답 해석 못 함"
            return r
        r["답_정규"] = format(a.normalize(), "f")
        sign = lambda x: (x > 0) - (x < 0)
        r["부호일치"] = int(sign(a) == sign(t))
        r["자릿수일치"] = int(a == 0) if t == 0 else int(a != 0 and round(math.log10(abs(a) / abs(t))) == 0)
        if a == t:
            r.update(엄격="정답", 관용="정답")
            return r
        diff = abs(a - t)
        lenient = (unit in ("%", "%p") and diff <= PCT_TOL) or (t != 0 and diff <= REL_TOL * abs(t))
        k = scale_k(a, t)
        if lenient:
            r.update(관용="정답", 오답갈래="반올림 차이")
        elif a == -t:
            r["오답갈래"] = "부호만 틀림"
        elif k is not None:
            r.update(오답갈래="자릿수만 틀림", 배수_k=k)
        elif scale_k(-a, t) is not None:
            r.update(오답갈래="자릿수·부호 틀림", 배수_k=scale_k(-a, t))
        else:
            r["오답갈래"] = "값 다름"
        return r
    if tp == "date":
        a, short = parse_date(ans)
        if a is None:
            r["오답갈래"] = "답 해석 못 함"
            return r
        r["답_정규"] = a
        if a == truth:
            r["관용"] = "정답"
            if short:
                r["오답갈래"] = "두 자리 연도"
            else:
                r["엄격"] = "정답"
        else:
            same = [a[:4] == truth[:4], a[4:6] == truth[4:6], a[6:] == truth[6:]]
            r["오답갈래"] = "날짜 다름(" + "".join(n for n, ok in zip("연월일", same) if not ok) + ")"
        return r
    a, t = squash(ans), squash(truth)                          # enum
    r["답_정규"] = a
    if a == t:
        r.update(엄격="정답", 관용="정답")
    elif a and (a in t or t in a):
        r.update(관용="정답", 오답갈래="표기 차이(포함)")
    else:
        r["오답갈래"] = "분류 다름"
    return r


def grade_empty(tp: str, ans, present: bool) -> str:
    """정답 칸이 빈 칸: 비움 / 0 채움 / 값 채움."""
    if not present or is_blank(ans):
        return "비움"
    if tp == "num":
        a = parse_num(ans)
        if a is not None and a == 0:
            return "0 채움"
    return "값 채움"


# ================================================================ 통계
def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    z, p = 1.959964, k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def pct(k: int, n: int, ci: bool = True) -> str:
    if n == 0:
        return "– (0건)"
    s = f"{100 * k / n:.1f}% ({k}/{n})"
    if ci:
        lo, hi = wilson(k, n)
        s += f" [{100 * lo:.1f}~{100 * hi:.1f}]"
    return s


def rule3(err: int, n: int) -> str:
    return f"오류 0 → 오류율 95% 상한 {100 * min(1.0, 3 / n):.1f}% (3/{n})" if n and err == 0 else ""


# ================================================================ A
def load_answers_a(path: Path) -> dict[str, dict]:
    out = {}
    for ln in path.read_text(encoding="utf-8-sig").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        o = json.loads(ln)
        rcp = str(o.get("rcept_no") or o.get("접수번호") or "").strip()
        a = o.get("answer")
        if not isinstance(a, dict):
            a = {k: v for k, v in o.items() if k not in ("rcept_no", "접수번호", "kind", "answer")}
        out[rcp] = a                                           # 같은 접수번호가 두 번 나오면 뒤 것
    return out


def grade_a(answers: dict[str, dict], key_path: Path | None = None):
    key = pd.read_csv(key_path or EP09 / "sample_A_정답.csv", dtype=str, encoding="utf-8-sig").fillna("")
    rows = []
    for k in key.itertuples(index=False):
        a = answers.get(k.rcept_no)
        doc_ok = a is not None
        present, val = False, None
        if doc_ok:
            for nm in (k.칸, k.질문이름):
                if nm in a:
                    present, val = True, a[nm]
                    break
        base = {"kind": k.kind, "rcept_no": k.rcept_no, "칸": k.칸, "형": k.형, "단위": k.단위, "정답": k.정답, "정답상태": k.상태,
                "문서답있음": int(doc_ok), "답_원문": "" if val is None else (json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val)}
        if k.상태 == "값":
            base.update(grade_cell(k.형, k.단위, k.정답, val, present))
        elif k.상태 == "빈칸":
            base["빈칸결과"] = grade_empty(k.형, val, present)
        rows.append(base)
    cells = pd.DataFrame(rows).fillna("")
    for c in ("엄격", "관용", "오답갈래", "빈칸결과", "자릿수일치", "부호일치", "답_정규", "배수_k"):
        if c not in cells:
            cells[c] = ""
    return cells


def agg_a(g: pd.DataFrame) -> dict:
    v = g[g["정답상태"] == "값"]
    e = g[g["정답상태"] == "빈칸"]
    ans = v[v["엄격"] != "답없음"]
    num = ans[(ans["형"] == "num") & (ans["자릿수일치"] != "")]
    return {
        "칸_값": len(v), "정답_엄격": int((v["엄격"] == "정답").sum()), "정답_관용": int((v["관용"] == "정답").sum()),
        "오답_엄격": int((v["엄격"] == "오답").sum()), "오답_관용": int((v["관용"] == "오답").sum()), "답없음": int((v["엄격"] == "답없음").sum()),
        "숫자_답함": len(num), "자릿수_일치": int((num["자릿수일치"] == 1).sum()), "부호_일치": int((num["부호일치"] == 1).sum()),
        "오답_부호만": int((v["오답갈래"] == "부호만 틀림").sum()), "오답_자릿수만": int(v["오답갈래"].isin(["자릿수만 틀림", "자릿수·부호 틀림"]).sum()),
        "오답_반올림차이": int((v["오답갈래"] == "반올림 차이").sum()), "오답_해석못함": int((v["오답갈래"] == "답 해석 못 함").sum()),
        "칸_빈칸": len(e), "빈칸_비움": int((e["빈칸결과"] == "비움").sum()), "빈칸_0채움": int((e["빈칸결과"] == "0 채움").sum()),
        "빈칸_값채움": int((e["빈칸결과"] == "값 채움").sum()), "칸_해석불가(제외)": int((g["정답상태"] == "해석불가").sum()),
    }


def doc_table(cells: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (kind, rcp), g in cells.groupby(["kind", "rcept_no"], sort=False):
        v, e = g[g["정답상태"] == "값"], g[g["정답상태"] == "빈칸"]
        keep = bool((e["빈칸결과"] == "비움").all())
        out.append({"kind": kind, "rcept_no": rcp, "문서답있음": int(g["문서답있음"].iloc[0]), "칸_값": len(v), "칸_빈칸": len(e),
                    "전부맞음_엄격": int(len(v) > 0 and (v["엄격"] == "정답").all()), "전부맞음_관용": int(len(v) > 0 and (v["관용"] == "정답").all()),
                    "빈칸_전부비움": int(keep),
                    "전부맞음_엄격+빈칸지킴": int(len(v) > 0 and (v["엄격"] == "정답").all() and keep),
                    "전부맞음_관용+빈칸지킴": int(len(v) > 0 and (v["관용"] == "정답").all() and keep)})
    return pd.DataFrame(out)


def report_a(cells: pd.DataFrame, name: str, out_dir: Path, doc_meta: pd.DataFrame | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cells.to_csv(out_dir / f"{name}_A_칸.csv", index=False, encoding="utf-8-sig")
    by_f = pd.DataFrame([{"kind": k, "칸": c, **agg_a(g)} for (k, c), g in cells.groupby(["kind", "칸"], sort=False)])
    by_k = pd.DataFrame([{"kind": k, **agg_a(g)} for k, g in cells.groupby("kind", sort=False)])
    docs = doc_table(cells)
    by_f.to_csv(out_dir / f"{name}_A_칸별.csv", index=False, encoding="utf-8-sig")
    by_k.to_csv(out_dir / f"{name}_A_종류별.csv", index=False, encoding="utf-8-sig")
    docs.to_csv(out_dir / f"{name}_A_문서.csv", index=False, encoding="utf-8-sig")
    t = agg_a(cells)
    n_doc = len(docs)
    L = [f"# 실험 A 채점 요약 — {name}", "",
         f"- 문서 {n_doc}건(답이 온 문서 {int(docs['문서답있음'].sum())}건) · 값 있는 칸 {t['칸_값']} · 빈 칸 {t['칸_빈칸']} · 해석불가로 뺀 칸 {t['칸_해석불가(제외)']}",
         "- 대괄호 = 윌슨 95% 구간. 관용 = 상대 오차 0.5% 이내(%·%p 칸은 절대 차 0.05 이내)·두 자리 연도·분류 포함 관계 허용.", "",
         "## 칸 단위(값 있는 칸)", "",
         "| 기준 | 정답 | 오답 | 답 없음 |", "|---|---|---|---|",
         f"| 엄격 | {pct(t['정답_엄격'], t['칸_값'])} | {pct(t['오답_엄격'], t['칸_값'], False)} | {pct(t['답없음'], t['칸_값'], False)} |",
         f"| 관용 | {pct(t['정답_관용'], t['칸_값'])} | {pct(t['오답_관용'], t['칸_값'], False)} | {pct(t['답없음'], t['칸_값'], False)} |", "",
         f"- 숫자 칸 가운데 답한 칸 {t['숫자_답함']}개: 단위(자릿수) 일치 {pct(t['자릿수_일치'], t['숫자_답함'])} · 부호 일치 {pct(t['부호_일치'], t['숫자_답함'])}",
         f"- 오답 갈래(엄격 기준 오답 {t['오답_엄격']}개 중): 부호만 틀림 {t['오답_부호만']} · 자릿수만 틀림 {t['오답_자릿수만']} · 반올림 차이 {t['오답_반올림차이']} · 답 해석 못 함 {t['오답_해석못함']} · "
         f"그 밖 {t['오답_엄격'] - t['오답_부호만'] - t['오답_자릿수만'] - t['오답_반올림차이'] - t['오답_해석못함']}", "",
         "## 지어내기(정답 칸이 빈 칸)", "",
         f"- 빈 칸 {t['칸_빈칸']}개: 값을 채움 {pct(t['빈칸_값채움'], t['칸_빈칸'])} · 0 을 채움 {pct(t['빈칸_0채움'], t['칸_빈칸'], False)} · 비움 {pct(t['빈칸_비움'], t['칸_빈칸'], False)}",
         f"- 0 까지 채움으로 치면 {pct(t['빈칸_값채움'] + t['빈칸_0채움'], t['칸_빈칸'])}", "",
         "## 문서 단위", "",
         f"- 값 있는 칸 전부 정답: 엄격 {pct(int(docs['전부맞음_엄격'].sum()), n_doc)} · 관용 {pct(int(docs['전부맞음_관용'].sum()), n_doc)}",
         f"- 거기에 빈 칸도 전부 비움: 엄격 {pct(int(docs['전부맞음_엄격+빈칸지킴'].sum()), n_doc)} · 관용 {pct(int(docs['전부맞음_관용+빈칸지킴'].sum()), n_doc)}", ""]
    if doc_meta is not None and "정정" in doc_meta:
        m = docs.merge(doc_meta[["rcept_no", "정정"]].astype({"정정": int}), on="rcept_no", how="left")
        for flag, lab in ((0, "정정 아님"), (1, "정정 공시")):
            g = m[m["정정"] == flag]
            L.append(f"- {lab} {len(g)}건: 전부 정답(엄격) {pct(int(g['전부맞음_엄격'].sum()), len(g))}")
        L.append("")
    L += ["## 종류별", "", "| 종류 | 문서 | 값 칸 | 정답(엄격) | 정답(관용) | 답 없음 | 빈 칸 | 값 채움 | 문서 전부 정답(엄격) |", "|---|---:|---:|---|---|---:|---:|---|---|"]
    for r in by_k.itertuples(index=False):
        d = docs[docs["kind"] == r.kind]
        L.append(f"| {r.kind} | {len(d)} | {r.칸_값} | {pct(r.정답_엄격, r.칸_값)} | {pct(r.정답_관용, r.칸_값)} | {r.답없음} | {r.칸_빈칸} | {pct(r.빈칸_값채움, r.칸_빈칸)} | {pct(int(d['전부맞음_엄격'].sum()), len(d))} |")
    L += ["", "## 칸별(오류가 0 인 칸은 3/n 상한)", "", "| 종류 | 칸 | 값 칸 | 정답(엄격) | 정답(관용) | 오답 | 답 없음 | 비고 |", "|---|---|---:|---|---|---:|---:|---|"]
    for r in by_f.itertuples(index=False):
        L.append(f"| {r.kind} | {r.칸} | {r.칸_값} | {pct(r.정답_엄격, r.칸_값)} | {pct(r.정답_관용, r.칸_값, False)} | {r.오답_엄격} | {r.답없음} | {rule3(r.오답_엄격 + r.답없음, r.칸_값)} |")
    (out_dir / f"{name}_A_요약.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"total": t, "docs": docs, "by_field": by_f, "by_kind": by_k}


# ================================================================ B
UP, DOWN, DK = {"오름", "상승", "up", "오른다", "+", "1"}, {"내림", "하락", "down", "내린다", "-1"}, {"모름", "중립", "판단불가", "판단 불가", "unknown", "0", "null", "none", "", "nan"}


def norm_b(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "모름"
    s = str(v).strip().lower()
    return "오름" if s in UP else "내림" if s in DOWN else "모름" if s in DK else "형식 밖"


def load_answers_b(path: Path) -> dict[str, str]:
    if path.suffix.lower() == ".csv":
        d = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
        return dict(zip(d["id"], d["answer"]))
    out = {}
    for ln in path.read_text(encoding="utf-8-sig").splitlines():
        if ln.strip():
            o = json.loads(ln)
            out[str(o["id"])] = o.get("answer")
    return out


def grade_b(answers: dict, key_path: Path | None = None) -> pd.DataFrame:
    k = pd.read_csv(key_path or EP09 / "sample_B.csv", dtype=str, encoding="utf-8-sig").fillna("")
    k["답있음"] = k["id"].map(lambda i: int(i in answers))
    k["답"] = k["id"].map(lambda i: norm_b(answers.get(i)) if i in answers else "답 없음")
    for h in ("post5", "post30"):
        x = pd.to_numeric(k[h])
        k[f"방향_{h}"] = x.map(lambda v: "오름" if v > 0 else "내림" if v < 0 else "변화없음")
        k[f"적중_{h}"] = [("" if a not in ("오름", "내림") else "제외(변화없음)" if t == "변화없음" else int(a == t)) for a, t in zip(k["답"], k[f"방향_{h}"])]
    return k


def stat_b(g: pd.DataFrame, h: str, rng: random.Random) -> dict:
    n = len(g)
    truth, ans = list(g[f"방향_{h}"]), list(g["답"])
    nz = [(a, t) for a, t in zip(ans, truth) if t != "변화없음"]
    said = [(a, t) for a, t in nz if a in ("오름", "내림")]
    hit = sum(a == t for a, t in said)
    up = sum(t == "오름" for _, t in nz)
    said_all = [(a, t) for a, t in zip(ans, truth) if a in ("오름", "내림")]
    sims = []
    for _ in range(1000):
        sims.append(sum(rng.choice(("오름", "내림")) == t for _, t in nz) / len(nz) if nz else float("nan"))
    sims.sort()
    return {"n": n, "변화없음": n - len(nz), "방향있음": len(nz), "답함": len(said), "적중": hit,
            "모름": sum(a == "모름" for a in ans), "형식밖": sum(a == "형식 밖" for a in ans), "답없음": sum(a == "답 없음" for a in ans),
            "답_오름": sum(a == "오름" for a in ans), "답_내림": sum(a == "내림" for a in ans),
            "기준_전부오름": up, "기준_전부내림": len(nz) - up,
            "무작위_lo": sims[25] if nz else float("nan"), "무작위_hi": sims[974] if nz else float("nan"),
            "답함_0포함": len(said_all), "적중_0포함": hit}


def report_b(k: pd.DataFrame, name: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    k.to_csv(out_dir / f"{name}_B_건.csv", index=False, encoding="utf-8-sig")
    rng = random.Random(SEED)
    groups = [(f"{kind} · {seg}", g) for (kind, seg), g in k.groupby(["갈래", "구간"], sort=False)]
    if "제목_반복수" in k:                                        # 틀 제목(같은 글자 제목이 10줄 이상 — 상승률 상위 목록 등)을 뺀 줄
        tmpl = pd.to_numeric(k["제목_반복수"], errors="coerce").fillna(0) >= TEMPLATE_MIN
        for (kind, seg), g in k[~tmpl].groupby(["갈래", "구간"], sort=False):
            if len(g) < int(((k["갈래"] == kind) & (k["구간"] == seg)).sum()):
                groups.append((f"{kind} · {seg} (틀 제목 뺌)", g))
    back = k[k["구간"] == "뒤"]
    if back["갈래"].nunique() > 1:
        groups.append(("뒤 구간 합침(일반 기사 + 시세 중계)", back))
    groups.append(("전체", k))
    res = {}
    L = [f"# 실험 B 채점 요약 — {name}", "",
         f"- 표본 {len(k)}건 · 답이 온 건 {int(k['답있음'].sum())}건. 대괄호 = 윌슨 95% 구간.",
         "- 적중률(답한 것 중) = 오름/내림으로 답했고 수익률이 0 이 아닌 건 가운데 방향이 맞은 비율. 수익률 0(변화 없음)은 분모에서 뺀다.",
         "- 전체 대비 = 방향이 있는 건 전체가 분모(모름·형식 밖·답 없음은 못 맞힌 것으로).",
         "- 기준선: 전부 '오름'이라고 했을 때 · 전부 '내림' · 무작위(기대값 50%, 고정 시드 1,000회 모의의 2.5~97.5% 범위).", ""]
    for h, lab in (("post5", "기사 뒤 5분"), ("post30", "기사 뒤 30분")):
        L += [f"## {lab} ({h})", "",
              "| 묶음 | 표본 | 변화 없음(뺌) | 답한 것 중 적중률 | 전체 대비 적중률 | 모름 비율 | 답 오름/내림/모름/형식 밖/답 없음 | 전부 오름 | 전부 내림 | 무작위 범위 | 0 을 오답으로 치면 |",
              "|---|---:|---:|---|---|---|---|---|---|---|---|"]
        for lab2, g in groups:
            s = stat_b(g, h, rng)
            res[(lab2, h)] = s
            L.append(f"| {lab2} | {s['n']} | {s['변화없음']} | {pct(s['적중'], s['답함'])} | {pct(s['적중'], s['방향있음'])} | {pct(s['모름'] + s['형식밖'] + s['답없음'], s['n'])} | "
                     f"{s['답_오름']}/{s['답_내림']}/{s['모름']}/{s['형식밖']}/{s['답없음']} | {pct(s['기준_전부오름'], s['방향있음'], False)} | {pct(s['기준_전부내림'], s['방향있음'], False)} | "
                     f"{100 * s['무작위_lo']:.1f}~{100 * s['무작위_hi']:.1f}% | {pct(s['적중_0포함'], s['답함_0포함'], False)} |")
        a, b = res.get(("일반 기사 · 앞", h)), res.get(("일반 기사 · 뒤", h))
        if a and b and a["답함"] and b["답함"]:
            pa, pb = a["적중"] / a["답함"], b["적중"] / b["답함"]
            se = math.sqrt(pa * (1 - pa) / a["답함"] + pb * (1 - pb) / b["답함"])
            L += ["", f"- 일반 기사 앞 − 뒤 = {100 * (pa - pb):+.1f}%p (정규 근사 95% 구간 {100 * (pa - pb - 1.96 * se):+.1f} ~ {100 * (pa - pb + 1.96 * se):+.1f}%p, 앞 {a['답함']}건 · 뒤 {b['답함']}건)"]
            res[("앞-뒤", h)] = pa - pb
        L.append("")
    (out_dir / f"{name}_B_요약.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return res


# ================================================================ 자체 시험
def fmt_exact(t: Decimal, unit: str, rng: random.Random):
    """정답과 같은 값을 여러 표기로 — 정규화가 전부 '정답'으로 읽어야 한다."""
    forms = ["plain", "comma", "unit", "number"]
    if t == t.to_integral_value() and t != 0 and t % 100000000 == 0:
        forms.append("eok")
    if t == t.to_integral_value() and t != 0 and t % 1000000 == 0:
        forms.append("mil")
    if t < 0:
        forms.append("tri")
    f = rng.choice(forms)
    i = t == t.to_integral_value()
    body = f"{int(t):,}" if i else format(t, "f")
    u = {"원": "원", "주": "주", "%": "%", "%p": "%p", "회차": "회", "명": "명"}.get(unit, "")
    if f == "plain":
        return format(t, "f")
    if f == "comma":
        return body
    if f == "unit":
        return f" {body} {u}"
    if f == "number":
        return int(t) if i else float(t)
    if f == "eok":
        q = int(t) // 100000000
        jo, eok = divmod(abs(q), 10000)
        s = (f"{jo}조" if jo else "") + (f" {eok:,}억" if eok else "")
        return ("-" if q < 0 else "") + s.strip() + "원"
    if f == "mil":
        return f"{int(t) // 1000000:,}백만{u}"
    return f"△{abs(int(t)):,}" if i else f"△{format(abs(t), 'f')}"


def fake_a(key: pd.DataFrame, rng: random.Random):
    """정답을 일부러 조금 틀리게 만든 가짜 답 + 기대 채점 결과."""
    answers, expect = defaultdict(dict), {}
    docs = list(dict.fromkeys(key["rcept_no"]))
    skip_docs = set(rng.sample(docs, max(1, len(docs) // 50)))            # 문서째 답이 안 온 경우
    for k in key.itertuples(index=False):
        ck = (k.rcept_no, k.칸)
        name = k.칸 if rng.random() < 0.5 else k.질문이름                  # 칸 이름 두 가지 다 받는지
        if k.rcept_no in skip_docs:
            expect[ck] = ("답없음", "답없음", "") if k.상태 == "값" else ("비움",) if k.상태 == "빈칸" else None
            continue
        if k.상태 == "해석불가":
            answers[k.rcept_no][name] = "아무 값"
            expect[ck] = None
            continue
        u = rng.random()
        if k.상태 == "빈칸":
            if u < 0.20:
                answers[k.rcept_no][name] = "12,345" if k.형 == "num" else "2026년 01월 02일" if k.형 == "date" else "등기임원"
                expect[ck] = ("값 채움",)
            elif u < 0.27 and k.형 == "num":
                answers[k.rcept_no][name] = rng.choice([0, "0", "0원"])
                expect[ck] = ("0 채움",)
            else:
                v = rng.choice([None, "-", "해당사항 없음", "", "MISSING"])
                if v != "MISSING":
                    answers[k.rcept_no][name] = v
                expect[ck] = ("비움",)
            continue
        if u < 0.10:                                                       # 답 없음
            v = rng.choice([None, "-", "없음", "MISSING"])
            if v != "MISSING":
                answers[k.rcept_no][name] = v
            expect[ck] = ("답없음", "답없음", "")
            continue
        if k.형 == "num":
            t = Decimal(k.정답)
            if u < 0.17 and t != 0:
                answers[k.rcept_no][name] = format(t * 1000, "f")
                expect[ck] = ("오답", "오답", "자릿수만 틀림")
            elif u < 0.22 and t != 0:
                answers[k.rcept_no][name] = format(-t, "f")
                expect[ck] = ("오답", "오답", "부호만 틀림")
            elif u < 0.29 and (k.단위 in ("%", "%p") or abs(t) >= 1000):
                a = t + Decimal("0.04") if k.단위 in ("%", "%p") else t + max(1, int(abs(t) * Decimal("0.002")))
                answers[k.rcept_no][name] = format(a, "f")
                expect[ck] = ("오답", "정답", "반올림 차이")
            elif u < 0.34 and abs(t) >= 10:
                a = t * 3 + 7                                              # 10^k 배가 아닌 틀린 값
                answers[k.rcept_no][name] = f"{a:,}"
                expect[ck] = ("오답", "오답", "값 다름")
            elif u < 0.37:
                answers[k.rcept_no][name] = "본문 참조"
                expect[ck] = ("오답", "오답", "답 해석 못 함")
            else:
                answers[k.rcept_no][name] = fmt_exact(t, k.단위, rng)
                expect[ck] = ("정답", "정답", "")
        elif k.형 == "date":
            y, m, d = int(k.정답[:4]), int(k.정답[4:6]), int(k.정답[6:])
            if u < 0.18:
                d2 = d + 1 if d < 28 else d - 1
                answers[k.rcept_no][name] = f"{y}-{m:02d}-{d2:02d}"
                expect[ck] = ("오답", "오답", "날짜 다름(일)")
            elif u < 0.24:
                answers[k.rcept_no][name] = f"{y % 100:02d}.{m:02d}.{d:02d}"
                expect[ck] = ("오답", "정답", "두 자리 연도")
            else:
                answers[k.rcept_no][name] = rng.choice([f"{y}년 {m}월 {d}일", f"{y}-{m:02d}-{d:02d}", f"{y}.{m}.{d}", f"{y}{m:02d}{d:02d}", f"{y}. {m:02d}. {d:02d}.", int(k.정답)])
                expect[ck] = ("정답", "정답", "")
        else:
            if u < 0.20:
                answers[k.rcept_no][name] = "전혀다른분류"
                expect[ck] = ("오답", "오답", "분류 다름")
            elif u < 0.30 and len(squash(k.정답)) >= 4:
                answers[k.rcept_no][name] = squash(k.정답)[:-2]
                expect[ck] = ("오답", "정답", "표기 차이(포함)")
            else:
                answers[k.rcept_no][name] = rng.choice([k.정답, " " + k.정답.replace(" ", "  ") + " "])
                expect[ck] = ("정답", "정답", "")
    return {r: answers.get(r, {}) for r in docs if r not in skip_docs}, expect


def selftest() -> int:
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # 1) 정규화 단위 시험
    D = Decimal
    for src, want in [("1,234,567", D(1234567)), ("9,000,000,000원", D(9000000000)), ("90억원", D(9000000000)), ("1조 2,000억", D(1200000000000)),
                      ("9,000백만원", D(9000000000)), ("3.5천만원", D(35000000)), ("3.0%", D("3.0")), ("12.02 %", D("12.02")), ("-34.01%p", D("-34.01")),
                      ("△123,456,789", D(-123456789)), ("(123,456,789)", D(-123456789)), ("−12,345,678원", D(-12345678)), ("▲1,000", D(-1000)),
                      ("제3회", D(3)), ("약 100주", D(100)), (5, D(5)), (0.3, D("0.3")), ("0", D(0)), ("1.5e3", D(1500)), ("2억 5천만원", D(250000000)),
                      ("본문 참조", None), ("12-34", None), ("3,000 ~ 4,000", None), (True, None)]:
        got = parse_num(src)
        check(got == want, f"parse_num({src!r}) = {got} ≠ {want}")
    for src, want in [("2026년 04월 08일", ("20260408", False)), ("2026-4-8", ("20260408", False)), ("2026.04.08.", ("20260408", False)), (20260408, ("20260408", False)),
                      ("2026. 4. 8", ("20260408", False)), ("26.04.08", ("20260408", True)), ("미정", (None, False)), ("2026년 13월 40일", (None, False))]:
        got = parse_date(src)
        check(got == want, f"parse_date({src!r}) = {got} ≠ {want}")
    for src, want in [(None, True), ("-", True), (" 해당사항 없음 ", True), ("없음.", True), (0, False), ("0", False), ("", True), (float("nan"), True)]:
        check(is_blank(src) == want, f"is_blank({src!r}) ≠ {want}")
    c = grade_cell("num", "원", "9000000000", "9,000", True)
    check(c["오답갈래"] == "자릿수만 틀림" and c["배수_k"] == -6 and c["자릿수일치"] == 0 and c["부호일치"] == 1, f"백만 단위 그대로 답한 경우: {c}")
    c = grade_cell("num", "%", "12.02", "12.0", True)
    check(c["엄격"] == "오답" and c["관용"] == "정답", f"반올림: {c}")
    c = grade_cell("num", "주", "0.3", "0", True)
    check(c["관용"] == "오답", f"0.3 → 0 은 관용으로도 오답이어야: {c}")
    c = grade_cell("num", "원", "-123456789", "123,456,789", True)
    check(c["오답갈래"] == "부호만 틀림" and c["부호일치"] == 0 and c["자릿수일치"] == 1, f"부호: {c}")
    check(grade_empty("num", "0", True) == "0 채움" and grade_empty("num", "-", True) == "비움" and grade_empty("date", "2026-01-01", True) == "값 채움", "빈 칸 판정")
    check(abs(wilson(50, 100)[0] - 0.4038) < 0.001 and abs(wilson(50, 100)[1] - 0.5962) < 0.001, f"윌슨 구간: {wilson(50, 100)}")

    # 2) A — 가짜 답을 채점해 넣은 오류 수와 채점 결과가 맞는지
    key = pd.read_csv(EP09 / "sample_A_정답.csv", dtype=str, encoding="utf-8-sig").fillna("")
    rng = random.Random(SEED)
    answers, expect = fake_a(key, rng)
    TEST.mkdir(parents=True, exist_ok=True)
    fake_path = TEST / "가짜답_A.jsonl"
    with fake_path.open("w", encoding="utf-8") as f:
        for i, (rcp, a) in enumerate(answers.items()):                    # 두 가지 줄 형식을 번갈아
            f.write(json.dumps({"rcept_no": rcp, "answer": a} if i % 2 else {"접수번호": rcp, **a}, ensure_ascii=False) + "\n")
    cells = grade_a(load_answers_a(fake_path))
    bad = 0
    for r in cells.itertuples(index=False):
        e = expect[(r.rcept_no, r.칸)]
        got = None if r.정답상태 == "해석불가" else (r.빈칸결과,) if r.정답상태 == "빈칸" else (r.엄격, r.관용, r.오답갈래)
        if got != e:
            bad += 1
            if bad <= 10:
                fails.append(f"A 칸 불일치 {r.rcept_no} {r.칸}: 정답 {r.정답!r} 답 {r.답_원문!r} → {got}, 기대 {e}")
    meta = pd.read_csv(EP09 / "sample_A.csv", dtype=str, encoding="utf-8-sig")
    rep = report_a(cells, "자체시험", TEST, meta)
    exp_cnt = Counter(e for e in expect.values() if e)
    t = rep["total"]
    check(t["정답_엄격"] == sum(v for k, v in exp_cnt.items() if len(k) == 3 and k[0] == "정답"), "A 합계: 엄격 정답 수")
    check(t["정답_관용"] == sum(v for k, v in exp_cnt.items() if len(k) == 3 and k[1] == "정답"), "A 합계: 관용 정답 수")
    check(t["답없음"] == sum(v for k, v in exp_cnt.items() if len(k) == 3 and k[0] == "답없음"), "A 합계: 답 없음 수")
    check(t["빈칸_값채움"] == exp_cnt[("값 채움",)] and t["빈칸_0채움"] == exp_cnt[("0 채움",)] and t["빈칸_비움"] == exp_cnt[("비움",)], "A 합계: 빈 칸")
    check(t["칸_값"] == t["정답_엄격"] + t["오답_엄격"] + t["답없음"], "A 합계: 정답+오답+답없음 = 값 칸")
    # 정답 그대로 넣으면 전부 정답·빈 칸 전부 비움이어야 한다
    perfect = defaultdict(dict)
    for k in key.itertuples(index=False):
        perfect[k.rcept_no][k.칸] = k.원값
    pc = grade_a(dict(perfect))
    pt = agg_a(pc)
    check(pt["정답_엄격"] == pt["칸_값"] and pt["빈칸_비움"] == pt["칸_빈칸"], f"정답지 그대로 넣었는데 만점이 아님: {pt}")
    check(int(doc_table(pc)["전부맞음_엄격+빈칸지킴"].sum()) == pc["rcept_no"].nunique(), "정답지 그대로: 문서 전부 맞음")

    # 3) B — 맞힐 확률을 정해 만든 가짜 답
    kb = pd.read_csv(EP09 / "sample_B.csv", dtype=str, encoding="utf-8-sig").fillna("")
    rng = random.Random(SEED + 1)
    ans_b, exp_hit, exp_said, exp_dk = {}, Counter(), Counter(), Counter()
    for r in kb.itertuples(index=False):
        grp = f"{r.갈래} · {r.구간}"
        u = rng.random()
        if u < 0.03:
            continue                                                       # 답이 안 온 건
        p5 = float(r.post5)
        truth = "오름" if p5 > 0 else "내림" if p5 < 0 else "변화없음"
        if u < 0.18:
            ans_b[r.id] = rng.choice(["모름", "중립", None])
            exp_dk[grp] += 1
            continue
        if u < 0.20:
            ans_b[r.id] = "글쎄요"
            continue
        right = rng.random() < 0.6
        a = truth if (right and truth != "변화없음") else ("내림" if truth == "오름" else "오름")
        ans_b[r.id] = rng.choice({"오름": ["오름", "상승", "UP"], "내림": ["내림", "하락", "down"]}[a])
        if truth != "변화없음":
            exp_said[grp] += 1
            exp_hit[grp] += int(a == truth)
    fb = TEST / "가짜답_B.jsonl"
    with fb.open("w", encoding="utf-8") as f:
        for i, a in ans_b.items():
            f.write(json.dumps({"id": i, "answer": a}, ensure_ascii=False) + "\n")
    res = report_b(grade_b(load_answers_b(fb)), "자체시험", TEST)
    for grp in exp_said:
        s = res[(grp, "post5")]
        check(s["답함"] == exp_said[grp] and s["적중"] == exp_hit[grp] and s["모름"] == exp_dk[grp], f"B {grp}: 채점 {s['적중']}/{s['답함']} 모름 {s['모름']} ≠ 기대 {exp_hit[grp]}/{exp_said[grp]} 모름 {exp_dk[grp]}")
        check(s["기준_전부오름"] + s["기준_전부내림"] == s["방향있음"] and s["방향있음"] + s["변화없음"] == s["n"], f"B {grp}: 분모")
    tot = res[("전체", "post5")]
    check(tot["답없음"] == len(kb) - len(ans_b), "B: 답 없는 건 수")

    print(f"정규화 시험 · A 칸 {len(cells)}개(값 {t['칸_값']} · 빈칸 {t['칸_빈칸']}) · B {len(kb)}건")
    print(f"A 가짜 답 결과: 엄격 정답 {t['정답_엄격']} · 관용 정답 {t['정답_관용']} · 오답(엄격) {t['오답_엄격']} · 답 없음 {t['답없음']} · 빈칸 값 채움 {t['빈칸_값채움']} · 0 채움 {t['빈칸_0채움']}")
    print(f"B 가짜 답 결과(post5 전체): 답함 {tot['답함']} · 적중 {tot['적중']} · 모름 {tot['모름']} · 형식 밖 {tot['형식밖']} · 답 없음 {tot['답없음']}")
    if fails:
        print(f"\n자체 시험 실패 {len(fails)}건" + (f" (A 칸 불일치 {bad}개)" if bad else ""))
        for m in fails[:30]:
            print("  -", m)
        return 1
    print(f"자체 시험 통과 — 산출물 {TEST}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="9편 실험 채점기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("a", "b"):
        p = sub.add_parser(c)
        p.add_argument("--answers", required=True)
        p.add_argument("--name", default="")
        p.add_argument("--key", default="", help="정답 파일(기본: data/ep09/sample_A_정답.csv · sample_B.csv)")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "selftest":
        sys.exit(selftest())
    path = Path(a.answers)
    name = a.name or path.stem
    key = Path(a.key) if a.key else None
    if a.cmd == "a":
        meta = pd.read_csv(EP09 / "sample_A.csv", dtype=str, encoding="utf-8-sig") if not key else None
        rep = report_a(grade_a(load_answers_a(path), key), name, OUT, meta)
        t = rep["total"]
        print(f"A {name}: 값 칸 {t['칸_값']} · 엄격 정답 {t['정답_엄격']} · 관용 정답 {t['정답_관용']} · 답 없음 {t['답없음']} · 빈칸 {t['칸_빈칸']} 중 값 채움 {t['빈칸_값채움']}")
    else:
        res = report_b(grade_b(load_answers_b(path), key), name, OUT)
        s = res[("전체", "post5")]
        print(f"B {name}: post5 답함 {s['답함']} · 적중 {s['적중']} · 모름 {s['모름']}")
    print("저장:", OUT)


if __name__ == "__main__":
    main()
