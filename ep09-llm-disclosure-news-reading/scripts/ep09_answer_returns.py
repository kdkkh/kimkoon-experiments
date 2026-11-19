# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 3단계 B — 모델의 답(오름/내림/모름)별 실제 수익률 (2026-11-17, 사전 등록 뒤 추가한 탐색 집계).

결정적 코드만 — 모델·API·웹을 부르지 않는다. 받아 둔 파일만 읽는다.
읽는 것(고치지 않음)
  data/ep09/채점3/<판>_B_건.csv        ep09_grade3.py 가 낸 건별 채점(답 · post5 · post30 · 제목_반복수 · 갈래 · 구간 · 부분)
  data/ep09/sample_B3.csv               3단계 표본 7,000건
  data/news/analysis_year/events.csv    가격 반응 원자료(이 폴더 밖에서 만든 것 — README) — 수익률 대조용
만드는 것(돌릴 때마다 통째로 다시 씀)
  data/ep09/채점3/답별_수익률.md · 답별_수익률.csv

정의(다른 스크립트와 같게 — 근거는 각 파일)
  - 수익률(events.csv 를 만든 계산 — 이 폴더 밖): 기사 분 m 의 봉은 넣지 않음. post5 = C(m+5)/C(m)-1, post30 = C(m+30)/C(m)-1.
    C(x) = x 분까지 마지막 체결 봉 종가(정규장). 수수료·세금·호가 차이 없음.
  - 답 정규화: ep09_grade.py norm_b. 답이 온 건만(ep09_grade3.py grade_b_all).
  - 적중 판정의 0 처리: 수익률 0 은 적중률 분모에서 뺀다(ep09_grade.py grade_b). 이 집계의 평균·중앙값에는 0 을 그대로 넣는다.
  - 목록형 제목: 제목_반복수(use==1 전체에서 같은 글자 제목 수) ≥ 10 (ep09_grade.py TEMPLATE_MIN, ep09_tasks3.py build_b3).
  - 95% 구간: 평균은 부트스트랩 백분위(건 단위 복원 추출, 5,000회, 고정 시드). 차이는 두 묶음을 따로 복원 추출해 평균 차.
    CSV 에는 t 구간(평균) · 웰치 t 구간(차이)도 함께 적는다.

쓰기(이 폴더에서):  python -X utf8 scripts/ep09_answer_returns.py
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
EP09 = DATA / "ep09"
OUT = EP09 / "채점3"
EVENTS = DATA / "news" / "analysis_year" / "events.csv"
SEED = 20261117
NBOOT = 5000
TEMPLATE_MIN = 10
HORIZONS = (("post5", "5분"), ("post30", "30분"))
ANS = ("오름", "내림", "모름")

SETS = [  # (이름, 파일, 설명)
    ("B-주 Sonnet", "B주_sonnet", "Sonnet · 모름 허용 · 7,000건"),
    ("B-주 Sonnet(부분 2,000)", "B부분_sonnet", "B-주에서 부분 표본 2,000건만(B-강제·세 급과 같은 건)"),
    ("B-강제 Sonnet", "B강제_sonnet", "Sonnet · 모름 없이 · 부분 2,000건"),
    ("Haiku", "B부분_haiku", "Haiku · 모름 허용 · 부분 2,000건(답 온 건만)"),
    ("Opus", "B부분_opus", "Opus · 모름 허용 · 부분 2,000건"),
]

# 다시 센 값과 맞춰 볼 수. 원본은 3단계 보고서의 수를 판마다 적었다. 공개판은 영상에 나간 수만 남겼다
# (영상: Sonnet 7,000건 · 답 오름 2,854 / 내림 534 / 모름 3,612 · 30분 적중 1,445/3,119). 없는 항목은 대조하지 않는다.
REPORT = {
    "B-주 Sonnet": {"rows": 7000, "답": (2854, 534, 3612), "30분": {"전체": (1445, 3119)}},
}

RNG = np.random.default_rng(SEED)


def read_csv(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, dtype=str, encoding="utf-8-sig", keep_default_na=False)


# ================================================================ 통계
def boot_means(x: np.ndarray) -> np.ndarray:
    n = len(x)
    out = np.empty(NBOOT)
    step = max(1, 2_000_000 // max(n, 1))
    for s in range(0, NBOOT, step):
        e = min(NBOOT, s + step)
        out[s:e] = x[RNG.integers(0, n, (e - s, n))].mean(axis=1)
    return out


def ci_boot(x: np.ndarray):
    if len(x) < 2:
        return (math.nan, math.nan)
    b = boot_means(x)
    return tuple(np.percentile(b, [2.5, 97.5]))


def ci_t(x: np.ndarray):
    n = len(x)
    if n < 2:
        return (math.nan, math.nan)
    m, se = x.mean(), x.std(ddof=1) / math.sqrt(n)
    q = stats.t.ppf(0.975, n - 1)
    return (m - q * se, m + q * se)


def diff_ci(a: np.ndarray, b: np.ndarray):
    """→ 차, 부트스트랩 구간, 웰치 t 구간."""
    if len(a) < 2 or len(b) < 2:
        return math.nan, (math.nan, math.nan), (math.nan, math.nan)
    d = a.mean() - b.mean()
    bd = boot_means(a) - boot_means(b)
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    se = math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1)) if se > 0 else 1
    q = stats.t.ppf(0.975, df)
    return d, tuple(np.percentile(bd, [2.5, 97.5])), (d - q * se, d + q * se)


def describe(x: np.ndarray) -> dict:
    n = len(x)
    if n == 0:
        return {"n": 0}
    lo, hi = np.quantile(x, [0.01, 0.99])
    bl, bh = ci_boot(x)
    tl, th = ci_t(x)
    return {"n": n, "평균": x.mean(), "중앙값": float(np.median(x)), "표준편차": x.std(ddof=1) if n > 1 else math.nan,
            "Q1": float(np.quantile(x, 0.25)), "Q3": float(np.quantile(x, 0.75)),
            "오른비율": (x > 0).mean(), "내린비율": (x < 0).mean(), "0비율": (x == 0).mean(),
            "평균_boot_lo": bl, "평균_boot_hi": bh, "평균_t_lo": tl, "평균_t_hi": th,
            "위아래1%자른평균": x[(x >= lo) & (x <= hi)].mean()}


def concentration(g: pd.DataFrame, h: str) -> dict:
    x = g[h].to_numpy()
    if len(x) == 0:
        return {}
    cnt = g["code"].value_counts()
    by_code = g.groupby("code")[h].sum()
    tot = x.sum()
    sign = 1 if tot >= 0 else -1
    top = (by_code * sign).idxmax()
    rest = g.loc[g["code"] != top, h]
    lo, hi = np.quantile(x, [0.01, 0.99])
    return {"건수": len(x), "종목수": int(cnt.size), "건수최다종목": cnt.index[0], "건수최다몫": cnt.iloc[0] / len(x),
            "상위5종목건수몫": cnt.iloc[:5].sum() / len(x), "합기여최대종목": top,
            "합기여최대몫": by_code[top] / tot if tot else math.nan, "그종목뺀평균": rest.mean() if len(rest) else math.nan,
            "위아래1%자른평균": x[(x >= lo) & (x <= hi)].mean(), "평균": x.mean(),
            "종목같은무게평균": g.groupby("code")[h].mean().mean()}


# ================================================================ 자료
def load_set(fname: str, ev: pd.DataFrame, sample: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    k = read_csv(OUT / f"{fname}_B_건.csv")
    chk = {"건별 줄": len(k)}
    k = k[k["답있음"] == "1"].copy()
    chk["답 온 줄"] = len(k)
    # 표본과 대조(같은 id 의 수익률 글자가 같은가)
    sm = sample.set_index("id")
    inS = k["id"].isin(sm.index)
    chk["표본에 있음"] = int(inS.sum())
    same = 0
    for h in ("post5", "post30"):
        same += int((k.loc[inS, h].to_numpy() == sm.loc[k.loc[inS, "id"], h].to_numpy()).sum())
    chk["표본과 수익률 글자 같음(5분+30분 칸)"] = f"{same}/{2 * int(inS.sum())}"
    # events.csv 와 대조(키 = srno_code, use==1)
    m = k[["id", "post5", "post30"]].merge(ev, on="id", how="left", suffixes=("", "_ev"), indicator=True)
    chk["events.csv 에 붙음"] = int((m["_merge"] == "both").sum())
    chk["events.csv 에 못 붙음"] = int((m["_merge"] != "both").sum())
    ok = m["_merge"] == "both"
    diff = 0
    for h in ("post5", "post30"):
        a = pd.to_numeric(m.loc[ok, h]).to_numpy()
        b = pd.to_numeric(m.loc[ok, h + "_ev"]).to_numpy()
        diff = max(diff, float(np.nanmax(np.abs(a - b))) if len(a) else 0.0)
    chk["events.csv 와 수익률 최대 차"] = diff
    chk["events 쪽 use≠1"] = int((m.loc[ok, "use"] != "1").sum())
    for h in ("post5", "post30"):
        k[h] = pd.to_numeric(k[h]) * 100          # % 로
    k["목록형"] = pd.to_numeric(k["제목_반복수"], errors="coerce").fillna(0) >= TEMPLATE_MIN
    return k, chk


def groups_of(k: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    out = []
    base = [("일반 기사 · 앞", (k["갈래"] == "일반 기사") & (k["구간"] == "앞")),
            ("일반 기사 · 뒤", (k["갈래"] == "일반 기사") & (k["구간"] == "뒤")),
            ("시세 중계 · 뒤", (k["갈래"] == "시세 중계") & (k["구간"] == "뒤")),
            ("전체", pd.Series(True, index=k.index))]
    for lab, msk in base:
        if msk.sum():
            out.append((lab, k[msk]))
    for lab, msk in base:
        mm = msk & ~k["목록형"]
        if mm.sum() and mm.sum() < msk.sum():
            out.append((lab + " (목록형 뺌)", k[mm]))
    return out


# ================================================================ 출력 도우미
def f3(v):
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:+.3f}"


def f2(v):
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.2f}"


def pc(v):
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{100 * v:.1f}%"


def ci(lo, hi):
    if any(isinstance(v, float) and math.isnan(v) for v in (lo, hi)):
        return "–"
    tag = "0 포함" if lo <= 0 <= hi else "0 벗어남"
    return f"[{lo:+.3f} ~ {hi:+.3f}] {tag}"


def main():
    sample = read_csv(EP09 / "sample_B3.csv")
    ev = read_csv(EVENTS)[["srno", "code", "use", "post5", "post30"]]
    ev["id"] = ev["srno"] + "_" + ev["code"]
    ev_dup = int(ev["id"].duplicated().sum())
    ev = ev.drop_duplicates("id", keep="first")[["id", "use", "post5", "post30"]]

    rows_csv = []
    L = ["# 9편 실험 3단계 B — 모델의 답별 실제 수익률", "",
         "> **사전 등록 뒤 추가한 탐색 집계**(2026-11-17). 사전 등록(3단계)의 B 지표는 적중률뿐이고, 답별 수익률은 등록에 없다.",
         "> 판 다섯 × 묶음 여러 개 × 5분·30분을 함께 보므로, 구간이 0 을 벗어난 줄이 있어도 해석하지 않는다. 숫자와 '0 포함 / 0 벗어남'만 적는다.", "",
         "만든 것: `scripts/ep09_answer_returns.py`(인자 없이 재실행, 모델·API·웹 호출 없음). 건마다 값은 `답별_수익률.csv`.", "",
         "## 0. 조건", "",
         "- **수익률 정의**(events.csv 를 만든 계산 — 이 폴더 밖): 기사 분 m(증권사 뉴스 API 의 기사 시각 data_tm 의 시·분). **기사 분 봉은 넣지 않음.** "
         "5분 = C(m+5)/C(m) − 1, 30분 = C(m+30)/C(m) − 1, C(x) = x 분까지 마지막 체결 봉 종가(정규장 09:00 이후 봉, 거래량 0 봉 뺌, 빈 분 = 값 그대로). "
         "**수수료·세금·호가 차이(스프레드)·슬리피지 전.** 그 가격에 살 수 있었다는 뜻이 아니다.",
         "- 주 표본 조건(use==1): 09:06 ≤ m ≤ 15:00, 창 [m−6, m+30] 이 받은 구간 안, 기사 앞 10분 안 체결 있음, 가격 단위 섞임 의심 뺌. 종목별 첫 기사(30분 안 앞 기사 없음).",
         "- 단위: **%**(수익률 × 100). 평균·중앙값·사분위에는 **수익률 0 을 그대로 넣는다**(적중률은 0 을 분모에서 뺐다 — `ep09_grade.py` grade_b).",
         "- 답: `ep09_grade.py` norm_b 로 정규화한 답, **답이 온 건만**(`ep09_grade3.py` grade_b_all). 형식 밖 답은 모든 판에서 0건.",
         "- 목록형 제목 = use==1 전체에서 같은 글자 제목이 10줄 이상(`제목_반복수` ≥ 10, 보고서·채점과 같은 기준).",
         f"- **95% 구간 = 부트스트랩 백분위**(건 단위 복원 추출 {NBOOT:,}회, 시드 {SEED}). 차이는 두 묶음을 따로 복원 추출한 평균 차. "
         "같은 종목·같은 날 건이 묶여 있어도 건을 독립으로 보고 뽑았다 → 구간이 실제보다 좁을 수 있다(추정). CSV 에 t 구간·웰치 t 구간도 있다.",
         "- 판: B-주 Sonnet 7,000건 / B-주의 부분 2,000건(Sonnet, B-강제·세 급과 같은 건 — 비교용) / B-강제 Sonnet 2,000건 / Haiku 2,000건(답 온 1,851건) / Opus 2,000건. "
         "부분 2,000건은 일반 기사 앞·뒤만이라 시세 중계 줄이 없다. Haiku 깨진 묶음 보조판(`B부분_haiku_깨진묶음포함`)은 넣지 않았다.", ""]

    data, chks = {}, {}
    for name, fname, _ in SETS:
        k, chk = load_set(fname, ev, sample)
        data[name], chks[name] = k, chk

    # ================================================ 대조
    L += ["## 1. 자료 붙이기 · 영상에 나간 수와 대조", "",
          f"건별 CSV 에 post5·post30 열이 이미 있어(채점 때 표본에서 옮긴 값) 그대로 썼다. 같은 값인지 표본·events.csv 와 다시 맞췄다(키 = `srno_code`; events.csv 의 같은 키 중복 {ev_dup}줄 — 첫 줄만 씀).", "",
          "| 판 | 건별 줄 | 답 온 줄 | 표본에 있음 | 표본과 수익률 글자 같음 | events.csv 붙음 / 못 붙음 | events 와 최대 차 | events 쪽 use≠1 |",
          "|---|---:|---:|---:|---|---|---:|---:|"]
    for name, *_ in SETS:
        c = chks[name]
        L.append(f"| {name} | {c['건별 줄']:,} | {c['답 온 줄']:,} | {c['표본에 있음']:,} | {c['표본과 수익률 글자 같음(5분+30분 칸)']} | "
                 f"{c['events.csv 에 붙음']:,} / {c['events.csv 에 못 붙음']} | {c['events.csv 와 수익률 최대 차']:.1e} | {c['events 쪽 use≠1']} |")
    L += ["", "| 판 | 항목 | 보고서 | 다시 셈 | 같음 |", "|---|---|---|---|---|"]
    mism = []
    for name, *_ in SETS:
        k, rep = data[name], REPORT.get(name)
        if not rep:
            continue
        cnt = tuple(int((k["답"] == a).sum()) for a in ANS)
        items = [("답 온 건", str(rep["rows"]), str(len(k))), ("답 오름/내림/모름", "/".join(map(str, rep["답"])), "/".join(map(str, cnt)))]
        for lab_h, h in (("30분", "post30"), ("5분", "post5")):
            for grp, (hit, said) in rep.get(lab_h, {}).items():
                g = k if grp == "전체" else k[(k["갈래"] + " · " + k["구간"]) == grp]
                s = g[g["답"].isin(["오름", "내림"]) & (g[h] != 0)]
                hh = int(((s["답"] == "오름") == (s[h] > 0)).sum())
                items.append((f"{lab_h} 적중 · {grp}", f"{hit}/{said}", f"{hh}/{len(s)}"))
        for it, a, b in items:
            ok = a == b
            if not ok:
                mism.append((name, it, a, b))
            L.append(f"| {name} | {it} | {a} | {b} | {'같음' if ok else '**다름**'} |")
    L += ["", f"- 대조 결과: 다른 줄 {len(mism)}개." + ("" if not mism else " " + "; ".join(f"{n} {i} 보고서 {a} · 다시 셈 {b}" for n, i, a, b in mism)), ""]
    # 부분 판끼리 답이 같은 건 위에 있는가(B-주와 부분 Sonnet)
    a, b = data["B-주 Sonnet"].set_index("id")["답"], data["B-주 Sonnet(부분 2,000)"].set_index("id")["답"]
    L += [f"- B-주 Sonnet 과 부분 2,000건 판의 같은 id 답이 같은 건: {int((a.loc[b.index] == b).sum())}/{len(b)}(같은 실행 기록에서 나온 판).", ""]

    # ================================================ 집계
    sec = 2
    main_rows = []
    for name, fname, desc in SETS:
        k = data[name]
        L += [f"## {sec}. {name} — {desc}", ""]
        sec += 1
        for h, lab in HORIZONS:
            L += [f"### {name} · 기사 뒤 {lab}", "",
                  "기준선(답과 무관, 그 묶음 전체) · 답별 분포. 단위 %.", "",
                  "| 묶음 | 답 | 건 | 평균 | 평균 95% 구간(부트스트랩) | 중앙값 | 표준편차 | Q1 ~ Q3 | 오른 / 내린 / 0 | 위아래 1% 자른 평균 |",
                  "|---|---|---:|---:|---|---:|---:|---|---|---:|"]
            diffs = []
            for grp, g in groups_of(k):
                parts = [("(기준선) 전체", g)] + [(a, g[g["답"] == a]) for a in ANS]
                got = {}                                   # 주 표가 같은 값(같은 부트스트랩)을 다시 쓰게
                for a, gg in parts:
                    x = gg[h].to_numpy()
                    d = describe(x)
                    got[a] = d
                    row = {"판": name, "묶음": grp, "기간": lab, "답": a, **d}
                    rows_csv.append(row)
                    if d["n"] == 0:
                        L.append(f"| {grp} | {a} | 0 | – | – | – | – | – | – | – |")
                        continue
                    L.append(f"| {grp} | {a} | {d['n']:,} | {f3(d['평균'])} | {ci(d['평균_boot_lo'], d['평균_boot_hi'])} | {f3(d['중앙값'])} | {f2(d['표준편차'])} | "
                             f"{f3(d['Q1'])} ~ {f3(d['Q3'])} | {pc(d['오른비율'])} / {pc(d['내린비율'])} / {pc(d['0비율'])} | {f3(d['위아래1%자른평균'])} |")
                xu, xd, xk = (g[g["답"] == a][h].to_numpy() for a in ANS)
                xs = g[g["답"].isin(["오름", "내림"])][h].to_numpy()
                for lab_d, p, q in (("오름 − 내림", xu, xd), ("오름 − 모름", xu, xk)):
                    dd, bci, tci = diff_ci(p, q)
                    got[lab_d] = (dd, bci, tci)
                    diffs.append((grp, lab_d, f"{len(p):,} / {len(q):,}", dd, bci))
                    rows_csv.append({"판": name, "묶음": grp, "기간": lab, "답": lab_d, "n": len(p), "n2": len(q), "평균": dd,
                                     "평균_boot_lo": bci[0], "평균_boot_hi": bci[1], "평균_t_lo": tci[0], "평균_t_hi": tci[1]})
                ab, ak = np.abs(xs), np.abs(xk)
                dd, bci, tci = diff_ci(ab, ak)
                diffs.append((grp, "수익률 절댓값 평균: 답함(오름+내림) − 모름", f"{len(ab):,} / {len(ak):,}", dd, bci,
                              f"절댓값 평균 — 답함 {ab.mean():.3f} · 모름 {ak.mean():.3f}" if len(ab) and len(ak) else ""))
                rows_csv.append({"판": name, "묶음": grp, "기간": lab, "답": "절댓값 답함 − 모름", "n": len(ab), "n2": len(ak), "평균": dd,
                                 "평균_boot_lo": bci[0], "평균_boot_hi": bci[1], "평균_t_lo": tci[0], "평균_t_hi": tci[1],
                                 "답함_abs평균": ab.mean() if len(ab) else math.nan, "모름_abs평균": ak.mean() if len(ak) else math.nan})
                if h == "post30":
                    main_rows.append((name, grp, {a: got[a] for a in ANS}, got["(기준선) 전체"], got["오름 − 내림"]))
            L += ["", f"차이({lab}, 단위 %p, 95% 구간 = 부트스트랩)", "",
                  "| 묶음 | 비교 | 건(빼지는 쪽 / 빼는 쪽) | 차 | 95% 구간 | 참고 |", "|---|---|---|---:|---|---|"]
            for t in diffs:
                grp, lab_d, nn, dd, bci = t[:5]
                note = t[5] if len(t) > 5 else ""
                L.append(f"| {grp} | {lab_d} | {nn} | {f3(dd)} | {ci(*bci)} | {note} |")
            L.append("")

        # 쏠림(30분 — 5분은 CSV)
        L += [f"### {name} · 종목 쏠림(답별)", "",
              "건수 최다 종목 몫 = 그 답 건 가운데 한 종목이 차지한 건수 비율. 합 기여 최대 종목 = 수익률 합에서 같은 부호로 가장 크게 기여한 종목(몫 = 그 종목 합 ÷ 전체 합, 합이 0 에 가까우면 100% 를 넘을 수 있음). 단위 %. 30분만(5분은 CSV).", "",
              "| 묶음 | 답 | 건 | 종목 수 | 건수 최다 종목(몫) | 상위 5종목 건수 몫 | 합 기여 최대 종목(몫) | 평균 | 그 종목 뺀 평균 | 위아래 1% 자른 평균 | 종목 같은 무게 평균 |",
              "|---|---|---:|---:|---|---|---|---:|---:|---:|---:|"]
        for grp, g in groups_of(k):
            if "목록형" in grp:
                continue
            for a in ANS:
                gg = g[g["답"] == a]
                for h, lab in HORIZONS:
                    c = concentration(gg, h)
                    if c:
                        rows_csv.append({"판": name, "묶음": grp, "기간": lab, "답": f"쏠림 · {a}", **{f"쏠림_{kk}": vv for kk, vv in c.items()}})
                c = concentration(gg, "post30")
                if not c:
                    continue
                L.append(f"| {grp} | {a} | {c['건수']:,} | {c['종목수']:,} | {c['건수최다종목']} ({pc(c['건수최다몫'])}) | {pc(c['상위5종목건수몫'])} | "
                         f"{c['합기여최대종목']} ({pc(c['합기여최대몫'])}) | {f3(c['평균'])} | {f3(c['그종목뺀평균'])} | {f3(c['위아래1%자른평균'])} | {f3(c['종목같은무게평균'])} |")
        L.append("")

    # ================================================ 주 표(맨 앞에 끼워 넣음)
    head = ["## 주 표 — 30분, 답별 평균(%) · 오름 − 내림(%p)", "",
            "| 판 | 묶음 | 기준선 평균 · 오른/내린 | 오름: 건 · 평균 [95%] | 내림: 건 · 평균 [95%] | 모름: 건 · 평균 [95%] | 오름 − 내림 [95%] |",
            "|---|---|---|---|---|---|---|"]
    for name, grp, d, base, (dd, bci, _) in main_rows:
        if "목록형" in grp and name != "B-주 Sonnet":
            continue
        cell = []
        for a in ANS:
            x = d[a]
            cell.append("0건" if x["n"] == 0 else f"{x['n']:,} · {f3(x['평균'])} {ci(x['평균_boot_lo'], x['평균_boot_hi'])}")
        L_ = f"| {name} | {grp} | {f3(base['평균'])} · {pc(base['오른비율'])}/{pc(base['내린비율'])} | " + " | ".join(cell) + f" | {f3(dd)} {ci(*bci)} |"
        head.append(L_)
    dfc = pd.DataFrame(rows_csv)
    dd_ = dfc.dropna(subset=["평균_boot_lo", "평균_t_lo"])
    flip = dd_[((dd_["평균_boot_lo"] > 0) | (dd_["평균_boot_hi"] < 0)) != ((dd_["평균_t_lo"] > 0) | (dd_["평균_t_hi"] < 0))]
    head += ["", f"- 부트스트랩 구간과 t 구간(CSV)의 '0 포함/벗어남' 판정이 갈린 줄: {len(flip)}/{len(dd_)}"
             + ("" if flip.empty else " — " + "; ".join(f"{r.판} · {r.묶음} · {r.기간} · {r.답}" for r in flip.itertuples())) + ".",
             "- 부트스트랩 구간 끝은 뽑기 오차로 시드에 따라 0.01%p 안팎 달라질 수 있다(같은 시드로 다시 돌리면 같은 값).", ""]
    idx =L.index("## 1. 자료 붙이기 · 영상에 나간 수와 대조")
    L = L[:idx] + head + L[idx:]

    (OUT / "답별_수익률.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    pd.DataFrame(rows_csv).to_csv(OUT / "답별_수익률.csv", index=False, encoding="utf-8-sig")
    print(f"[끝] {OUT / '답별_수익률.md'} · 줄 {len(rows_csv)} · 대조 불일치 {len(mism)}")


if __name__ == "__main__":
    main()
