# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 공개판에서 새로 쓴 파일(원본 없음).
"""가짜 견본 작업 공간 만들기 — 모델·네트워크를 부르지 않는다. 지어낸 회사·값·제목만 쓴다(실제 상장사·공시·기사가 아니다).

왜 있나: 실제 자료(공시 원문·뉴스 제목·분봉 수익률)는 약관상 다시 나눠 줄 수 없어 싣지 않았다. 대신 같은 형식의 가짜 자료를
실험이 정한 표본 크기(예: 뉴스 7,000건 · 평가 3,000건 · 재실행 60건)를 채울 만큼 만들어, 표본 추출 → 과제 → (가짜 답) → 채점이
코드를 고치지 않고 끝까지 도는지 볼 수 있게 한다. 숫자는 아무 뜻이 없다.

만드는 것(자료 뿌리 아래 — 구조는 ep09_paths.py):
  _가짜_견본_작업공간.txt          표시 파일(이게 있는 폴더만 다시 만들거나 가짜 답을 쓴다)
  daily/_universe_20261104.csv     가짜 종목 154개(code = FK0001… , name = 견본…)
  disclosure/구조화/<엔드포인트>.csv  19종(값은 OpenDART 표기 그대로의 글자: "1,234,567" · "2026년 01월 02일" · "-")
  disclosure/원문/<날짜>/<접수번호>.zip  가짜 공시 원문(DART XML 꼴, 정정 공시 일부 · 정기보고서 4건)
  fnltt/재무_보고서별.csv           정기보고서 4건의 재무 값
  news/analysis_year/events.csv    가짜 뉴스 제목 약 1만 2천 줄 + 기사 뒤 5·30분 수익률
  news/analysis_year/prepost/ 아래 prepost_events.csv  기사 앞뒤 30분 가격 갈래(0~4, −1)
  news/lines/<날짜>.csv            기사 줄별 종목 코드

쓰기(이 폴더에서):
  python -X utf8 scripts/ep09_fake_data.py                 # 기본 자료 뿌리(data/)에 만든다. 비어 있지 않은데 표시 파일이 없으면 멈춘다
  python -X utf8 scripts/ep09_fake_data.py --samples sample_data   # 만든 뒤 파일마다 앞 몇 줄을 sample_data/ 에 견본으로 옮긴다
"""
from __future__ import annotations

import argparse
import io
import random
import shutil
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ep09_paths import DATA
import ep09_sample as S1
import ep09_tasks3 as T3

MARK = "_가짜_견본_작업공간.txt"
SEED = 20261118
RNG = random.Random(SEED)
A = ["가람", "나래", "다온", "라온", "마루", "바름", "새봄", "아름", "여울", "잔솔", "초롱", "타래", "파랑", "하랑", "온새"]
B = ["전자", "화학", "바이오", "건설", "식품", "소재", "에너지", "로봇", "제약", "기계"]
DORG = ["견본통신", "견본경제", "견본일보"]
EMPTY_KINDS = {"cmpDvDecsn", "bsnInhDecsn", "bsnTrfDecsn"}        # 원본 표본에도 없던 세 종류 — 원문 없는 줄만 둔다
ONE_DOC = {"otcprStkInvscrTrfDecsn"}                              # 원본 표본에서 1건뿐이던 종류
PER_KIND = 5


# ================================================================ 공통
def universe() -> pd.DataFrame:
    rows = [{"code": f"FK{i + 1:04d}", "name": f"견본{a}{b}"} for i, (a, b) in enumerate((a, b) for a in A for b in B)]
    rows += [{"code": f"FK900{i}", "name": f"견본정기{n}"} for i, n in enumerate(("하나", "두리", "세찬", "네모"), 1)]
    return pd.DataFrame(rows)


def rday(a: date, b: date) -> date:
    return a + timedelta(days=RNG.randrange((b - a).days + 1))


def kdate(d: date) -> str:
    return f"{d.year}년 {d.month:02d}월 {d.day:02d}일"


def comma(v: int) -> str:
    return f"{v:,}" if v >= 0 else f"-{-v:,}"


def value_for(kind: str, col: str, tp: str, unit: str, why: str, row: dict) -> str:
    if why.startswith(S1.R_EMPTY) and RNG.random() < 0.7:
        return "-"
    if "빈 칸 섞임" in why and RNG.random() < 0.25:
        return "-"
    if tp == "date":
        return kdate(rday(date(2025, 1, 2), date(2027, 12, 28)))
    if tp == "enum":
        opts = S1.ENUM_OPTS.get((kind, col), ["일반"])
        return RNG.choice(opts)
    sign = -1 if (why == S1.R_SIGN and RNG.random() < 0.45) else 1
    if unit == "원":
        if col in ("fv_ps", "piic_fv_ps"):
            return comma(RNG.choice([100, 200, 500, 1000, 5000]))
        if "주당" in why or col in ("cv_prc", "ex_prc", "dpstk_prc_ostk", "act_mktprcfl_cvprc_lwtrsprc"):
            return comma(RNG.randrange(1000, 90000, 5))
        return comma(sign * RNG.randrange(10 ** 8, 9 * 10 ** 11, 1000))
    if unit == "주":
        if why == S1.R_RATE:                                         # 1주당 배정 주식수
            return RNG.choice(["0.2", "0.5", "1", "2"])
        return comma(sign * RNG.randrange(10 ** 4, 5 * 10 ** 7))
    if unit == "%":
        return f"{RNG.uniform(0.01, 60):.2f}"
    if unit == "%p":
        x = RNG.uniform(0.01, 9.9) * (-1 if RNG.random() < 0.45 else 1)
        return f"{x:.2f}"
    if unit == "회차":
        return str(RNG.randrange(1, 40))
    if unit == "명":
        return str(RNG.randrange(0, 5))
    return str(RNG.randrange(1, 1000))


def fix_rules(kind: str, row: dict):
    """문항 규칙(5단계 J5)이 여러 갈래로 나오게 몇 칸을 맞춘다 — 신규 보고 · 양수 후 소유 ≥ 양수 주식 수."""
    if kind == "majorstock" and RNG.random() < 0.3:
        row["stkqy_irds"] = row["stkqy"]
    if kind == "elestock" and RNG.random() < 0.3:
        row["sp_stock_lmp_irds_cnt"] = row["sp_stock_lmp_cnt"]
    if kind == "otcprStkInvscrInhDecsn" and row.get("inhdtl_stkcnt", "-") != "-":
        n = int(row["inhdtl_stkcnt"].replace(",", ""))
        row["atinh_owstkcnt"] = comma(n + RNG.choice([0, RNG.randrange(1, 10 ** 6)]))


# ================================================================ 공시 원문(DART XML 꼴)
def xml_doc(title: str, corp: str, body_rows: list[tuple[str, str]], corr: list[tuple[str, str, str]] | None = None, extra: str = "") -> str:
    tr = "\n".join(f"<TR><TD>{i}. {lab}</TD><TE>{val}</TE></TR>" for i, (lab, val) in enumerate(body_rows, 1))
    c = ""
    if corr is not None:
        rows = "\n".join(f"<TR><TD>{lab}</TD><TD>{b}</TD><TD>{a}</TD><TD>오기 정정</TD></TR>" for lab, b, a in corr)
        c = ("<P>정정신고(보고)</P>\n<CORRECTION>\n<TABLE>\n<TR><TH>정정사항</TH><TH>정정 전</TH><TH>정정 후</TH><TH>정정사유</TH></TR>\n"
             f"{rows}\n</TABLE>\n</CORRECTION>\n")
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
            "<!-- 가짜 견본: 지어낸 회사와 값이다. 실제 공시가 아니다. -->\n"
            f"<DOCUMENT>\n<DOCUMENT-NAME>{title}</DOCUMENT-NAME>\n<COMPANY-NAME>{corp}</COMPANY-NAME>\n{c}<BODY>\n"
            f"<P>{title}</P>\n<P>회사명: {corp}</P>\n<P>문의 전화: 000-0000-0000 (가짜 번호 — 전화번호 가림 시험용)</P>\n"
            f"<TABLE>\n{tr}\n</TABLE>\n{extra}"
            "<P>기타 투자판단에 참고할 사항: 이 문서는 시험용으로 지어낸 것이며 실제 회사·거래와 관계없다.</P>\n"
            "<P>위 내용은 가짜 견본 생성기가 만든 표로, 칸 이름은 OpenDART 서식 표기를 따랐다.</P>\n"
            "</BODY>\n</DOCUMENT>\n")


def put_zip(rcp: str, xml: str):
    p = DATA / "disclosure" / "원문" / rcp[:8] / f"{rcp}.zip"
    p.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{rcp}.xml", xml.encode("utf-8"))
    p.write_bytes(buf.getvalue())


def build_disclosure(names: list[str]):
    seq = [0]

    def new_rcp(d: date) -> str:
        seq[0] += 1
        return f"{d:%Y%m%d}99{seq[0]:04d}"

    (ov_rcp, ov_col), (ov_val, _) = next(iter(T3.CORRECTION_OVERRIDE.items()))
    api = DATA / "disclosure" / "구조화"
    api.mkdir(parents=True, exist_ok=True)
    pool = list(names)
    for kind, fields in S1.FIELDS.items():
        cols = [c for c, *_ in fields]
        RNG.shuffle(pool)
        corps = pool[:PER_KIND + 1]
        n_doc = 0 if kind in EMPTY_KINDS else (1 if kind in ONE_DOC else PER_KIND)
        rows = []
        for j in range(n_doc + 1):                                    # 마지막 한 줄은 원문 zip 이 없는 줄
            d = rday(date(2025, 11, 4), date(2026, 10, 30))
            rcp = ov_rcp if (kind == "cvbdIsDecsn" and j == PER_KIND - 1) else new_rcp(d)
            row = {"rcept_no": rcp, "corp_cls": "Y", "corp_code": f"FAKE{seq[0]:04d}", "corp_name": corps[j]}
            for c, lab, tp, unit, why in fields:
                row[c] = value_for(kind, c, tp, unit, why, row)
            fix_rules(kind, row)
            if j == 0 and kind in ("tsstkAqDecsn", "crDecsn"):         # 해석불가 칸(값이 범위·글) 하나씩
                c0 = [c for c, _, tp, *_ in fields if tp == "date"][0]
                row[c0] = "미정(추후 확정 시 공시)"
            corr = None
            if rcp == ov_rcp:                                         # 정정 표에는 정정 후, 본표·구조화 값에는 정정 전이 남은 문서
                row[ov_col] = "2,500,000"
                corr = [("전환에 따라 발행할 주식 주식수", "2,500,000", f"{int(ov_val):,}"),
                        ("기타 투자판단에 참고할 사항", "내용 보완 전", "내용 보완")]
            elif j == 1 and n_doc >= 3:                               # 종류마다 정정 공시 하나: 구조화 = 정정 후 값
                ch = [(lab, c) for c, lab, tp, unit, why in fields if row[c] not in ("-",) and tp in ("num", "date")][:2]
                corr = []
                for lab, c in ch:
                    old = row[c]
                    if "년" in old:
                        old = kdate(rday(date(2025, 1, 2), date(2027, 12, 28)))
                    else:
                        v = old.replace(",", "")
                        old = comma(int(float(v) * 2) + 7) if "." not in v else f"{float(v) + 1.5:.2f}"
                    corr.append((lab, old, row[c]))
                corr.append(("정정사유 비고", "-", "-"))
                corr.append(("기타 투자판단에 참고할 사항", "변경 전 문구", "변경 후 문구"))
            rows.append(row)
            if j < n_doc:
                title = f"주요사항보고서({S1.KIND_NAME[kind]})" if kind not in ("majorstock", "elestock") else S1.KIND_NAME[kind]
                body = [(lab, row[c]) for c, lab, *_ in fields]
                body += [("이사회결의일 비고", "해당사항 없음"), ("공시책임자", "(이름 가림)")]
                put_zip(rcp, xml_doc(title, row["corp_name"], body, corr))
        pd.DataFrame(rows, columns=["rcept_no", "corp_cls", "corp_code", "corp_name"] + cols).to_csv(api / f"{kind}.csv", index=False, encoding="utf-8-sig")


def build_fnltt():
    rows = []
    prev = {"FY": "FY", "HY": "HY", "TQ": "TQ", "FQ": "FQ"}
    end = {"FY": "12-31", "HY": "06-30", "TQ": "09-30", "FQ": "03-31"}
    uni = universe().set_index("code")["name"]
    for rcp, code, year, rep in T3.H5_DOCS:
        body, extra = [], ""
        for y in (int(year), int(year) - 1):
            for scope in ("연결", "별도"):
                v = {"매출액_누적": RNG.randrange(10 ** 10, 9 * 10 ** 12, 1000), "영업이익_누적": RNG.randrange(-5 * 10 ** 10, 5 * 10 ** 11, 1000),
                     "순이익_누적": RNG.randrange(-5 * 10 ** 10, 4 * 10 ** 11, 1000)}
                rows.append({"종목코드": code, "회사명": uni[code], "연도": str(y), "보고서": prev[rep] if y != int(year) else rep, "연결": scope,
                             "통화": "KRW", "결산기준일": f"{y}-{end[rep]}", **v,
                             "매출액_코드": "ifrs-full_Revenue", "영업이익_코드": "dart_OperatingIncomeLoss", "순이익_코드": "ifrs-full_ProfitLoss"})
                per = "당기" if y == int(year) else "전기"
                body += [(f"{scope} {per} 매출액(원)", comma(v["매출액_누적"])), (f"{scope} {per} 영업이익(원)", comma(v["영업이익_누적"])),
                         (f"{scope} {per} 당기순이익(원)", comma(v["순이익_누적"]))]
        extra = "<P>재무에 관한 사항 — 요약재무정보(단위: 원). 가짜 견본 값.</P>\n"
        put_zip(rcp, xml_doc(f"{'사업' if rep == 'FY' else '반기' if rep == 'HY' else '분기'}보고서 ({year}.{end[rep][:2]})", uni[code], body, None, extra))
    p = DATA / "fnltt" / "재무_보고서별.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")


# ================================================================ 뉴스
NOUN = ["신제품", "시제품", "공급 계약", "수주", "증설", "특허", "협약", "실적", "배당", "연구 성과", "해외 진출", "임상 결과", "설비 투자", "자사주"]
VERB = ["발표", "공개", "추진", "확대", "체결", "검토", "완료", "착수"]
TAG = ["단독", "속보", "기획", "종합"]
DISC = ["단일판매ㆍ공급계약체결", "자기주식취득결정", "유상증자결정", "전환사채권발행결정", "주식등의대량보유상황보고서", "무상증자결정"]
LIST_TITLES = ["[목록] 견본시장 오름폭 상위 종목", "[목록] 견본시장 거래량 상위 종목"]


def title_of(kind: str, name: str) -> str:
    r = RNG.random()
    if kind != "공시 피드" and r < 0.02:
        return RNG.choice(LIST_TITLES)
    if kind == "일반 기사":
        t = f"{name}, {RNG.choice(NOUN)} {RNG.choice(VERB)}"
        if RNG.random() < 0.4:
            t = f"[{RNG.choice(TAG)}] " + t
        if RNG.random() < 0.5:
            t += f"… {RNG.randrange(5, 900)}억 규모"
        return t
    if kind == "시세 중계":
        x = RNG.uniform(1, 29.9)
        return RNG.choice([f"{name}, {x:.1f}% 상승 거래 중", f"{name}, {x:.1f}% 하락 거래 중", f"{name} 급등세 {x:.2f}%↑", f"[시세] {name} {x:.2f}% 오름"])
    return f"[공시] {name} {RNG.choice(DISC)}"


def weekdays(a: date, b: date):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def build_news(uni: pd.DataFrame):
    codes = list(uni["code"][:150])
    nm = dict(zip(uni["code"], uni["name"]))
    ev, lines, seq = [], {}, 0
    for d in weekdays(date(2025, 11, 4), date(2026, 11, 10)):
        ds = f"{d:%Y%m%d}"
        if ds <= "20260531":
            plan = {"일반 기사": 27, "시세 중계": 4, "공시 피드": 4}
        elif ds < "20260701":
            plan = {"일반 기사": 15, "시세 중계": 5, "공시 피드": 5}
        else:
            plan = {"일반 기사": 41, "시세 중계": 16, "공시 피드": 10}
        day_rows = []
        for kind, n in plan.items():
            for _ in range(n):
                seq += 1
                code = "FK0999" if RNG.random() < 0.01 else RNG.choice(codes)   # FK0999 = 이름표에 없는 종목(뺌 확인용)
                m = RNG.randrange(546, 901)
                tm = f"{m // 60:02d}{m % 60:02d}{RNG.randrange(60):02d}"
                t = title_of(kind, nm.get(code, "견본무명"))
                p30 = 0.0 if RNG.random() < 0.05 else RNG.gauss(0, 0.012)
                p5 = 0.0 if RNG.random() < 0.08 else RNG.gauss(0, 0.006)
                day_rows.append({"use": "1" if RNG.random() > 0.02 else "0", "day": ds, "tm": tm, "srno": f"{ds}{tm}{seq:04d}", "code": code,
                                 "kind": kind, "title": t, "mk": RNG.choice(["유", "코"]), "dorg": RNG.choice(DORG),
                                 "pre5": f"{RNG.gauss(0, 0.006):.6f}", "bar0": f"{RNG.gauss(0, 0.003):.6f}",
                                 "post5": "0" if p5 == 0 else f"{p5:.6f}", "post30": "0" if p30 == 0 else f"{p30:.6f}"})
        if day_rows and RNG.random() < 0.3:                              # 같은 기사가 다시 전송된 줄(같은 날·종목·제목)
            r0 = dict(day_rows[0])
            seq += 1
            r0["srno"] = f"{ds}{r0['tm']}{seq:04d}"
            day_rows.append(r0)
        ev += day_rows
        lines[ds] = [{"srno": r["srno"], "codes": r["code"] + ("|" + RNG.choice(codes) if RNG.random() < 0.1 else ""), "title": r["title"]} for r in day_rows]
    e = pd.DataFrame(ev)
    p = DATA / "news" / "analysis_year"
    (p / "prepost").mkdir(parents=True, exist_ok=True)
    e.to_csv(p / "events.csv", index=False, encoding="utf-8-sig")
    ld = DATA / "news" / "lines"
    ld.mkdir(parents=True, exist_ok=True)
    for ds, rs in lines.items():
        pd.DataFrame(rs).to_csv(ld / f"{ds}.csv", index=False, encoding="utf-8-sig")
    # 기사 앞뒤 30분 갈래(0 둘 다 없음 · 1 앞만 · 2 뒤만 · 3 이어짐 · 4 되돌림 · −1 계산 못 함)
    u = e[e["use"] == "1"].copy()
    rows = []
    seen = {}
    for r in u.itertuples(index=False):
        m = int(r.tm[:2]) * 60 + int(r.tm[2:4])
        k = (r.day, r.code)
        bd = seen.get(k, 0)
        seen[k] = bd + 1
        if m < 571:
            c_raw = c_ex = -1
        else:
            c_raw = RNG.choices([0, 1, 2, 3, 4], [0.66, 0.16, 0.08, 0.04, 0.06])[0]
            c_ex = c_raw if RNG.random() < 0.8 else RNG.choices([0, 1, 2, 3, 4], [0.66, 0.16, 0.08, 0.04, 0.06])[0]
        rows.append({"day": r.day, "tm": r.tm, "m": m, "srno": r.srno, "code": r.code, "dorg": r.dorg, "kind": r.kind,
                     "type": RNG.choice(["일반", "속보", "목록", "단독"]), "period": "앞 절반" if r.day <= "20260508" else "뒤 절반",
                     "before_day": bd, "tv20": round(RNG.lognormvariate(22, 1.5), 0),
                     "pre30": round(RNG.gauss(0, 0.012), 6), "post30": float(r.post30), "ex_pre30": round(RNG.gauss(0, 0.012), 6),
                     "ex_post30": round(float(r.post30) - RNG.gauss(0, 0.002), 6), "q4_30분_원_상대상위10": c_raw, "q4_30분_초과_상대상위10": c_ex})
    pd.DataFrame(rows).to_csv(p / "prepost" / "prepost_events.csv", index=False, encoding="utf-8-sig")
    return len(e), len(rows)


# ================================================================ 견본 옮기기
def write_samples(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    note = ["# 가짜 견본 — 형식만 같은 지어낸 자료", "",
            "이 폴더의 파일은 `scripts/ep09_fake_data.py` 가 만든 가짜 작업 공간에서 앞 몇 줄씩 옮긴 것이다.",
            "회사 이름(견본…) · 종목 코드(FK…) · 접수번호(…99xxxx) · 뉴스 제목 · 수익률 · 공시 값은 모두 지어냈다. 실제 상장사·공시·기사가 아니다.",
            "실험을 끝까지 돌려 보려면 이 견본이 아니라 `python -X utf8 scripts/ep09_offline_check.py` 를 쓴다(같은 생성기로 표본 크기를 채운 가짜 작업 공간을 만든다).", "",
            "견본 폴더 안의 하위 폴더는 자료 뿌리(data/) 아래 자리와 같다. 원문만 zip 대신 풀어 둔 xml 이다(`disclosure/원문_xml/`).", "",
            "| 파일 | 원래 자리(자료 뿌리 data/ 아래 폴더) | 뜻 |", "|---|---|---|"]
    picks = [("daily/_universe_20261104.csv", 8, "종목 코드 → 이름"),
             ("disclosure/구조화/tsstkAqDecsn.csv", 4, "OpenDART 구조화 API 결과(자기주식 취득 결정) — 정답지"),
             ("disclosure/구조화/majorstock.csv", 4, "OpenDART 지분공시(대량보유) 구조화 결과 — 정답지"),
             ("fnltt/재무_보고서별.csv", 5, "정기보고서 재무 값(H5 정답)"),
             ("news/analysis_year/events.csv", 8, "뉴스 제목 + 기사 뒤 5·30분 수익률"),
             ("news/analysis_year/prepost/" + "prepost_events.csv", 8, "기사 앞뒤 30분 가격 갈래"),
             ("news/lines/20251104.csv", 5, "기사 줄별 종목 코드(4단계 특징)")]
    for rel, n, what in picks:
        src = DATA / rel
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        txt = src.read_text(encoding="utf-8-sig").splitlines()[:n + 1]
        dst.write_text("\n".join(txt) + "\n", encoding="utf-8-sig")
        note.append(f"| `{Path(rel).name}` | `data/{Path(rel).parent.as_posix()}/` | {what} |")
    d = pd.read_csv(DATA / "disclosure" / "구조화" / "tsstkAqDecsn.csv", dtype=str)
    for rcp in list(d["rcept_no"])[:2]:
        z = DATA / "disclosure" / "원문" / rcp[:8] / f"{rcp}.zip"
        if z.exists():
            with zipfile.ZipFile(z) as zz:
                x = zz.read(sorted(zz.namelist())[0]).decode("utf-8")
            dst = out / "disclosure" / "원문_xml" / f"{rcp}.xml"
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(x, encoding="utf-8")
            note.append(f"| `disclosure/원문_xml/{rcp}.xml` | `data/disclosure/원문/{rcp[:8]}/` 의 `{rcp}.zip` 안 문서 | 공시 원문(DART XML 꼴). 실제로는 zip 으로 둔다 |")
    note.append("")
    (out / "가짜_견본_안내.md").write_text("\n".join(note) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="가짜 견본 작업 공간 만들기(모델·네트워크 호출 없음)")
    ap.add_argument("--samples", default="", help="만든 뒤 앞 몇 줄씩을 이 폴더에 견본으로 옮김")
    a = ap.parse_args()
    if DATA.exists() and any(DATA.iterdir()):
        if not (DATA / MARK).exists():
            sys.exit(f"{DATA} 가 비어 있지 않고 가짜 견본 표시 파일이 없다 — 실제 자료일 수 있어 멈춤(--data 로 다른 폴더를 주거나 비운 뒤 다시)")
        # 표시 파일이 있어도, 가짜 규칙(접수번호 9~10번째 글자가 99)을 벗어난 원문 zip 이 하나라도 있으면 실제 자료가 섞인 것 → 지우지 않는다
        real = [z.name for z in DATA.rglob("*.zip") if z.stem[:14].isdigit() and z.stem[8:10] != "99"]
        if real:
            sys.exit(f"{DATA} 에 가짜 견본이 아닌 원문 zip 이 있다(예: {real[0]}) — 실제 자료를 지우지 않으려고 멈춤. 가짜 검사는 --data 로 다른 폴더에서")
        shutil.rmtree(DATA)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / MARK).write_text("이 폴더는 scripts/ep09_fake_data.py 가 만든 가짜 견본 작업 공간이다. 지어낸 자료만 들어 있다.\n", encoding="utf-8")
    uni = universe()
    p = DATA / "daily" / "_universe_20261104.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    uni.to_csv(p, index=False, encoding="utf-8-sig")
    build_disclosure(list(uni["name"][:150]))
    build_fnltt()
    n_ev, n_pp = build_news(uni)
    n_zip = sum(1 for _ in (DATA / "disclosure" / "원문").glob("*/*.zip"))
    print(f"가짜 견본 작업 공간: {DATA}")
    print(f"  종목 {len(uni)} · 원문 zip {n_zip} · 뉴스 {n_ev:,}줄 · 앞뒤 갈래 {n_pp:,}줄")
    if a.samples:
        write_samples(Path(a.samples))
        print("  견본 옮김:", Path(a.samples).resolve())


if __name__ == "__main__":
    main()
