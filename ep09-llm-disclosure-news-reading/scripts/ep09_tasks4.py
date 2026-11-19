# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 4단계 — 과제 정의(표본·예시·정답표·묶음·기준선). 모델 호출 없음. (2026-11-17)

과제: 뉴스 제목 + 종목명만 보고 한 건마다 두 가지를 답한다(방향은 묻지 않음).
  Q1 「이 기사가 나오기 전 30분에 이 종목 가격이 평소보다 크게 움직였는가」  예 / 아니오 / 모름
  Q2 「이 기사가 나온 뒤 30분에 이 종목 가격이 평소보다 크게 움직였는가」  예 / 아니오 / 모름
정답(주) = prepost_events.csv 의 q4_30분_원_상대상위10 (0 둘 다 없음 · 1 앞만 · 2 뒤만 · 3 이어짐 · 4 되돌림 · −1 계산 못 함)
  Q1 예 = {1,3,4} · Q2 예 = {2,3,4}.  보조 정답 = q4_30분_초과_상대상위10 (초과 수익률 판).

표본: 뒤 절반(20260509~20261110)에서 3,000건 — 일반 기사 1,500 · 시세 중계 750 · 공시 피드 750.
예시: 앞 절반(20251104~20260508)에서 40건(갈래 분류 × Q1·Q2 정답 네 조합이 고르게).
기준선(코드만): 전부 아니오·전부 예·층별 비율 무작위(채점기에서) · 낱말 규칙(로지스틱 회귀, 앞 절반 학습) · 갈래 분류 규칙.

쓰기(이 폴더에서):
  python -X utf8 scripts/ep09_tasks4.py build       # 표본·예시·묶음·깔때기 → data/ep09/과제4/
  python -X utf8 scripts/ep09_tasks4.py baseline    # 낱말 규칙·갈래 분류 규칙 학습(앞 절반만) → 과제4/기준선_예측.csv · 기준선_설정.json
읽기만: prepost_events.csv(자료 뿌리의 news/analysis_year/prepost/ 아래) · data/news/analysis_year/events.csv · data/daily/_universe_20261104.csv
        data/ep09/sample_B.csv · sample_B3.csv(겹침 표시용) · prepost_features.py 의 특징 함수(원본 news_prepost_rules.py 에서 옮김)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)

EP09 = DATA / "ep09"
T4 = EP09 / "과제4"
AY = DATA / "news" / "analysis_year"
PP = AY / "prepost"
NAMES = DATA / "daily" / "_universe_20261104.csv"

SEED4 = 20261119
B_BATCH = 20
PLAN_N = {"일반 기사": 1500, "시세 중계": 750, "공시 피드": 750}
EX_PER_COMBO = {"일반 기사": 4, "시세 중계": 3, "공시 피드": 3}     # × 4조합 = 16 + 12 + 12 = 40
N_FORCED_BATCHES = 50                                                # 강제 판 1,000건
N_RERUN_BATCHES = 20                                                 # 재실행 400건
KINDS = ["일반 기사", "시세 중계", "공시 피드"]
COL_RAW, COL_EX = "q4_30분_원_상대상위10", "q4_30분_초과_상대상위10"
YES1, YES2 = (1, 3, 4), (2, 3, 4)
# 학습 기한(2026-06) 기준 구간 — 뒤 절반 안에서
CUT_GRAY, CUT_AFTER = "20260601", "20260701"
LIST_REPEAT = 10                                                     # 목록형(틀) 제목: use==1 전체에서 같은 제목 10줄 이상(2·3단계와 같음)
# 낱말 규칙에 쓰는 특징 종류 = 제목에서만 나오는 것(모델 입력과 같은 정보 — 내가 정함)
TITLE_FTYPES = {"낱말", "두 낱말", "형태소", "앞 꼬리표", "끝 꼬리표", "표시", "제목 길이", "제목 속 종목 이름 수"}
MIN_FEAT = 5                                                          # 앞 절반에서 5건 이상 나온 특징만(내가 정함)
LR_C = 1.0                                                            # L2 로지스틱 회귀 규제 세기(내가 정함, 고정)
N_FOLD = 5


def period_of(day: str) -> str:
    if day < CUT_GRAY:
        return "기한 앞(~05)"
    if day < CUT_AFTER:
        return "회색(06)"
    return "기한 뒤(07~)"


# ================================================================ 표본 풀
def load_pool() -> tuple[pd.DataFrame, list[str]]:
    usecols = ["day", "tm", "m", "srno", "code", "dorg", "kind", "type", "period", "before_day", "tv20",
               "pre30", "post30", "ex_pre30", "ex_post30", COL_RAW, COL_EX]
    ev = pd.read_csv(PP / "prepost_events.csv", dtype={"day": str, "srno": str, "code": str, "tm": str}, usecols=usecols)
    ti = pd.read_csv(AY / "events.csv", dtype={"day": str, "srno": str, "code": str}, usecols=["day", "srno", "code", "use", "title"])
    ti = ti[ti.use == 1].drop(columns="use")
    ti["title"] = ti["title"].fillna("").astype(str)
    rep = ti.groupby("title")["title"].transform("size")              # 3단계와 같은 셈: use==1 전체에서 같은 제목 수
    ti["제목_반복수"] = rep
    n0 = len(ev)
    ev = ev.merge(ti, on=["day", "srno", "code"], how="left", validate="one_to_one")
    assert len(ev) == n0
    ev["title"] = ev["title"].fillna("")
    nm = dict(pd.read_csv(NAMES, dtype=str, encoding="utf-8-sig").fillna("")[["code", "name"]].values)
    ev["종목명"] = ev["code"].map(nm).fillna("")
    ev["id"] = ev["srno"] + "_" + ev["code"]
    ev["tm"] = ev["tm"].str.zfill(6)
    L = ["| 단계 | 앞 절반 | 뒤 절반 |", "|---|---:|---:|"]

    def row(lab, d):
        c = d["period"].value_counts()
        L.append(f"| {lab} | {c.get('앞 절반', 0):,} | {c.get('뒤 절반', 0):,} |")

    row("prepost_events.csv 주 표본(use==1)", ev)
    ev = ev[ev[COL_RAW] >= 0]
    row("30분 창 · 원 · 상대 상위 10% 갈래 계산된 건(−1 뺌: 09:31 전 기사·창 값 없음·평소 창 100개 미만)", ev)
    ev = ev[ev[COL_EX] >= 0]
    row("초과 수익률 판 갈래도 계산된 건", ev)
    ev = ev[(ev["종목명"] != "") & (ev["title"] != "")]
    row("종목명·제목 있음", ev)
    ev = ev.sort_values(["day", "tm", "srno", "code"]).drop_duplicates(["day", "m", "title"], keep="first")
    row("같은 날·분·제목 되풀이는 첫 건만(여러 종목에 붙은 같은 기사 포함)", ev)
    for c, col in (("Q1", COL_RAW), ("Q2", COL_RAW), ("Q1_초과", COL_EX), ("Q2_초과", COL_EX)):
        st = YES1 if c.startswith("Q1") else YES2
        ev[c] = ev[col].isin(st).astype(int)
    ev["목록형"] = (ev["제목_반복수"] >= LIST_REPEAT).astype(int)
    return ev.reset_index(drop=True), L


def build():
    T4.mkdir(parents=True, exist_ok=True)
    pool, L0 = load_pool()
    back = pool[pool["period"] == "뒤 절반"].copy()
    front = pool[pool["period"] == "앞 절반"].copy()
    old2 = set(pd.read_csv(EP09 / "sample_B.csv", dtype=str, encoding="utf-8-sig")["id"])
    old3 = set(pd.read_csv(EP09 / "sample_B3.csv", dtype=str, encoding="utf-8-sig")["id"])
    # ---- 평가 표본(뒤 절반, 층마다 무작위)
    out = []
    for i, k in enumerate(KINDS):
        g = back[back["kind"] == k].sort_values("id")
        s = g.sample(PLAN_N[k], random_state=SEED4 + i)
        out.append(s)
    S = pd.concat(out).sort_values(["day", "tm", "srno", "code"]).reset_index(drop=True)
    assert S["id"].is_unique
    S["층"] = S["kind"]
    S["기한구간"] = S["day"].map(period_of)
    S["겹침_B2"] = S["id"].isin(old2).astype(int)
    S["겹침_B3"] = S["id"].isin(old3).astype(int)
    # ---- 예시(앞 절반, 갈래 분류 × (Q1,Q2) 네 조합, 평가 표본 제목과 겹치지 않음)
    eval_titles = set(S["title"])
    fr = front[~front["title"].isin(eval_titles)].sort_values("id")
    ex = []
    j = 0
    for k in KINDS:
        for q1 in (1, 0):
            for q2 in (1, 0):
                g = fr[(fr["kind"] == k) & (fr["Q1"] == q1) & (fr["Q2"] == q2)]
                g = g.drop_duplicates("title")
                ex.append(g.sample(EX_PER_COMBO[k], random_state=SEED4 + 10 + j))
                j += 1
    E = pd.concat(ex)
    E = E.drop_duplicates("title")
    assert len(E) == 40, len(E)
    order = list(E["id"])
    random.Random(SEED4 + 20).shuffle(order)
    E = E.set_index("id").loc[order].reset_index()
    E["예시번호"] = range(1, len(E) + 1)
    assert not (set(E["title"]) & eval_titles)
    # ---- 묶음: 3,000건을 섞어 20건씩 150묶음(모든 판·모델이 같은 묶음)
    ids = sorted(S["id"])
    random.Random(SEED4 + 30).shuffle(ids)
    batches = {f"N{i // B_BATCH + 1:03d}": ids[i:i + B_BATCH] for i in range(0, len(ids), B_BATCH)}
    keys = sorted(batches)
    forced = sorted(random.Random(SEED4 + 31).sample(keys, N_FORCED_BATCHES))
    rerun = sorted(random.Random(SEED4 + 32).sample(keys, N_RERUN_BATCHES))
    S["강제"] = S["id"].isin({x for b in forced for x in batches[b]}).astype(int)
    S["재실행"] = S["id"].isin({x for b in rerun for x in batches[b]}).astype(int)
    b_of = {x: b for b, v in batches.items() for x in v}
    S["묶음"] = S["id"].map(b_of)
    cols = ["id", "층", "day", "tm", "m", "srno", "code", "종목명", "dorg", "type", "title", "제목_반복수", "목록형", "기한구간",
            "pre30", "post30", "ex_pre30", "ex_post30", COL_RAW, COL_EX, "Q1", "Q2", "Q1_초과", "Q2_초과", "겹침_B2", "겹침_B3", "묶음", "강제", "재실행"]
    S[cols].to_csv(T4 / "표본4.csv", index=False, encoding="utf-8-sig")
    E[["예시번호", "id", "kind", "day", "종목명", "title", "Q1", "Q2", COL_RAW]].rename(columns={"kind": "층"}).to_csv(T4 / "예시4.csv", index=False, encoding="utf-8-sig")
    (T4 / "묶음4.json").write_text(json.dumps({"묶음": batches, "강제": forced, "재실행": rerun}, ensure_ascii=False, indent=0), encoding="utf-8")
    # ---- 깔때기·층별 정답 비율
    L = [f"# 4단계 표본 깔때기 (scripts/ep09_tasks4.py build, {datetime.now():%Y-%m-%d %H:%M})", "",
         f"시드 {SEED4}(층마다 +0·+1·+2, 예시 +10~+21, 예시 순서 +20, 묶음 +30, 강제 묶음 +31, 재실행 묶음 +32).", "",
         "## 1. 풀(앞·뒤 절반)", ""] + L0 + ["",
         "## 2. 평가 표본(뒤 절반)", "",
         "| 층 | 뽑을 수 있는 건 | 표본 | Q1 예(원) | Q2 예(원) | Q1 예(초과) | Q2 예(초과) | 기한 앞(~05)/회색(06)/기한 뒤(07~) | 목록형 제목 | 겹침 2단계 B | 겹침 3단계 B3 |",
         "|---|---:|---:|---|---|---|---|---|---:|---:|---:|"]
    for k in KINDS + ["전체"]:
        g = back if k == "전체" else back[back["kind"] == k]
        s = S if k == "전체" else S[S["층"] == k]
        pc = Counter(s["기한구간"])
        L.append(f"| {k} | {len(g):,} | {len(s):,} | {s.Q1.mean() * 100:.1f}% ({s.Q1.sum()}) | {s.Q2.mean() * 100:.1f}% ({s.Q2.sum()}) | "
                 f"{s.Q1_초과.mean() * 100:.1f}% | {s.Q2_초과.mean() * 100:.1f}% | {pc['기한 앞(~05)']}/{pc['회색(06)']}/{pc['기한 뒤(07~)']} | "
                 f"{int(s.목록형.sum())} | {int(s.겹침_B2.sum())} | {int(s.겹침_B3.sum())} |")
    L += ["", "- 정답 비율(자연 비율) 비교용 — 뒤 절반 풀 전체(정리 뒤):", ""]
    for k in KINDS:
        g = back[back["kind"] == k]
        f = front[front["kind"] == k]
        L.append(f"  - {k}: 뒤 절반 풀 Q1 {g.Q1.mean() * 100:.1f}% · Q2 {g.Q2.mean() * 100:.1f}% / 앞 절반 풀 Q1 {f.Q1.mean() * 100:.1f}% · Q2 {f.Q2.mean() * 100:.1f}%")
    L += ["", "## 3. 예시 40건(앞 절반)", "",
          "| 층 | Q1 예·Q2 예 | Q1 예·Q2 아니오 | Q1 아니오·Q2 예 | 둘 다 아니오 |", "|---|---:|---:|---:|---:|"]
    for k in KINDS:
        e = E[E["kind"] == k]
        L.append(f"| {k} | " + " | ".join(str(int(((e.Q1 == a) & (e.Q2 == b)).sum())) for a, b in ((1, 1), (1, 0), (0, 1), (0, 0))) + " |")
    L += ["", f"- 예시 제목은 평가 표본 제목과 글자가 같은 것이 없다(확인). 예시 안 Q1 예 {E.Q1.mean() * 100:.0f}% · Q2 예 {E.Q2.mean() * 100:.0f}%(자연 비율보다 높음 — 고르게 섞은 결과).",
          f"- 묶음 {len(batches)}개(20건씩, 층이 섞임) · 강제 판 {len(forced)}묶음({len(forced) * B_BATCH}건) · 재실행 {len(rerun)}묶음({len(rerun) * B_BATCH}건).", ""]
    (T4 / "표본_깔때기_4단계.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


# ================================================================ 기준선(앞 절반에서만 정함)
def _f1(y, p):
    tp = int(((y == 1) & (p == 1)).sum())
    fp = int(((y == 0) & (p == 1)).sum())
    fn = int(((y == 1) & (p == 0)).sum())
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def best_threshold(y, s):
    """점수 s 에 대해 F1 이 가장 큰 문턱(앞 절반 OOF 점수로만). 후보 = 점수 분위 1~99%."""
    qs = np.unique(np.quantile(s, np.linspace(0.01, 0.99, 197)))
    best = (-1, 0.5)
    for t in qs:
        f = _f1(y, (s >= t).astype(int))
        if f > best[0]:
            best = (f, float(t))
    return best[1], best[0]


def baseline():
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold
    import scipy.sparse as sp
    import prepost_features as NR              # 특징 함수만(원본 news_prepost_rules.py 에서 옮김)

    pool, _ = load_pool()
    front = pool[pool["period"] == "앞 절반"].copy().reset_index(drop=True)
    S = pd.read_csv(T4 / "표본4.csv", dtype={"day": str, "srno": str, "code": str, "tm": str, "id": str}, encoding="utf-8-sig")
    ev_s = pool.set_index("id").loc[S["id"]].reset_index()
    both = pd.concat([front, ev_s], ignore_index=True)
    fmask = np.r_[np.ones(len(front), bool), np.zeros(len(ev_s), bool)]
    code2 = NR.load_names()
    feats, edges = NR.build_features(both.copy(), code2, fmask)
    info = {"앞 절반 학습 건수": int(len(front)), "제목 길이 경계(앞 절반)": edges["len_edges"], "시드": SEED4, "규제 C": LR_C,
            "특징 최소 건수": MIN_FEAT, "폴드": N_FOLD, "제목 특징 종류": sorted(TITLE_FTYPES)}
    out = pd.DataFrame({"id": ev_s["id"]})
    for variant, keep in (("낱말", lambda f: NR.ftype(f) in TITLE_FTYPES), ("전체특징", lambda f: True)):
        fr = [{f for f in feats[i] if keep(f)} for i in range(len(front))]
        ts = [{f for f in feats[len(front) + i] if keep(f)} for i in range(len(ev_s))]
        cnt = Counter(f for fs in fr for f in fs)
        vocab = sorted(f for f, c in cnt.items() if c >= MIN_FEAT)
        Xf = NR.to_X(fr, vocab).T.tocsr()
        Xt = NR.to_X(ts, vocab).T.tocsr()
        info[f"{variant} 특징 수"] = len(vocab)
        groups = front["day"].values
        for q in ("Q1", "Q2"):
            y = front[q].values
            oof = np.zeros(len(front))
            for tr, va in GroupKFold(N_FOLD).split(Xf, y, groups):
                m = LogisticRegression(C=LR_C, solver="liblinear", max_iter=2000)
                m.fit(Xf[tr], y[tr])
                oof[va] = m.predict_proba(Xf[va])[:, 1]
            thr, f1 = best_threshold(y, oof)
            m = LogisticRegression(C=LR_C, solver="liblinear", max_iter=2000)
            m.fit(Xf, y)
            st = m.predict_proba(Xt)[:, 1]
            out[f"{variant}_{q}_점수"] = st
            out[f"{variant}_{q}_예측"] = (st >= thr).astype(int)
            info[f"{variant} {q} 문턱(앞 절반 OOF F1 최대)"] = thr
            info[f"{variant} {q} 앞 절반 OOF F1"] = round(f1, 4)
            info[f"{variant} {q} 앞 절반 OOF AUC"] = round(float(roc_auc_score(y, oof)), 4)
            info[f"{variant} {q} 앞 절반 OOF 예 비율"] = round(float((oof >= thr).mean()), 4)
            if variant == "낱말":
                coef = pd.Series(m.coef_[0], index=vocab).sort_values()
                info[f"{variant} {q} 가중치 위 10"] = [[NR.show(k), round(float(v), 3)] for k, v in coef.tail(10)[::-1].items()]
                info[f"{variant} {q} 가중치 아래 10"] = [[NR.show(k), round(float(v), 3)] for k, v in coef.head(10).items()]
            print(f"[기준선] {variant} {q}: 특징 {len(vocab):,} · 문턱 {thr:.4f} · 앞 절반 OOF F1 {f1:.3f}", flush=True)
    # 갈래 분류 규칙: 예라고 할 갈래 집합을 앞 절반 F1 최대로(2^3 = 8 가지 중)
    import itertools
    for q in ("Q1", "Q2"):
        y = front[q].values
        best = (-1, ())
        for r in range(0, 4):
            for sub in itertools.combinations(KINDS, r):
                p = front["kind"].isin(sub).astype(int).values
                f = _f1(y, p)
                if f > best[0]:
                    best = (f, sub)
        info[f"갈래 규칙 {q} 예 갈래"] = list(best[1])
        info[f"갈래 규칙 {q} 앞 절반 F1"] = round(best[0], 4)
        out[f"갈래_{q}_예측"] = ev_s["kind"].isin(best[1]).astype(int).values
    for k in KINDS:
        f = front[front["kind"] == k]
        info[f"앞 절반 정답 비율 {k}"] = {"Q1": round(float(f.Q1.mean()), 4), "Q2": round(float(f.Q2.mean()), 4), "건수": int(len(f))}
    out.to_csv(T4 / "기준선_예측.csv", index=False, encoding="utf-8-sig", float_format="%.6g")
    (T4 / "기준선_설정.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in info.items() if "가중치" not in k}, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser(description="9편 실험 4단계 과제 정의")
    ap.add_argument("cmd", choices=["build", "baseline"])
    a = ap.parse_args()
    build() if a.cmd == "build" else baseline()


if __name__ == "__main__":
    main()
