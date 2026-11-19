# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 4단계 — 채점·집계 (2026-11-17). 결정적 코드만 — 모델·외부 API 를 부르지 않는다.

정답 = 과제4/표본4.csv 의 Q1·Q2(30분 창 · 원 수익률 · 상대 상위 10%), 보조 = Q1_초과·Q2_초과.
답 = run4/<판>_<모델>_run<N>.jsonl 의 answers(번호 → 앞·뒤). '예'·'아니오'·'모름' 밖의 값과 빠진 번호는 '답 없음'(분모에서 뺌).
지표(질문마다): 답 분포 · 모름 비율 · 답한 건 정확도 · '예' 정밀도 · 재현율 · F1 · 균형 정확도(BA) — 답한 건 기준과 '모름 = 오답' 기준 둘 다.
  구간: 비율은 윌슨 95%, BA·F1·차는 층 안에서 다시 뽑는 부트스트랩(2,000회, 시드 고정) 2.5~97.5%.
  '모름 = 오답': 정확도 = (TP+TN)/전체 · 재현율 = TP/정답 예 전체 · BA = (TP/정답 예 전체 + TN/정답 아니오 전체)/2.

쓰기(이 폴더에서):
  python -X utf8 scripts/ep09_grade4.py selftest     # 정답을 답으로 넣으면 BA 1 인지 · 전부 모름이면 BA(모름=오답) 0 인지
  python -X utf8 scripts/ep09_grade4.py all          # → data/ep09/채점4/
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
import ep09_run as R  # noqa: E402

EP09 = DATA / "ep09"
T4 = EP09 / "과제4"
RUN4 = EP09 / "run4"
OUT4 = EP09 / "채점4"
MODELS = ("haiku", "sonnet", "opus")
MNAME = {"haiku": "Haiku", "sonnet": "Sonnet", "opus": "Opus"}
PNAME = {"N": "맨손", "E": "예시", "F": "강제"}
KINDS = ["일반 기사", "시세 중계", "공시 피드"]
PERIODS = ["기한 앞(~05)", "회색(06)", "기한 뒤(07~)"]
QS = ("Q1", "Q2")
QNAME = {"Q1": "Q1 앞 30분", "Q2": "Q2 뒤 30분"}
B = 2000
SEED = 20261119
MAP = {"예": "Y", "아니오": "N", "모름": "U"}


# ================================================================ 통계 도구
def wilson(k, n, z=1.96):
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def pct(k, n, ci=True):
    if n == 0:
        return "–"
    s = f"{k / n * 100:.1f}% ({k}/{n})"
    if ci:
        lo, hi = wilson(k, n)
        s += f" [{lo * 100:.1f}~{hi * 100:.1f}]"
    return s


def boot_idx(strata: np.ndarray, rng, b=B) -> np.ndarray:
    """층 안에서 다시 뽑기 → (b, n) 위치 배열."""
    parts = []
    for s in pd.unique(strata):
        ix = np.flatnonzero(strata == s)
        parts.append(ix[rng.integers(0, len(ix), (b, len(ix)))])
    return np.concatenate(parts, axis=1)


def conf_counts(y, a):
    """y: 0/1, a: 'Y'/'N'/'U' → 배열 연산용 표시(브로드캐스트 가능)."""
    Y, N, U = (a == "Y"), (a == "N"), (a == "U")
    tp = (Y & (y == 1)).sum(-1)
    fp = (Y & (y == 0)).sum(-1)
    fn_ans = (N & (y == 1)).sum(-1)
    tn = (N & (y == 0)).sum(-1)
    P = (y == 1).sum(-1)
    Nn = (y == 0).sum(-1)
    return tp, fp, fn_ans, tn, P, Nn, U.sum(-1)


def ba_all(y, a):
    tp, fp, fn, tn, P, Nn, u = conf_counts(y, a)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (tp / P + tn / Nn) / 2


def ba_ans(y, a):
    tp, fp, fn, tn, P, Nn, u = conf_counts(y, a)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (tp / (tp + fn) + tn / (tn + fp)) / 2


def f1_ans(y, a):
    tp, fp, fn, tn, P, Nn, u = conf_counts(y, a)
    with np.errstate(invalid="ignore", divide="ignore"):
        return 2 * tp / (2 * tp + fp + fn)


def prec(y, a):
    tp, fp, fn, tn, P, Nn, u = conf_counts(y, a)
    with np.errstate(invalid="ignore", divide="ignore"):
        return tp / (tp + fp)


def q(x, lo=2.5, hi=97.5):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return (math.nan, math.nan)
    return (float(np.percentile(x, lo)), float(np.percentile(x, hi)))


def ci_txt(v, lo, hi, scale=100, d=1, unit=""):
    if not np.isfinite(v):
        return "–"
    return f"{v * scale:.{d}f}{unit} [{lo * scale:.{d}f}~{hi * scale:.{d}f}]"


def zjudge(lo, hi, ref=0.0):
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "–"
    if lo > ref:
        return "벗어남(+)"
    if hi < ref:
        return "벗어남(−)"
    return "포함"


# ================================================================ 읽기
def load_sample() -> pd.DataFrame:
    s = pd.read_csv(T4 / "표본4.csv", dtype={"id": str, "day": str, "srno": str, "code": str, "tm": str}, encoding="utf-8-sig")
    b = pd.read_csv(T4 / "기준선_예측.csv", dtype={"id": str}, encoding="utf-8-sig")
    s = s.merge(b, on="id", how="left", validate="one_to_one")
    s["abs_post30"] = s["post30"].abs()
    s["abs_pre30"] = s["pre30"].abs()
    return s


def norm(v):
    if v is None:
        return None
    v = str(v).strip().strip('"').strip()
    return MAP.get(v)


SALV = re.compile(r'"번호"\s*:\s*"?(\d+)"?[^{}]*?"앞"\s*:\s*"([^"]*)"[^{}]*?"뒤"\s*:\s*"([^"]*)"', re.S)


def load_run(pan: str, model: str, run: int = 1, salvage: bool = False) -> tuple[dict, dict]:
    """→ (id → (앞, 뒤) 정규화 답), 호출 정보. salvage=True 면 파싱 실패 묶음에서 번호·앞·뒤 짝을 정규식으로 꺼낸다(보조, 마지막 것)."""
    p = RUN4 / f"{pan}_{model}_run{run}.jsonl"
    out, info = {}, Counter()
    recs = R.latest(p, "unit")
    for u, r in recs.items():
        info["묶음"] += 1
        info[r["status"]] += 1
        if r["status"] == "ok":
            info["번호 빠짐"] += len(r.get("번호_빠짐", []))
            for i, a in r["answers"].items():
                out[i] = (norm(a.get("앞")), norm(a.get("뒤")))
        elif r["status"] == "파싱실패" and salvage:
            got = {}
            for m in SALV.finditer(r.get("result", "")):
                got[int(m.group(1))] = (norm(m.group(2)), norm(m.group(3)))
            for k, uid in enumerate(r["ids"], 1):
                if k in got:
                    out[uid] = got[k]
    return out, dict(info)


def calls(pan: str, model: str, run: int = 1) -> pd.DataFrame:
    rows = [r for r in R.read_jsonl(RUN4 / f"{pan}_{model}_run{run}.jsonl") if r["status"] in ("ok", "파싱실패")]
    return pd.DataFrame(rows)


# ================================================================ 한 칸 지표
def cell(y, a):
    """y: 0/1 배열, a: 답 배열(Y/N/U) — 답 온 건만."""
    tp, fp, fn, tn, P, Nn, u = (int(x) for x in conf_counts(y, a))
    n = len(y)
    nY, nN = tp + fp, fn + tn
    d = {"n": n, "예": nY, "아니오": nN, "모름": u, "정답 예": P,
         "모름%": pct(u, n, ci=False), "정답 예 비율": pct(P, n, ci=False),
         "정확도(답한 건)": pct(tp + tn, nY + nN), "정밀도": pct(tp, nY), "재현율(답한 건)": pct(tp, tp + fn),
         "재현율(모름=오답)": pct(tp, P), "정확도(모름=오답)": pct(tp + tn, n),
         "_tp": tp, "_fp": fp, "_fn": fn, "_tn": tn, "_P": P, "_N": Nn, "_u": u}
    with np.errstate(invalid="ignore", divide="ignore"):
        d["_f1"] = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else math.nan
        d["_ba_ans"] = ((tp / (tp + fn) if tp + fn else math.nan) + (tn / (tn + fp) if tn + fp else math.nan)) / 2
        d["_ba_all"] = ((tp / P if P else math.nan) + (tn / Nn if Nn else math.nan)) / 2
        d["_prec"] = tp / nY if nY else math.nan
    return d


def u2n(a):
    """보조: '모름'을 '아니오'로 바꾼 답(모든 건에 결정이 있게)."""
    return np.where(a == "U", "N", a).astype(object)


def boot_cell(y, a, strata, rng):
    ix = boot_idx(strata, rng)
    yy, aa = y[ix], a[ix]
    return {"ba_all": q(ba_all(yy, aa)), "ba_ans": q(ba_ans(yy, aa)), "f1": q(f1_ans(yy, aa)), "ba_u2n": q(ba_all(yy, u2n(aa)))}


def fmt_cell(d, bc):
    return {**{k: v for k, v in d.items() if not k.startswith("_")},
            "F1(답한 건)": ci_txt(d["_f1"], *bc["f1"], d=1),
            "BA(답한 건)": ci_txt(d["_ba_ans"], *bc["ba_ans"]),
            "BA(모름=오답)": ci_txt(d["_ba_all"], *bc["ba_all"])}


# ================================================================ 전체
def answers_frame(S: pd.DataFrame, salvage=False):
    """판·모델별 답을 표본 순서에 맞춘 열로. 열 이름 <판>_<모델>_r<run>_<Q>."""
    A = pd.DataFrame({"id": S["id"]})
    info = {}
    runs = [(p, m, 1) for p in ("N", "E") for m in MODELS] + [("F", "sonnet", 1), ("N", "sonnet", 2), ("N", "sonnet", 3)]
    for p, m, r in runs:
        ans, inf = load_run(p, m, r, salvage)
        info[(p, m, r)] = inf
        A[f"{p}_{m}_r{r}_Q1"] = S["id"].map(lambda i: ans.get(i, (None, None))[0])
        A[f"{p}_{m}_r{r}_Q2"] = S["id"].map(lambda i: ans.get(i, (None, None))[1])
    return A, info


def run_all():
    OUT4.mkdir(parents=True, exist_ok=True)
    S = load_sample()
    A, info = answers_frame(S)
    As, info_s = answers_frame(S, salvage=True)
    for c in A.columns[1:]:
        S[c] = A[c].values
    rng = np.random.default_rng(SEED)
    L = []
    w = L.append
    w("# 4단계 집계 (scripts/ep09_grade4.py all — 자동 생성)\n")
    w("> 숫자와 '구간이 ~을 포함/벗어남'만. 비율 구간 = 윌슨 95%, BA·F1·차 구간 = 층 안 부트스트랩 2,000회 2.5~97.5%. BA = 균형 정확도(0.5 = 가르지 못함).\n")
    # ---- 호출·답 수
    w("## 1. 호출과 답이 온 건\n")
    w("| 판 | 모델 | run | 묶음 | ok | 파싱 실패 | 번호 빠짐 | Q1 답 온 건 | Q2 답 온 건 | Q1 형식 밖 값 | 파싱 실패 살린 뒤 Q1·Q2 답 온 건(보조) |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for (p, m, r), inf in info.items():
        if not inf.get("묶음"):
            continue
        c1 = A[f"{p}_{m}_r{r}_Q1"].notna().sum()
        c2 = A[f"{p}_{m}_r{r}_Q2"].notna().sum()
        # 형식 밖 값 = 답 객체는 있는데 정규화가 None
        raw_ok = 0
        for rr in R.latest(RUN4 / f"{p}_{m}_run{r}.jsonl", "unit").values():
            if rr["status"] == "ok":
                raw_ok += sum(1 for a in rr["answers"].values() if norm(a.get("앞")) is None)
        w(f"| {PNAME[p]} | {MNAME[m]} | {r} | {inf.get('묶음', 0)} | {inf.get('ok', 0)} | {inf.get('파싱실패', 0)} | {inf.get('번호 빠짐', 0)} | {c1} | {c2} | {raw_ok} | "
          f"{As[f'{p}_{m}_r{r}_Q1'].notna().sum()} · {As[f'{p}_{m}_r{r}_Q2'].notna().sum()} |")
    w("")
    rows_main = []
    # ---- 기준선
    strata_all = S["층"].values
    cfg = json.loads((T4 / "기준선_설정.json").read_text(encoding="utf-8"))
    rate_front = {k: cfg[f"앞 절반 정답 비율 {k}"] for k in KINDS}
    base_cols = {"전부 아니오": None, "전부 예": None, "낱말 규칙": "낱말_{q}_예측", "갈래 분류 규칙": "갈래_{q}_예측", "전체 특징 규칙(참고)": "전체특징_{q}_예측"}

    def base_ans(name, qq, idx=None):
        n = len(S)
        if name == "전부 아니오":
            a = np.array(["N"] * n, object)
        elif name == "전부 예":
            a = np.array(["Y"] * n, object)
        else:
            a = np.where(S[base_cols[name].format(q=qq)].values == 1, "Y", "N").astype(object)
        return a if idx is None else a[idx]

    w("## 2. 기준선(모델 호출 없음, 3,000건 전부)\n")
    for qq in QS:
        y = S[qq].values
        w(f"### {QNAME[qq]}\n")
        w("| 기준선 | 층 | 예 답 | 정밀도 [윌슨] | 재현율 | 정확도 | F1 | BA [부트스트랩] |")
        w("|---|---|---:|---|---|---|---|---|")
        for name in base_cols:
            for k in ["전체"] + KINDS:
                m_ = np.ones(len(S), bool) if k == "전체" else (S["층"].values == k)
                a = base_ans(name, qq)[m_]
                d = cell(y[m_], a)
                bc = boot_cell(y[m_], a, strata_all[m_], rng)
                w(f"| {name} | {k} | {d['예']} | {d['정밀도']} | {d['재현율(모름=오답)']} | {d['정확도(모름=오답)']} | {ci_txt(d['_f1'], *bc['f1'])} | {ci_txt(d['_ba_all'], *bc['ba_all'])} |")
        # 층별 비율 무작위(앞 절반 비율) — 1,000번 모의
        sims = []
        r2 = np.random.default_rng(SEED + 1)
        pr = np.array([rate_front[k][qq] for k in S["층"]])
        for _ in range(1000):
            a = np.where(r2.random(len(S)) < pr, "Y", "N").astype(object)
            sims.append((ba_all(y, a), prec(y, a), f1_ans(y, a)))
        sims = np.array(sims, float)
        w(f"| 층별 비율 무작위(앞 절반 비율, 1,000번 모의) | 전체 | 평균 {int((pr).sum())} | 평균 {sims[:, 1].mean() * 100:.1f} [{np.percentile(sims[:, 1], 2.5) * 100:.1f}~{np.percentile(sims[:, 1], 97.5) * 100:.1f}] | – | – | "
          f"{sims[:, 2].mean() * 100:.1f} [{np.percentile(sims[:, 2], 2.5) * 100:.1f}~{np.percentile(sims[:, 2], 97.5) * 100:.1f}] | {sims[:, 0].mean() * 100:.1f} [{np.percentile(sims[:, 0], 2.5) * 100:.1f}~{np.percentile(sims[:, 0], 97.5) * 100:.1f}] |")
        from sklearn.metrics import roc_auc_score
        aucs = []
        for k in ["전체"] + KINDS:
            m_ = np.ones(len(S), bool) if k == "전체" else (S["층"].values == k)
            aucs.append(f"{k} {roc_auc_score(y[m_], S[f'낱말_{qq}_점수'].values[m_]):.3f}")
        w(f"\n- 낱말 규칙 점수의 AUC(문턱 없이, 이 3,000건): " + " · ".join(aucs) + f" (앞 절반 OOF {cfg[f'낱말 {qq} 앞 절반 OOF AUC']})\n")

    # ---- 주 표
    w("## 3. 주 표 — 모델 × 판(답 온 건, 30분 · 원 · 상대 상위 10%)\n")
    w("BA(모름=오답)의 0.5 비교: 구간이 0.5 를 포함하면 '가르지 못함과 구별되지 않는다'.\n")
    combos = [(p, m) for p in ("N", "E") for m in MODELS] + [("F", "sonnet")]
    detail = []
    for qq in QS:
        w(f"### {QNAME[qq]}\n")
        w("| 판 | 모델 | 층 | 답 온 건 | 예/아니오/모름 | 모름% | 정밀도 [윌슨] | 층 정답 비율 | 정밀도 대 층 정답 비율 | 재현율(답한 건) | 재현율(모름=오답) | 정확도(답한 건) | F1(답한 건) | BA(답한 건) | BA(모름=오답) | BA(모름=오답) 0.5 | BA(모름=아니오, 보조) |")
        w("|---|---|---|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for p, m in combos:
            col = f"{p}_{m}_r1_{qq}"
            for k in ["전체"] + KINDS:
                m_ = S[col].notna().values & (np.ones(len(S), bool) if k == "전체" else (S["층"].values == k))
                if m_.sum() == 0:
                    continue
                y = S[qq].values[m_]
                a = S[col].values[m_].astype(object)
                d = cell(y, a)
                bc = boot_cell(y, a, strata_all[m_], rng)
                fc = fmt_cell(d, bc)
                lo, hi = wilson(d["_tp"], d["예"]) if d["예"] else (math.nan, math.nan)
                base = d["_P"] / d["n"]
                jud = "–" if not d["예"] else ("위로 벗어남" if lo > base else "아래로 벗어남" if hi < base else "포함")
                w(f"| {PNAME[p]} | {MNAME[m]} | {k} | {d['n']} | {d['예']}/{d['아니오']}/{d['모름']} | {d['모름%']} | {d['정밀도']} | {base * 100:.1f}% | {jud} | {d['재현율(답한 건)']} | "
                  f"{d['재현율(모름=오답)']} | {d['정확도(답한 건)']} | {fc['F1(답한 건)']} | {fc['BA(답한 건)']} | {fc['BA(모름=오답)']} | {zjudge(*bc['ba_all'], ref=0.5)} | {ci_txt(ba_all(y, u2n(a)), *bc['ba_u2n'])} |")
                detail.append({"Q": qq, "판": PNAME[p], "모델": MNAME[m], "층": k, **{kk: v for kk, v in fc.items()},
                               "BA_ans": d["_ba_ans"], "BA_all": d["_ba_all"], "F1": d["_f1"], "prec": d["_prec"]})
        w("")
    pd.DataFrame(detail).to_csv(OUT4 / "주표_지표.csv", index=False, encoding="utf-8-sig")
    # 나머지 절은 함수로
    S2 = S
    sections(S2, A, As, rng, w, base_ans, rate_front, cfg)
    (OUT4 / "집계_4단계.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    keep = ["id", "층", "기한구간", "목록형", "Q1", "Q2", "Q1_초과", "Q2_초과", "abs_pre30", "abs_post30", "낱말_Q1_예측", "낱말_Q2_예측", "갈래_Q1_예측", "갈래_Q2_예측"]
    S2[keep + list(A.columns[1:])].to_csv(OUT4 / "건별_답.csv", index=False, encoding="utf-8-sig")
    print(f"→ {OUT4 / '집계_4단계.md'} ({len(L)}줄)")


def sections(S, A, As, rng, w, base_ans, rate_front, cfg):
    strata_all = S["층"].values
    combos = [(p, m) for p in ("N", "E") for m in MODELS] + [("F", "sonnet")]

    # ---- 4. 기준선 대비(짝지은 비교)
    w("## 4. 기준선 대비 차(같은 건끼리, 모델 − 기준선, %p)\n")
    w("- BA(모름=오답): 모델이 답을 보낸 모든 건에서. BA(답한 건): 모델이 예·아니오로 답한 건만 — 기준선도 같은 건에서 잰다.")
    w("- 정밀도 대 '층 구성 기대값': 모델이 '예'라 한 건의 층 구성대로 층 정답 비율을 섞은 값(예를 층 안에서 무작위로 골랐을 때의 정밀도)과의 차.\n")
    for qq in QS:
        w(f"### {QNAME[qq]}\n")
        w("| 판 | 모델 | 층 | BA(모름=오답) − 낱말 규칙 | 0 | BA(답한 건) − 낱말 규칙(같은 건) | 0 | BA(모름=오답) − 갈래 분류 규칙 | 0 | BA(답한 건) − 갈래 분류 규칙 | 0 | 정밀도 − 낱말 규칙 정밀도 | 0 | 정밀도 − 층 구성 기대값 | 0 | BA(모름=아니오) − 낱말 규칙(보조) | 0 |")
        w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for p, m in combos:
            col = f"{p}_{m}_r1_{qq}"
            for k in ["전체"] + KINDS:
                m_ = S[col].notna().values & (np.ones(len(S), bool) if k == "전체" else (S["층"].values == k))
                if m_.sum() == 0:
                    continue
                y = S[qq].values[m_]
                a = S[col].values[m_].astype(object)
                bw = base_ans("낱말 규칙", qq)[m_]
                bk = base_ans("갈래 분류 규칙", qq)[m_]
                st = strata_all[m_]
                ix = boot_idx(st, rng)
                yy, aa, ww, kk = y[ix], a[ix], bw[ix], bk[ix]
                ans_mask = (aa != "U")
                # 답한 건에서의 기준선: 모델이 모름인 자리는 기준선도 모름으로 둬서 같은 건만 셈
                ww_ans = np.where(ans_mask, ww, "U")
                kk_ans = np.where(ans_mask, kk, "U")
                d_w_all = ba_all(yy, aa) - ba_all(yy, ww)
                d_w_ans = ba_ans(yy, aa) - ba_ans(yy, ww_ans)
                d_k_all = ba_all(yy, aa) - ba_all(yy, kk)
                d_k_ans = ba_ans(yy, aa) - ba_ans(yy, kk_ans)
                d_p_w = prec(yy, aa) - prec(yy, ww)
                # 층 구성 기대값
                rate = {kk_: S.loc[S["층"] == kk_, qq].mean() for kk_ in KINDS}
                r_arr = np.array([rate[s] for s in st])
                rr = r_arr[ix]
                with np.errstate(invalid="ignore", divide="ignore"):
                    exp_p = ((aa == "Y") * rr).sum(-1) / (aa == "Y").sum(-1)
                d_p_e = prec(yy, aa) - exp_p
                d_u_w = ba_all(yy, u2n(aa)) - ba_all(yy, ww)
                # 점 추정
                a0, w0, k0 = a, bw, bk
                am = a0 != "U"
                with np.errstate(invalid="ignore", divide="ignore"):
                    pt = [ba_all(y, a0) - ba_all(y, w0), ba_ans(y, a0) - ba_ans(y, np.where(am, w0, "U")),
                          ba_all(y, a0) - ba_all(y, k0), ba_ans(y, a0) - ba_ans(y, np.where(am, k0, "U")),
                          prec(y, a0) - prec(y, w0), prec(y, a0) - (((a0 == "Y") * r_arr).sum() / max((a0 == "Y").sum(), 1) if (a0 == "Y").sum() else math.nan),
                      ba_all(y, u2n(a0)) - ba_all(y, w0)]
                cis = [q(d_w_all), q(d_w_ans), q(d_k_all), q(d_k_ans), q(d_p_w), q(d_p_e), q(d_u_w)]
                cells = []
                for v, (lo, hi) in zip(pt, cis):
                    cells += [ci_txt(v, lo, hi, unit=""), zjudge(lo, hi)]
                w(f"| {PNAME[p]} | {MNAME[m]} | {k} | " + " | ".join(cells) + " |")
        w("")
    # 같은 '예' 수로 맞춘 낱말 규칙(보조)
    w("### 같은 '예' 수로 맞춘 낱말 규칙(보조) — 모델이 답을 보낸 건 안에서, 낱말 규칙 점수 위 k 건을 '예'로(k = 모델의 '예' 수)\n")
    w("| 판 | 모델 | Q | k | 모델 정밀도 [윌슨] | 낱말 규칙(위 k) 정밀도 [윌슨] | 모델 재현율(모름=오답) | 낱말 규칙(위 k) 재현율 |")
    w("|---|---|---|---:|---|---|---|---|")
    for p, m in combos:
        for qq in QS:
            col = f"{p}_{m}_r1_{qq}"
            m_ = S[col].notna().values
            if m_.sum() == 0:
                continue
            y = S[qq].values[m_]
            a = S[col].values[m_]
            k = int((a == "Y").sum())
            if k == 0:
                w(f"| {PNAME[p]} | {MNAME[m]} | {qq} | 0 | – | – | – | – |")
                continue
            sc = S[f"낱말_{qq}_점수"].values[m_]
            top = np.argsort(-sc, kind="stable")[:k]
            tp_w = int(y[top].sum())
            tp_m = int(((a == "Y") & (y == 1)).sum())
            w(f"| {PNAME[p]} | {MNAME[m]} | {qq} | {k} | {pct(tp_m, k)} | {pct(tp_w, k)} | {pct(tp_m, int(y.sum()), ci=False)} | {pct(tp_w, int(y.sum()), ci=False)} |")
    w("")

    # ---- 5. 판 비교(예시 − 맨손, 강제 − 맨손)
    w("## 5. 판 비교(같은 건끼리, 차 %p)\n")
    w("| 비교 | 모델 | Q | 같은 건 | 모름% 앞→뒤 | '예' 비율 앞→뒤 | BA(모름=오답) 차 | 0 | BA(답한 건) 차 | 0 | 정밀도 차 | 0 | 재현율(모름=오답) 차 | 0 |")
    w("|---|---|---|---:|---|---|---|---|---|---|---|---|---|---|")
    comps = [("예시 − 맨손", "E", "N", m) for m in MODELS] + [("강제 − 맨손", "F", "N", "sonnet")]
    for lab, p1, p0, m in comps:
        for qq in QS:
            c1, c0 = f"{p1}_{m}_r1_{qq}", f"{p0}_{m}_r1_{qq}"
            m_ = S[c1].notna().values & S[c0].notna().values
            if m_.sum() == 0:
                continue
            y = S[qq].values[m_]
            a1, a0 = S[c1].values[m_].astype(object), S[c0].values[m_].astype(object)
            ix = boot_idx(strata_all[m_], rng)
            yy, x1, x0 = y[ix], a1[ix], a0[ix]

            def rec_all(yv, av):
                tp, fp, fn, tn, P, Nn, u = conf_counts(yv, av)
                with np.errstate(invalid="ignore", divide="ignore"):
                    return tp / P
            res = []
            for fn_ in (ba_all, ba_ans, prec, rec_all):
                v = fn_(y, a1) - fn_(y, a0)
                lo, hi = q(fn_(yy, x1) - fn_(yy, x0))
                res += [ci_txt(v, lo, hi), zjudge(lo, hi)]
            n = int(m_.sum())
            w(f"| {lab} | {MNAME[m]} | {qq} | {n} | {(a0 == 'U').mean() * 100:.1f}→{(a1 == 'U').mean() * 100:.1f} | {(a0 == 'Y').mean() * 100:.1f}→{(a1 == 'Y').mean() * 100:.1f} | " + " | ".join(res) + " |")
    w("")

    # ---- 6. 기간별
    w("## 6. 학습 기한 앞·회색·뒤(뒤 절반 안 — 기한 앞 = 2026-05-09~05-31, 회색 = 06월, 기한 뒤 = 07월~)\n")
    w("| 판 | 모델 | Q | 구간 | 답 온 건 | 모름% | 정밀도 [윌슨] | 정답 예 비율 | 재현율(모름=오답) | BA(모름=오답) | BA(답한 건) | 낱말 규칙 BA | 모델 − 낱말 규칙 BA(모름=오답) | 0 |")
    w("|---|---|---|---|---:|---|---|---|---|---|---|---|---|---|")
    per_rows = []
    for p, m in combos:
        for qq in QS:
            col = f"{p}_{m}_r1_{qq}"
            for per in PERIODS:
                m_ = S[col].notna().values & (S["기한구간"].values == per)
                if m_.sum() == 0:
                    continue
                y = S[qq].values[m_]
                a = S[col].values[m_].astype(object)
                bw = base_ans("낱말 규칙", qq)[m_]
                d = cell(y, a)
                ix = boot_idx(strata_all[m_], rng)
                bc = {"ba_all": q(ba_all(y[ix], a[ix])), "ba_ans": q(ba_ans(y[ix], a[ix]))}
                dd = q(ba_all(y[ix], a[ix]) - ba_all(y[ix], bw[ix]))
                v = ba_all(y, a) - ba_all(y, bw)
                w(f"| {PNAME[p]} | {MNAME[m]} | {qq} | {per} | {d['n']} | {d['모름%']} | {d['정밀도']} | {d['정답 예 비율']} | {d['재현율(모름=오답)']} | "
                  f"{ci_txt(d['_ba_all'], *bc['ba_all'])} | {ci_txt(d['_ba_ans'], *bc['ba_ans'])} | {ba_all(y, bw) * 100:.1f} | {ci_txt(v, *dd)} | {zjudge(*dd)} |")
            # 기한 앞 − 기한 뒤 차(BA 모름=오답)
            ma = S[col].notna().values & (S["기한구간"].values == PERIODS[0])
            mb = S[col].notna().values & (S["기한구간"].values == PERIODS[2])
            if ma.sum() == 0 or mb.sum() == 0:
                continue
            ya, aa_ = S[qq].values[ma], S[col].values[ma].astype(object)
            yb, ab_ = S[qq].values[mb], S[col].values[mb].astype(object)
            ia, ib = boot_idx(strata_all[ma], rng), boot_idx(strata_all[mb], rng)
            dv = ba_all(ya, aa_) - ba_all(yb, ab_)
            dci = q(ba_all(ya[ia], aa_[ia]) - ba_all(yb[ib], ab_[ib]))
            per_rows.append(f"| {PNAME[p]} | {MNAME[m]} | {qq} | {ci_txt(dv, *dci)} | {zjudge(*dci)} |")
    w("\n기한 앞 − 기한 뒤 (BA 모름=오답, 서로 다른 건이라 따로 뽑은 부트스트랩)\n")
    w("| 판 | 모델 | Q | 차 %p [95%] | 0 |")
    w("|---|---|---|---|---|")
    for r_ in per_rows:
        w(r_)
    w("")

    # ---- 7. '예' 답 건의 실제 움직임 크기
    w("## 7. '예'라 답한 건의 실제 움직임 크기(Q1 = |앞 30분 수익률|, Q2 = |뒤 30분 수익률|, 단위 %, 원 수익률, 수수료·호가 차이 전)\n")
    w("| 판 | 모델 | Q | 예 건수 | 예 평균 | 아니오 건수 | 아니오 평균 | 모름 건수 | 모름 평균 | 예 − (아니오+모름) [부트스트랩] | 0 |")
    w("|---|---|---|---:|---|---:|---|---:|---|---|---|")
    rows_ret = combos + [("W", "낱말 규칙")]
    for p, m in rows_ret:
        for qq in QS:
            v = S["abs_pre30" if qq == "Q1" else "abs_post30"].values * 100
            if p == "W":
                col_a = base_ans("낱말 규칙", qq)
                m_ = np.ones(len(S), bool)
                lab_p, lab_m = "기준선", "낱말 규칙"
            else:
                col = f"{p}_{m}_r1_{qq}"
                m_ = S[col].notna().values
                col_a = S[col].values.astype(object)
                lab_p, lab_m = PNAME[p], MNAME[m]
            a = col_a[m_]
            vv = v[m_]
            yes, no, un = a == "Y", a == "N", a == "U"
            if yes.sum() == 0 or (~yes).sum() == 0:
                w(f"| {lab_p} | {lab_m} | {qq} | {int(yes.sum())} | – | {int(no.sum())} | – | {int(un.sum())} | – | – | – |")
                continue
            ix = boot_idx(strata_all[m_], rng)
            Y_, V_ = yes[ix], vv[ix]
            with np.errstate(invalid="ignore", divide="ignore"):
                dd = (V_ * Y_).sum(-1) / Y_.sum(-1) - (V_ * ~Y_).sum(-1) / (~Y_).sum(-1)
            lo, hi = q(dd)
            d0 = vv[yes].mean() - vv[~yes].mean()
            mu = lambda x: f"{vv[x].mean():.3f}" if x.sum() else "–"  # noqa: E731
            w(f"| {lab_p} | {lab_m} | {qq} | {int(yes.sum())} | {mu(yes)} | {int(no.sum())} | {mu(no)} | {int(un.sum())} | {mu(un)} | {d0:+.3f} [{lo:+.3f}~{hi:+.3f}] | {zjudge(lo, hi)} |")
    w("")

    # ---- 8. 재실행
    w("## 8. 재실행 — 맨손 Sonnet, 같은 400건 3회\n")
    rr = S[S["재실행"] == 1]
    for qq in QS:
        cols = [f"N_sonnet_r{r}_{qq}" for r in (1, 2, 3)]
        sub = rr[cols]
        ok = sub.notna().all(axis=1)
        same = (sub[ok].nunique(axis=1) == 1)
        pat = Counter(tuple(x) for x in sub[ok].values)
        w(f"- {QNAME[qq]}: 세 번 모두 답 온 건 {int(ok.sum())}/400 · 세 번 모두 같은 답 {pct(int(same.sum()), int(ok.sum()))}")
        top = ", ".join(f"{'/'.join(k)} {v}" for k, v in pat.most_common(8))
        w(f"  - 답 무늬(위 8): {top}")
        line = []
        for r in (1, 2, 3):
            c = f"N_sonnet_r{r}_{qq}"
            m_ = rr[c].notna().values
            d = cell(rr[qq].values[m_], rr[c].values[m_].astype(object))
            line.append(f"run{r} 모름 {d['모름%']} · 정밀도 {d['정밀도']} · BA(모름=오답) {d['_ba_all'] * 100:.1f}")
        w("  - " + " / ".join(line))
    w("")

    # ---- 9. 보조: 초과 수익률 판 정답 · 목록형 뺌 · 파싱 실패 살림
    w("## 9. 보조 표\n")
    w("### 9-1. 정답을 초과 수익률 판으로(Q1_초과·Q2_초과) · 목록형 제목 뺀 값 · 파싱 실패 묶음 살린 값 — 전체 층 합\n")
    w("| 판 | 모델 | Q | 판정 | 답 온 건 | 모름% | 정밀도 [윌슨] | 정답 예 비율 | BA(답한 건) | BA(모름=오답) | 낱말 규칙 BA(같은 건) |")
    w("|---|---|---|---|---:|---|---|---|---|---|---|")
    for p, m in combos:
        for qq in QS:
            col = f"{p}_{m}_r1_{qq}"
            for lab, ycol, extra, src in (("주(원)", qq, None, S), ("초과 수익률 정답", qq + "_초과", None, S),
                                          ("목록형 제목 뺌", qq, S["목록형"].values == 0, S), ("파싱 실패 살림", qq, None, None)):
                if src is None:
                    acol = As[col].values
                else:
                    acol = S[col].values
                m_ = pd.notna(acol)
                if extra is not None:
                    m_ = m_ & extra
                if m_.sum() == 0:
                    continue
                y = S[ycol].values[m_]
                a = acol[m_].astype(object)
                bw = base_ans("낱말 규칙", qq)[m_]
                d = cell(y, a)
                ix = boot_idx(strata_all[m_], rng)
                w(f"| {PNAME[p]} | {MNAME[m]} | {qq} | {lab} | {d['n']} | {d['모름%']} | {d['정밀도']} | {d['정답 예 비율']} | "
                  f"{ci_txt(d['_ba_ans'], *q(ba_ans(y[ix], a[ix])))} | {ci_txt(d['_ba_all'], *q(ba_all(y[ix], a[ix])))} | {ba_all(y, bw) * 100:.1f} |")
    w("")
    w("### 9-2. Q1·Q2 답 조합(맨손·예시, 전체)\n")
    w("| 판 | 모델 | 앞/뒤 답 조합 위 6 |")
    w("|---|---|---|")
    for p, m in combos:
        c1, c2 = f"{p}_{m}_r1_Q1", f"{p}_{m}_r1_Q2"
        mm = S[c1].notna() & S[c2].notna()
        cc = Counter(zip(S.loc[mm, c1], S.loc[mm, c2]))
        w(f"| {PNAME[p]} | {MNAME[m]} | " + ", ".join(f"{a}/{b} {v}" for (a, b), v in cc.most_common(6)) + " |")
    w("")

    # ---- 10. 토큰·시간
    w("## 10. 토큰 · 시간(호출 = 20건)\n")
    w("| 판 | 모델 | run | 호출 | 입력 평균 | 출력 평균 | 평균(초) | 최대(초) | 건당 입력 | 건당 출력 | 건당 초 | 표시 비용 합($, 구독이라 청구 아님) |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    tot = Counter()
    for p, m, r in [(p, m, 1) for p in ("N", "E") for m in MODELS] + [("F", "sonnet", 1), ("N", "sonnet", 2), ("N", "sonnet", 3)]:
        c = calls(p, m, r)
        if c.empty:
            continue
        tot["호출"] += len(c)
        tot["입력"] += c["in_tok"].sum()
        tot["출력"] += c["out_tok"].sum()
        tot["초"] += c["sec"].sum()
        tot["비용"] += c["cost_표시"].fillna(0).sum()
        w(f"| {PNAME[p]} | {MNAME[m]} | {r} | {len(c)} | {c['in_tok'].mean():,.0f} | {c['out_tok'].mean():,.0f} | {c['sec'].mean():.1f} | {c['sec'].max():.1f} | "
          f"{c['in_tok'].mean() / 20:,.0f} | {c['out_tok'].mean() / 20:,.1f} | {c['sec'].mean() / 20:.2f} | {c['cost_표시'].fillna(0).sum():.2f} |")
    w(f"\n- 합: 호출 {tot['호출']:,} · 입력 {int(tot['입력']):,} · 출력 {int(tot['출력']):,} · 호출 시간 합 {tot['초'] / 60:.1f}분 · 표시 비용 합 {tot['비용']:.2f}달러(구독 실행 — 청구액 아님)\n")
    # 실제 모델 목록
    used = Counter()
    for p in RUN4.glob("*.jsonl"):
        for r in R.read_jsonl(p):
            if r.get("status") in ("ok", "파싱실패"):
                used[(r["model_요청"], tuple(r.get("model_실제", [])))] += 1
    w("- 요청 모델 → 답의 모델 목록: " + " · ".join(f"{a} → {list(b)} {v}건" for (a, b), v in used.items()) + "\n")
    # 프롬프트 해시 대조
    pre = pd.read_csv(T4 / "프롬프트_해시_사전.csv", dtype=str, encoding="utf-8-sig")
    pre_h = {(r.task, r.unit): r.prompt_hash for r in pre.itertuples()}
    bad = tot_h = 0
    for p in RUN4.glob("*.jsonl"):
        for r in R.read_jsonl(p):
            tot_h += 1
            if pre_h.get((r["task"], r["unit"])) != r["prompt_hash"]:
                bad += 1
    w(f"- 실행 기록 {tot_h}줄의 prompt_hash 대 사전 계산 목록: 불일치 {bad}\n")


def selftest():
    S = load_sample()
    y = S["Q2"].values
    a = np.where(y == 1, "Y", "N").astype(object)
    assert abs(ba_all(y, a) - 1) < 1e-12 and abs(ba_ans(y, a) - 1) < 1e-12 and abs(prec(y, a) - 1) < 1e-12
    u = np.array(["U"] * len(y), object)
    assert ba_all(y, u) == 0
    n_ = np.array(["N"] * len(y), object)
    assert abs(ba_all(y, n_) - 0.5) < 1e-12
    print("selftest 통과: 정답 = 답 → BA 1 · 전부 모름 → BA(모름=오답) 0 · 전부 아니오 → BA 0.5")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    selftest() if cmd == "selftest" else run_all()
