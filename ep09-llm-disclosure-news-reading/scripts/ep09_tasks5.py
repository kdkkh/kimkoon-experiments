# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 5단계 — 뜻 판단 과제 정의 · 정답 · 표본 (2026-11-18). 파일만 읽는다 — 모델 호출·외부 API·새 수집 없음.

입력은 3단계 표본(2단계 sample_A.csv 266건)의 OpenDART 원문 zip 뿐이다. 1~4단계 파일은 읽기·불러오기만 한다.

과제
  C5  정정 공시 비교 — 정정 공시 원문을 주고 "무엇이 무엇에서 무엇으로 바뀌었나"를 JSON 목록으로.
      정답 = 원문 맨 앞 정정 표(DART <CORRECTION>)의 '정정 전'·'정정 후' 칸을 코드로 읽어,
             두 칸이 모두 '숫자 하나 · 날짜 하나 · -' 가운데 하나이고 서로 다른 줄의 (전, 후) 값 짝. 문서 안 같은 짝은 하나로 센다.
  S5  요약 — 공시 1건을 3문장 이내로. 채점은 (a) 요약 속 수·날짜가 원문에 있는가(코드 대조) (b) 3단계 정답표 값 칸 중 요약에 든 비율.
  J5  판단과 근거 — 종류별 예/아니오/판단 불가 문항 셋(J5_BANK). 정답은 3단계 정답표 칸 값에서 규칙(코드)으로, 상수 문항은 공시 종류의 정의로.
      답과 함께 원문 구절을 글자 그대로 인용하게 하고, 인용이 원문에 있는지 코드로 대조.

쓰기(이 폴더에서):
  python -X utf8 scripts/ep09_tasks5.py build      # data/ep09/과제5/ 에 표본·정답·깔때기(같은 시드 → 같은 결과)
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
import ep09_run as R            # noqa: E402  (doc_text·phash 만 — 고치지 않음)
import ep09_tasks3 as T3        # noqa: E402  (load_docs·key_a3 만 — 고치지 않음)
import dart_tables as E        # noqa: E402  (표 읽기 도구만 — 원본 extract_fields.py 에서 옮김)

EP09 = DATA / "ep09"
T5 = EP09 / "과제5"
SEED5 = 20261118
CAP_PER_KIND = 12               # S5·J5 표본: 종류마다 최대 12건(내가 정함)
RERUN_N = 60                    # 재실행: J5 Sonnet 60건

# ================================================================ 값 정규화(정답·채점 공용)
UNIT_TAIL = r"(?:원/주|원|주|%p|%|명|회차|회|배)?"
NUM_RE = re.compile(r"^\(?([-△▲−]?)\s*(\d[\d,]*(?:\.\d+)?)\)?\s*" + UNIT_TAIL + r"$")
DATE_RE = re.compile(r"^(\d{4})\s*(?:년|\.|-|/)\s*(\d{1,2})\s*(?:월|\.|-|/)\s*(\d{1,2})\s*(?:일)?\.?$")
EMPTY = {"-", "−", "–", "—", "없음", "해당없음", "해당사항없음", "해당사항 없음", "해당 없음", "null", "None"}


def dnum(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None


def ymd(y, m, d) -> str | None:
    try:
        return date(int(y), int(m), int(d)).strftime("%Y%m%d")
    except ValueError:
        return None


def norm_val(s) -> tuple[str, object]:
    """정정 표 칸 · 모델 답 칸 → ('빈','-') | ('num', Decimal) | ('date', 'YYYYMMDD') | ('글', 원문) | ('없음', '')"""
    if s is None:
        return ("빈", "-")
    s = re.sub(r"\s+", " ", str(s)).strip()
    if s == "":
        return ("없음", "")
    if s.replace(" ", "") in {e.replace(" ", "") for e in EMPTY}:
        return ("빈", "-")
    m = DATE_RE.match(s)
    if m:
        v = ymd(*m.groups())
        if v:
            return ("date", v)
    m = NUM_RE.match(s.replace(" ", ""))
    if m:
        v = dnum(m.group(2))
        if v is not None:
            return ("num", -v if m.group(1) else v)
    return ("글", s)


def norm_val_loose(s) -> tuple[str, object]:
    """모델 답 쪽(내가 정함): 엄격 정규화가 '글'이면, 날짜가 딱 하나 · 숫자가 딱 하나 든 글은 그 값으로 읽는다."""
    k, v = norm_val(s)
    if k != "글":
        return k, v
    ds = find_dates(str(s))
    if len(ds) == 1 and ds[0][0] == "date":
        rest = str(s)[:ds[0][2]] + str(s)[ds[0][3]:]
        if not re.search(r"\d", rest):
            return ("date", ds[0][1])
    nums = re.findall(r"\d[\d,]*(?:\.\d+)?", str(s))
    if len(nums) == 1 and not ds:
        v = dnum(nums[0])
        if v is not None:
            neg = bool(re.search(r"[-△▲−]\s*" + re.escape(nums[0]), str(s)))
            return ("num", -v if neg else v)
    return ("글", s)


def same(a: tuple, b: tuple) -> bool:
    if a[0] != b[0]:
        return False
    if a[0] == "num":
        return Decimal(a[1]) == Decimal(b[1])
    return a[1] == b[1]


def fmtv(t: tuple) -> str:
    k, v = t
    if k == "num":
        s = format(Decimal(v), "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    return str(v)


DATE_PATS = [
    ("date", re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")),
    ("date", re.compile(r"(?<!\d)(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})(?!\d)")),
    ("ym", re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월(?!\s*\d)")),
    ("md", re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일")),
    ("y", re.compile(r"(?<!\d)(\d{4})\s*년(?!\s*\d)")),
]


def find_dates(s: str) -> list[tuple[str, str, int, int]]:
    """글 속 날짜 → [(형, 값, 시작, 끝)] — 겹치면 앞 규칙(긴 형)이 먼저."""
    out, used = [], []
    for kind, pat in DATE_PATS:
        for m in pat.finditer(s):
            if any(not (m.end() <= a or m.start() >= b) for a, b in used):
                continue
            g = m.groups()
            if kind == "date":
                v = ymd(*g)
            elif kind == "ym":
                v = f"{int(g[0]):04d}{int(g[1]):02d}" if 1 <= int(g[1]) <= 12 else None
            elif kind == "md":
                v = f"{int(g[0]):02d}{int(g[1]):02d}" if 1 <= int(g[0]) <= 12 and 1 <= int(g[1]) <= 31 else None
            else:
                v = g[0]
            if v:
                out.append((kind, v, m.start(), m.end()))
                used.append((m.start(), m.end()))
    return sorted(out, key=lambda x: x[2])


def doc_index(text: str) -> dict:
    """원문 글 → 숫자 집합(절댓값) · 날짜 집합 · 공백 뺀 글."""
    dates = {v for k, v, _, _ in find_dates(text) if k == "date"}
    nums = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text):
        v = dnum(m.group(0))
        if v is not None:
            nums.add(v)
    return {"dates": dates, "nums": nums, "flat": re.sub(r"\s+", "", text)}


# ================================================================ C5 정정 표
def corr_rows(rcp: str) -> tuple[list[dict], str]:
    """정정 표 → [{항목, 전, 후}] (전·후 칸이 같은 칸으로 합쳐진 줄은 뺌) · 표 글."""
    x = E.raw_of(rcp)
    xf = 'class="xforms"' in x or "xforms_input" in x
    blk, _ = (E.split_correction_xforms(x) if xf else E.split_correction_dart(x))
    if not blk:
        return [], ""
    p = E.TableParser(xf)
    p.feed(blk)
    rows = []
    n_hdr = 0
    for t in p.tables:
        if n_hdr and t is not None and any("정정전" in E.norm_label(c.text) for row in t.rows for c in row):
            break                       # 앞선 정정의 표(정정 신고가 여러 번 쌓인 문서) — 맨 앞(이번 정정) 표만 쓴다(내가 정함)
        G = E.build_grid(t)
        if not G:
            continue
        nr, nc = max(r for r, _ in G) + 1, max(c for _, c in G) + 1
        hdr, cols = -1, {}
        for r in range(nr):
            txt = [E.norm_label(G[(r, c)].text) if (r, c) in G else "" for c in range(nc)]
            if any("정정전" in s for s in txt) and any("정정후" in s for s in txt):
                for c, s in enumerate(txt):
                    if "정정전" in s:
                        cols.setdefault("전", c)
                    elif "정정후" in s:
                        cols.setdefault("후", c)
                    elif "사유" in s:
                        cols.setdefault("사유", c)
                hdr = r
                break
        if hdr < 0 or "전" not in cols or "후" not in cols:
            continue
        n_hdr += 1
        lab_end = min(cols.get("사유", 99), cols["전"], cols["후"])
        for r in range(hdr + 1, nr):
            b, a = G.get((r, cols["전"])), G.get((r, cols["후"]))
            if b is None or a is None or b is a:
                continue
            labs = []
            for c in range(lab_end):
                cell = G.get((r, c))
                if cell is not None and cell is not b and all(cell is not l for l in labs):
                    labs.append(cell)
            rows.append({"항목": " > ".join(E.clean(c.text) for c in labs if E.clean(c.text)),
                         "전": E.clean(b.text), "후": E.clean(a.text)})
    return rows, blk


def c5_build(docs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    cand = docs[docs["정정"] == "1"].sort_values(["kind", "rcept_no"])
    keyrows, drows = [], []
    why = Counter()
    for r in cand.itertuples(index=False):
        rows, blk = corr_rows(r.rcept_no)
        pairs, seen = [], set()
        n_text = n_same = n_empty = 0
        for it in rows:
            b, a = norm_val(it["전"]), norm_val(it["후"])
            if b[0] == "없음" or a[0] == "없음":
                n_empty += 1
                continue
            if b[0] == "글" or a[0] == "글":
                n_text += 1
                continue
            if (b[0] == "빈" and a[0] == "빈") or same(b, a):
                n_same += 1
                continue
            key = (b[0], fmtv(b), a[0], fmtv(a))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((it, b, a))
        reason = "" if pairs else ("정정 표 없음" if not rows else "코드로 읽을 수 있는 (전, 후) 값 짝 없음")
        why[reason or "씀"] += 1
        drows.append({"kind": r.kind, "종류": r.종류, "rcept_no": r.rcept_no, "corp_name": r.corp_name, "원문_글자수": r.원문_글자수,
                      "정정표_줄": len(rows), "값짝": len(pairs), "글_줄": n_text, "같은값_줄": n_same, "빈칸_줄": n_empty, "뺀_이유": reason})
        for i, (it, b, a) in enumerate(pairs, 1):
            keyrows.append({"kind": r.kind, "rcept_no": r.rcept_no, "짝": f"p{i:02d}", "항목": it["항목"], "전_원문": it["전"], "후_원문": it["후"],
                            "전_형": b[0], "전_값": fmtv(b), "후_형": a[0], "후_값": fmtv(a)})
    d = pd.DataFrame(drows)
    k = pd.DataFrame(keyrows)
    L = ["## C5 정정 공시 비교 — 깔때기", "",
         f"- 3단계 표본 266건 중 정정 공시(sample_A.csv `정정`=1): **{len(cand)}건**",
         f"- 정정 표(DART <CORRECTION>)를 찾은 문서: {int((d['정정표_줄'] > 0).sum())}건 · 표 줄 합 {int(d['정정표_줄'].sum())}",
         f"- 줄 갈래: 값 짝으로 씀 {int(d['값짝'].sum())}(문서 안 중복 뺀 뒤) · 글 칸(숫자·날짜·'-' 하나가 아님) {int(d['글_줄'].sum())} · 전후 같음/둘 다 '-' {int(d['같은값_줄'].sum())} · 칸이 빔(안쪽 표) {int(d['빈칸_줄'].sum())}",
         f"- 뺀 문서: " + " · ".join(f"{k_} {v}" for k_, v in why.items() if k_ != "씀"),
         f"- **쓰는 문서 {why['씀']}건 · 정답 값 짝 {len(k)}개**", "",
         "| 종류 | 정정 공시 | 쓰는 문서 | 값 짝 |", "|---|---:|---:|---:|"]
    for kind, g in d.groupby("종류", sort=False):
        L.append(f"| {kind} | {len(g)} | {int((g['뺀_이유'] == '').sum())} | {int(g['값짝'].sum())} |")
    if len(k):
        L += ["", f"- 값 짝의 형: 전 {dict(Counter(k['전_형']))} · 후 {dict(Counter(k['후_형']))}", ""]
    return d, k, L


# ================================================================ J5 문항 은행
# (id, 질문, 규칙 이름, 출처) — 출처 '상수' = 공시 종류의 정의로 정한 답(모든 문서에 같음), '칸' = 정답표 칸 값으로 정함.
Q_SHARES = "이 공시에 적힌 일이 그대로 이루어지면, 이 공시를 낸 회사의 발행주식 총수가 늘어나는가?"
Q_CASH = "이 공시에 적힌 일로 이 공시를 낸 회사에 현금이 들어오는가?"
J5_BANK: dict[str, list[tuple[str, str, str, str]]] = {
    "tsstkAqDecsn": [
        ("j1", Q_SHARES, "아니오", "상수"),
        ("j2", Q_CASH, "아니오", "상수"),
        ("j3", "회사는 이 공시에서 사들이기로 한 주식을 정한 기간 안에 모두 사들이게 되는가?", "판단 불가", "상수"),
    ],
    "tsstkDpDecsn": [
        ("j1", Q_SHARES, "아니오", "상수"),
        ("j2", "이 공시에 적힌 처분이 이루어지면, 회사가 들고 있는 자기주식 수는 줄어드는가?", "예", "상수"),
        ("j3", "처분 방법 가운데 거래소 밖에서(장외) 넘기는 주식이 있는가?", "dp_m_otc>0", "칸"),
    ],
    "tsstkAqTrctrCnsDecsn": [
        ("j1", Q_SHARES, "아니오", "상수"),
        ("j2", Q_CASH, "아니오", "상수"),
        ("j3", "이 계약을 맺기 전에 회사가 이미 자기주식(보통주)을 들고 있는가?", "aq_wtn_div_ostk>0 또는 eaq_ostk>0", "칸"),
    ],
    "tsstkAqTrctrCcDecsn": [
        ("j1", Q_SHARES, "아니오", "상수"),
        ("j2", "계약을 해지한 뒤에도 남는 계약 금액이 있는가?", "ctr_prc_atcc>0", "칸"),
        ("j3", "해지하는 계약의 원래 계약 기간(종료일 − 시작일)은 200일보다 긴가?", "days(ctr_pd_bfcc_bgd, ctr_pd_bfcc_edd)>200", "칸"),
    ],
    "piicDecsn": [
        ("j1", Q_SHARES, "nstk_ostk_cnt>0 또는 nstk_estk_cnt>0", "칸"),
        ("j2", "모은 돈 가운데 회사 운영에 쓰는 돈(운영자금)이 있는가?", "fdpp_op>0", "칸"),
        ("j3", "새 주식을 기존 주주에게 가진 주식 비율대로 먼저 배정하는가?", "ic_mthn ∈ {주주배정증자, 주주배정후 실권주 일반공모, 주주우선공모증자}", "칸"),
    ],
    "fricDecsn": [
        ("j1", Q_SHARES, "nstk_ostk_cnt>0", "칸"),
        ("j2", Q_CASH, "아니오", "상수"),
        ("j3", "기존 보통주 1주를 가진 주주는 새 보통주를 1주 이상 받는가?", "nstk_ascnt_ps_ostk>=1", "칸"),
    ],
    "pifricDecsn": [
        ("j1", Q_SHARES, "piic_nstk_ostk_cnt>0 또는 fric_nstk_ostk_cnt>0", "칸"),
        ("j2", "무상으로 나눠 주는 새 보통주가 유상으로 발행하는 새 보통주보다 많은가?", "fric_nstk_ostk_cnt>piic_nstk_ostk_cnt", "칸"),
        ("j3", "유상증자로 모은 돈 가운데 빚을 갚는 데 쓰는 돈(채무상환자금)이 있는가?", "piic_fdpp_dtrp>0", "칸"),
    ],
    "crDecsn": [
        ("j1", Q_SHARES, "atcr_tisstk_ostk>bfcr_tisstk_ostk", "칸"),
        ("j2", Q_CASH, "아니오", "상수"),
        ("j3", "감자 뒤 자본금은 감자 전 자본금의 절반보다 적어지는가?", "atcr_cpt*2<bfcr_cpt", "칸"),
    ],
    "cvbdIsDecsn": [
        ("j1", "이 사채가 모두 주식으로 바뀌면, 이 공시를 낸 회사의 발행주식 총수가 늘어나는가?", "cvisstk_cnt>0", "칸"),
        ("j2", "이 사채를 산 쪽이 실제로 주식으로 바꾸게 되는가?", "판단 불가", "상수"),
        ("j3", "이 사채의 만기이자율은 표면이자율보다 높은가?", "bd_intr_sf>bd_intr_ex", "칸"),
    ],
    "bdwtIsDecsn": [
        ("j1", "이 사채에 붙은 새 주식을 살 권리가 모두 쓰이면, 이 공시를 낸 회사의 발행주식 총수가 늘어나는가?", "nstk_isstk_cnt>0", "칸"),
        ("j2", "이 사채를 산 쪽이 실제로 그 권리를 써서 새 주식을 사게 되는가?", "판단 불가", "상수"),
        ("j3", "이 사채의 만기이자율은 표면이자율보다 높은가?", "bd_intr_sf>bd_intr_ex", "칸"),
    ],
    "exbdIsDecsn": [
        ("j1", "이 사채가 모두 다른 주식으로 교환되면, 이 공시를 낸 회사의 발행주식 총수가 늘어나는가?", "아니오", "상수"),
        ("j2", "이 사채의 만기이자율은 표면이자율보다 높은가?", "bd_intr_sf>bd_intr_ex", "칸"),
        ("j3", "이 사채를 산 쪽이 실제로 교환을 청구하게 되는가?", "판단 불가", "상수"),
    ],
    "cmpMgDecsn": [
        ("j1", "이 합병으로 합병 뒤 남는 회사(존속회사)가 새 주식(합병신주)을 발행하는가?", "mgnstk_ostk_cnt>0", "칸"),
        ("j2", "합병상대회사는 가장 최근 사업연도에 순손실을 냈는가?", "rbsnfdtl_nic<0", "칸"),
        ("j3", "합병상대회사의 가장 최근 사업연도 부채총계는 자본총계보다 큰가?", "rbsnfdtl_tdbt>rbsnfdtl_teqt", "칸"),
    ],
    "otcprStkInvscrInhDecsn": [
        ("j1", "이 회사는 이번에 사들이기 전에도 그 회사(발행회사) 주식을 들고 있었는가?", "atinh_owstkcnt>inhdtl_stkcnt", "칸"),
        ("j2", Q_CASH, "아니오", "상수"),
        ("j3", "사들인 뒤 그 회사 지분을 절반(50%)보다 많이 갖게 되는가?", "atinh_eqrt>50", "칸"),
    ],
    "majorstock": [
        ("j1", "보고자 쪽이 들고 있는 주식 등의 수는 직전 보고 때보다 늘었는가?", "stkqy_irds>0 (신규 보고는 뺌)", "칸"),
        ("j2", "이번 보고 시점에 보고자 쪽 보유 비율은 5% 이상인가?", "stkrt>=5", "칸"),
        ("j3", "보고자 쪽 보유 비율은 직전 보고 때보다 1%p 이상 달라졌는가?", "|stkrt_irds|>=1 (신규 보고는 뺌)", "칸"),
    ],
    "elestock": [
        ("j1", "보고한 사람이 들고 있는 이 회사 주식 등의 수는 직전 보고 때보다 늘었는가?", "sp_stock_lmp_irds_cnt>0 (신규 보고는 뺌)", "칸"),
        ("j2", "보고한 사람은 이 회사의 등기임원인가?", "isu_exctv_rgist_at == 등기임원 (빈 칸 = 임원 아님 → 아니오)", "칸"),
        ("j3", "보고한 사람의 보유 비율은 10% 이상인가?", "sp_stock_lmp_rate>=10", "칸"),
    ],
}
EMPTY_MEANS_NONE = {"dp_m_otc", "aq_wtn_div_ostk", "eaq_ostk", "ctr_prc_atcc", "fdpp_op", "piic_fdpp_dtrp", "mgnstk_ostk_cnt",
                    "nstk_estk_cnt", "isu_exctv_rgist_at", "fric_nstk_ostk_cnt"}   # 빈 칸('-')이 '없음'을 뜻하는 칸(내가 정함)
SHAREHOLDER_PRIORITY = {"주주배정증자", "주주배정후 실권주 일반공모", "주주우선공모증자"}


def _d(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:]))


def j5_truth(kind: str, jid: str, rule: str, src: str, val: dict) -> tuple[str, str, str]:
    """→ (정답, 쓴 칸 값, 뺀 이유). val: 칸 → (정답 값, 상태)."""
    if src == "상수":
        return rule, "", ""

    def get(c):
        v, st = val.get(c, ("", "빈칸"))
        if st == "값":
            return v
        if st == "빈칸" and c in EMPTY_MEANS_NONE:
            return "0" if c != "isu_exctv_rgist_at" else ""
        return None

    def num(c):
        v = get(c)
        return None if v is None else Decimal(v)

    def yn(b):
        return "예" if b else "아니오"
    used = " · ".join(f"{c}={val.get(c, ('', '빈칸'))[0] or '∅'}" for c in sorted(set(re.findall(r"[a-z][a-z0-9_]+", rule))) if c in val)
    try:
        if rule == "dp_m_otc>0":
            ans = yn(num("dp_m_otc") > 0)
        elif rule.startswith("aq_wtn_div_ostk>0"):
            ans = yn(num("aq_wtn_div_ostk") > 0 or num("eaq_ostk") > 0)
        elif rule == "ctr_prc_atcc>0":
            ans = yn(num("ctr_prc_atcc") > 0)
        elif rule.startswith("days(ctr_pd_bfcc_bgd"):
            ans = yn((_d(get("ctr_pd_bfcc_edd")) - _d(get("ctr_pd_bfcc_bgd"))).days > 200)
        elif rule.startswith("nstk_ostk_cnt>0 또는"):
            a, b = num("nstk_ostk_cnt"), num("nstk_estk_cnt")
            if a is None:
                return "", used, "필요한 칸이 빔"
            ans = yn(a > 0 or (b or 0) > 0)
        elif rule == "fdpp_op>0":
            ans = yn(num("fdpp_op") > 0)
        elif rule.startswith("ic_mthn"):
            v = get("ic_mthn")
            if not v:
                return "", used, "필요한 칸이 빔"
            ans = yn(v in SHAREHOLDER_PRIORITY)
        elif rule == "nstk_ostk_cnt>0":
            ans = yn(num("nstk_ostk_cnt") > 0)
        elif rule == "nstk_ascnt_ps_ostk>=1":
            ans = yn(num("nstk_ascnt_ps_ostk") >= 1)
        elif rule.startswith("piic_nstk_ostk_cnt>0"):
            ans = yn(num("piic_nstk_ostk_cnt") > 0 or num("fric_nstk_ostk_cnt") > 0)
        elif rule == "fric_nstk_ostk_cnt>piic_nstk_ostk_cnt":
            ans = yn(num("fric_nstk_ostk_cnt") > num("piic_nstk_ostk_cnt"))
        elif rule == "piic_fdpp_dtrp>0":
            ans = yn(num("piic_fdpp_dtrp") > 0)
        elif rule == "atcr_tisstk_ostk>bfcr_tisstk_ostk":
            ans = yn(num("atcr_tisstk_ostk") > num("bfcr_tisstk_ostk"))
        elif rule == "atcr_cpt*2<bfcr_cpt":
            ans = yn(num("atcr_cpt") * 2 < num("bfcr_cpt"))
        elif rule == "cvisstk_cnt>0":
            ans = yn(num("cvisstk_cnt") > 0)
        elif rule == "nstk_isstk_cnt>0":
            ans = yn(num("nstk_isstk_cnt") > 0)
        elif rule == "bd_intr_sf>bd_intr_ex":
            ans = yn(num("bd_intr_sf") > num("bd_intr_ex"))
        elif rule == "mgnstk_ostk_cnt>0":
            ans = yn(num("mgnstk_ostk_cnt") > 0)
        elif rule == "rbsnfdtl_nic<0":
            ans = yn(num("rbsnfdtl_nic") < 0)
        elif rule == "rbsnfdtl_tdbt>rbsnfdtl_teqt":
            ans = yn(num("rbsnfdtl_tdbt") > num("rbsnfdtl_teqt"))
        elif rule == "atinh_owstkcnt>inhdtl_stkcnt":
            a, b = num("atinh_owstkcnt"), num("inhdtl_stkcnt")
            if a < b:
                return "", used, "양수 후 소유 < 양수 주식 수(칸끼리 어긋남)"
            ans = yn(a > b)
        elif rule == "atinh_eqrt>50":
            ans = yn(num("atinh_eqrt") > 50)
        elif rule.startswith("stkqy_irds>0"):
            if num("stkqy") == num("stkqy_irds"):
                return "", used, "신규 보고(직전 보고 없음)"
            ans = yn(num("stkqy_irds") > 0)
        elif rule == "stkrt>=5":
            ans = yn(num("stkrt") >= 5)
        elif rule.startswith("|stkrt_irds|>=1"):
            if num("stkqy") == num("stkqy_irds"):
                return "", used, "신규 보고(직전 보고 없음)"
            ans = yn(abs(num("stkrt_irds")) >= 1)
        elif rule.startswith("sp_stock_lmp_irds_cnt>0"):
            if num("sp_stock_lmp_cnt") == num("sp_stock_lmp_irds_cnt"):
                return "", used, "신규 보고(직전 보고 없음)"
            ans = yn(num("sp_stock_lmp_irds_cnt") > 0)
        elif rule.startswith("isu_exctv_rgist_at"):
            ans = yn(get("isu_exctv_rgist_at") == "등기임원")
        elif rule == "sp_stock_lmp_rate>=10":
            ans = yn(num("sp_stock_lmp_rate") >= 10)
        else:
            raise KeyError(rule)
    except (TypeError, AttributeError, InvalidOperation):
        return "", used, "필요한 칸이 빔"
    return ans, used, ""


def pick_cap(docs: pd.DataFrame) -> pd.DataFrame:
    rng = random.Random(SEED5)
    out = []
    for kind, g in docs.sort_values(["kind", "rcept_no"]).groupby("kind", sort=False):
        ids = sorted(g["rcept_no"])
        out += ids if len(ids) <= CAP_PER_KIND else sorted(rng.sample(ids, CAP_PER_KIND))
    return docs[docs["rcept_no"].isin(out)].sort_values(["kind", "rcept_no"])


def build():
    T5.mkdir(parents=True, exist_ok=True)
    docs = T3.load_docs()
    k = T3.key_a3()
    L = ["# 9편 실험 5단계 표본 — 깔때기", "", "`scripts/ep09_tasks5.py build` 가 센 값만 적는다(추정 없음). 입력은 3단계 표본 266건의 원문 zip 뿐 — 새 수집 없음.", ""]

    # C5
    d5, k5, Lc = c5_build(docs)
    d5.to_csv(T5 / "C5_문서.csv", index=False, encoding="utf-8-sig")
    k5.to_csv(T5 / "정답_C5.csv", index=False, encoding="utf-8-sig")
    L += Lc

    # S5 · J5 표본
    s = pick_cap(docs)
    s.to_csv(T5 / "S5J5_표본.csv", index=False, encoding="utf-8-sig")
    L += ["## S5 요약 · J5 판단과 근거 — 표본", "",
          f"- 3단계 표본 266건 → 종류마다 최대 {CAP_PER_KIND}건(시드 {SEED5}, 내가 정함) → **{len(s)}건**",
          f"- J5 는 문항을 만들지 않은 종류(타법인주식및출자증권양도결정 1건)를 뺌 → {int(s['kind'].isin(J5_BANK).sum())}건", "",
          "| 종류 | 3단계 표본 | 5단계 표본 | 그중 정정 공시 |", "|---|---:|---:|---:|"]
    for kind, g in docs.groupby("종류", sort=False):
        gs = s[s["종류"] == kind]
        L.append(f"| {kind} | {len(g)} | {len(gs)} | {int((gs['정정'] == '1').sum())} |")

    # S5 핵심 칸(숫자·날짜 값 칸, 숫자 0 은 뺌)
    tp = {(r.kind, r.칸): r.형 for r in pd.read_csv(EP09 / "sample_A_칸정의.csv", dtype=str, encoding="utf-8-sig").fillna("").itertuples(index=False)}
    ks = k[k["rcept_no"].isin(s["rcept_no"]) & (k["상태"] == "값")].copy()
    ks["형"] = [tp[(a, b)] for a, b in zip(ks["kind"], ks["칸"])]
    n_all = len(ks)
    n_enum = int((ks["형"] == "enum").sum())
    ks = ks[ks["형"] != "enum"]
    zero = ks["형"].eq("num") & ks["정답"].map(lambda v: Decimal(v) == 0)
    n_zero = int(zero.sum())
    ks = ks[~zero]
    ks[["kind", "rcept_no", "칸", "질문이름", "형", "단위", "정답"]].to_csv(T5 / "정답_S5_칸.csv", index=False, encoding="utf-8-sig")
    L += ["", "## S5 핵심 칸(3단계 정답표의 값 칸)", "",
          f"- 표본 {len(s)}건의 값 칸 {n_all} → 분류 칸 뺌 {n_enum} → 숫자 0 인 칸 뺌 {n_zero} → **{len(ks)}칸**(숫자 {int((ks['형'] == 'num').sum())} · 날짜 {int((ks['형'] == 'date').sum())})", ""]

    # J5 문항·정답
    val = {rcp: {r.칸: (r.정답, r.상태) for r in g.itertuples(index=False)} for rcp, g in k.groupby("rcept_no")}
    qrows, arows = [], []
    for kind, items in J5_BANK.items():
        for jid, q, rule, src in items:
            qrows.append({"kind": kind, "문항": jid, "질문": q, "규칙": rule, "출처": src})
    why = Counter()
    for r in s[s["kind"].isin(J5_BANK)].itertuples(index=False):
        for jid, q, rule, src in J5_BANK[r.kind]:
            ans, used, reason = j5_truth(r.kind, jid, rule, src, val[r.rcept_no])
            why[reason or "씀"] += 1
            arows.append({"kind": r.kind, "rcept_no": r.rcept_no, "문항": jid, "출처": src, "정답": ans, "쓴_칸": used, "뺀_이유": reason})
    pd.DataFrame(qrows).to_csv(T5 / "J5_질문.csv", index=False, encoding="utf-8-sig")
    a = pd.DataFrame(arows)
    a.to_csv(T5 / "정답_J5.csv", index=False, encoding="utf-8-sig")
    au = a[a["뺀_이유"] == ""]
    L += ["## J5 문항", "",
          f"- 문서 {a['rcept_no'].nunique()}건 × 3문항 = {len(a)} → 뺌 " + " · ".join(f"{k_} {v}" for k_, v in why.items() if k_ != "씀") + f" → **{len(au)}문항**",
          f"- 정답 분포: {dict(Counter(au['정답']))} · 출처: 상수 {int((au['출처'] == '상수').sum())} · 칸 {int((au['출처'] == '칸').sum())}", "",
          "| 종류 | 문항 | 출처 | 쓰는 문항 | 예 | 아니오 | 판단 불가 |", "|---|---|---|---:|---:|---:|---:|"]
    for (kind, jid), g in au.groupby(["kind", "문항"], sort=False):
        c = Counter(g["정답"])
        L.append(f"| {kind} | {jid} | {g['출처'].iloc[0]} | {len(g)} | {c['예']} | {c['아니오']} | {c['판단 불가']} |")

    # 재실행 표본(J5 Sonnet 60건)
    jdocs = sorted(au["rcept_no"].unique())
    rer = sorted(random.Random(SEED5 + 1).sample(jdocs, RERUN_N))
    (T5 / "재실행_J5.json").write_text(json.dumps(rer, ensure_ascii=False), encoding="utf-8")
    L += ["", f"- 재실행(J5 · Sonnet) 표본: J5 문서 {len(jdocs)}건 중 {RERUN_N}건(시드 {SEED5}+1)", ""]
    (T5 / "표본_깔때기_5단계.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    {"build": build}[sys.argv[1] if len(sys.argv) > 1 else "build"]()
