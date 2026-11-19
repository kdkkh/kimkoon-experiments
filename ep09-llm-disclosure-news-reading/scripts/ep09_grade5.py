# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 5단계 — 채점·집계 (2026-11-18). 결정적 코드만 쓴다(모델에 채점을 맡기지 않는다). 파일만 읽는다.

  C5 정정 비교: 정답 값 짝(정답_C5.csv)마다, 모델 목록에 (정정전, 정정후)가 같은 값으로 든 객체가 있으면 '찾음'.
               값 비교 = 숫자는 쉼표·단위 뺀 수, 날짜는 YYYYMMDD, '-'·null·'없음' = 빈 값(ep09_tasks5.norm_val_loose). 항목 이름은 보지 않는다.
               보조: (후, 전) 뒤바뀜 · 한쪽만 맞음 · 모델이 적은 값 가운데 원문에 없는 값.
  S5 요약:     (a) 요약 속 수·날짜를 뽑아(조·억·만·천 단위 풀어 씀) 원문 수·날짜와 대조 → 그대로·환산 / 어림 / 원문에 없음.
                   환산 = 원문 수 × 1·10³·10⁶·10⁸(원·천원·백만원·억원 표) 과 같음. 어림 = 요약에 적힌 자릿수 안에서 같음(|요약 − 원문| < 표기 단위).
               (b) 핵심 칸(정답_S5_칸.csv) 가운데 요약에 든 비율 — 엄격(값 같음·날짜 같음) / 관용(어림·연도 없는 월일 포함).
  J5 판단:     답 정오(정답_J5.csv) + 근거 인용이 원문(모델이 받은 글)에 글자 그대로 있는가(공백·줄바꿈만 무시).

쓰기(이 폴더에서):
  python -X utf8 scripts/ep09_grade5.py selftest    # 가짜 답으로 채점기 점검(호출 없음)
  python -X utf8 scripts/ep09_grade5.py all         # → data/ep09/채점5/집계_5단계.md 와 건별 CSV
"""
from __future__ import annotations

import bisect
import json
import math
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
import ep09_run as R  # noqa: E402
import ep09_tasks5 as T  # noqa: E402

EP09 = DATA / "ep09"
T5 = EP09 / "과제5"
RUN5 = EP09 / "run5"
G5 = EP09 / "채점5"
MODELS = ("haiku", "sonnet", "opus")
MULTS = (Decimal(1), Decimal(10) ** 3, Decimal(10) ** 6, Decimal(10) ** 8)
UNITS = {"조": Decimal(10) ** 12, "억": Decimal(10) ** 8, "천만": Decimal(10) ** 7, "백만": Decimal(10) ** 6, "만": Decimal(10) ** 4, "천": Decimal(10) ** 3}
AMT_RE = re.compile(r"(?:(\d[\d,]*(?:\.\d+)?)\s*(조|억|천만|백만|만|천)\s*)+")
AMT_PART = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(조|억|천만|백만|만|천)")
NUM_PLAIN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    z = 1.959964
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pct(k: int, n: int, ci: bool = True) -> str:
    if n == 0:
        return "–"
    s = f"{100 * k / n:.1f}% ({k}/{n})"
    if ci:
        lo, hi = wilson(k, n)
        s += f" [{100 * lo:.1f}~{100 * hi:.1f}]"
    return s


def overlap_note(rows: dict[str, tuple[int, int]]) -> str:
    """모델 → (k, n). 윌슨 구간이 서로 겹치는지."""
    iv = {m: wilson(k, n) for m, (k, n) in rows.items() if n}
    ms = list(iv)
    sep = [(a, b) for i, a in enumerate(ms) for b in ms[i + 1:] if iv[a][1] < iv[b][0] or iv[b][1] < iv[a][0]]
    if not sep:
        return "세 모델 구간이 모두 겹침 → 가를 수 없다"
    return "구간이 겹치지 않는 짝: " + ", ".join(f"{a}–{b}" for a, b in sep) + " (나머지 짝은 겹침)"


# ================================================================ 공통: 답 읽기
def last_obj(text: str):
    """보조: 글 속 JSON 객체 가운데 마지막 것(3단계 보조 집계와 같은 생각)."""
    s = R.strip_fence(text or "")
    dec = json.JSONDecoder()
    out, i = None, 0
    while True:
        i = s.find("{", i)
        if i < 0:
            break
        try:
            o, j = dec.raw_decode(s, i)
            if isinstance(o, dict):
                out = o
            i = j
        except json.JSONDecodeError:
            i += 1
    return out


def load_answers(task: str, model: str, run: int, salvage: bool = False) -> tuple[dict, dict]:
    """→ ({unit: answer dict}, {unit: 기록})  주 = status ok 만. salvage = 파싱실패에서 마지막 객체 채택(보조)."""
    recs = R.latest(RUN5 / f"{task}_{model}_run{run}.jsonl", "unit")
    ans = {}
    for u, r in recs.items():
        if r["status"] == "ok":
            ans[u] = r["answer"]
        elif salvage and r["status"] == "파싱실패":
            o = last_obj(r.get("result", ""))
            if o is not None:
                ans[u] = o
    return ans, recs


_DOC = {}


def doc(rcp: str) -> tuple[str, dict]:
    if rcp not in _DOC:
        t, _ = R.doc_text(rcp)
        idx = T.doc_index(t)
        idx["nums_sorted"] = sorted(idx["nums"])
        _DOC[rcp] = (t, idx)
    return _DOC[rcp]


def in_doc_value(v: tuple, idx: dict) -> bool:
    k, x = v
    if k == "num":
        return abs(Decimal(x)) in idx["nums"]
    if k == "date":
        return x in idx["dates"]
    if k == "글":
        parts = [p for p in re.split(r"\(이름\)", re.sub(r"\s+", "", str(x))) if p]
        return all(p in idx["flat"] for p in parts) if parts else True
    return True


# ================================================================ C5
def grade_c5_doc(rcp: str, ans: dict, key: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    t, idx = doc(rcp)
    ents = ans.get("바뀐것") if isinstance(ans, dict) else None
    ents = ents if isinstance(ents, list) else []
    norm = []
    erows = []
    for i, e in enumerate(ents, 1):
        if not isinstance(e, dict):
            erows.append({"rcept_no": rcp, "객체": i, "형식": "객체 아님", "원문에_없는_값": ""})
            continue
        b, a = T.norm_val_loose(e.get("정정전")), T.norm_val_loose(e.get("정정후"))
        norm.append((b, a))
        miss = [side for side, v in (("전", b), ("후", a)) if not in_doc_value(v, idx)]
        erows.append({"rcept_no": rcp, "객체": i, "형식": "", "항목": str(e.get("항목"))[:80], "정정전": str(e.get("정정전"))[:80], "정정후": str(e.get("정정후"))[:80],
                      "전_형": b[0], "후_형": a[0], "원문에_없는_값": "·".join(miss)})
    prow = []
    for r in key.itertuples(index=False):
        tb = (r.전_형, Decimal(r.전_값) if r.전_형 == "num" else r.전_값)
        ta = (r.후_형, Decimal(r.후_값) if r.후_형 == "num" else r.후_값)
        if any(T.same(b, tb) and T.same(a, ta) for b, a in norm):
            res = "찾음"
        elif any(T.same(b, ta) and T.same(a, tb) for b, a in norm):
            res = "뒤바뀜"
        elif any(T.same(b, tb) or T.same(a, ta) for b, a in norm):
            res = "한쪽만 맞음"
        else:
            res = "없음"
        prow.append({"rcept_no": rcp, "짝": r.짝, "항목": r.항목, "전_원문": r.전_원문, "후_원문": r.후_원문, "결과": res})
    return prow, erows


# ================================================================ S5
def summary_tokens(s: str) -> list[dict]:
    s = str(s or "")
    toks = []
    used = []
    for kind, v, a, b in T.find_dates(s):
        toks.append({"형": kind, "값": v, "글": s[a:b], "자리": a})
        used.append((a, b))
    rest = list(s)
    for a, b in used:
        for i in range(a, b):
            rest[i] = " "
    rest = "".join(rest)
    for m in AMT_RE.finditer(rest):
        tot, prec = Decimal(0), Decimal(1)
        for n, u in AMT_PART.findall(m.group(0)):
            x = T.dnum(n)
            if x is None:
                continue
            tot += x * UNITS[u]
            dec = len(n.split(".")[1]) if "." in n else 0
            prec = UNITS[u] * Decimal(10) ** -dec
        toks.append({"형": "num", "값": tot, "정밀": prec, "글": m.group(0).strip(), "자리": m.start()})
        rest = rest[:m.start()] + " " * (m.end() - m.start()) + rest[m.end():]
    for m in NUM_PLAIN.finditer(rest):
        x = T.dnum(m.group(0))
        if x is None:
            continue
        dec = len(m.group(0).split(".")[1]) if "." in m.group(0) else 0
        toks.append({"형": "num", "값": x, "정밀": Decimal(10) ** -dec, "글": m.group(0), "자리": m.start()})
    return sorted(toks, key=lambda d: d["자리"])


def classify_token(tk: dict, idx: dict) -> str:
    k, v = tk["형"], tk["값"]
    ds = idx["dates"]
    if k == "date":
        return "그대로" if v in ds else "원문에 없음"
    if k == "md":
        return "그대로" if any(d[4:] == v for d in ds) else "원문에 없음"
    if k == "ym":
        return "그대로" if any(d[:6] == v for d in ds) else "원문에 없음"
    if k == "y":
        return "그대로" if (any(d[:4] == v for d in ds) or Decimal(v) in idx["nums"]) else "원문에 없음"
    V = abs(Decimal(v))
    for m in MULTS:
        if (V / m) in idx["nums"]:
            return "그대로" if m == 1 else "환산"
    S = idx["nums_sorted"]
    p = tk["정밀"]
    for m in MULTS:
        lo, hi = (V - p) / m, (V + p) / m
        i = bisect.bisect_right(S, lo)
        if i < len(S) and S[i] < hi:
            return "어림"
    return "원문에 없음"


def sentences(s: str) -> int:
    return len(re.findall(r"(?<!\d)[.!?](?!\d)", str(s or ""))) or (1 if str(s or "").strip() else 0)


def grade_s5_doc(rcp: str, ans: dict, keys: pd.DataFrame) -> tuple[dict, list[dict], list[dict]]:
    t, idx = doc(rcp)
    s = ans.get("요약") if isinstance(ans, dict) else None
    s = s if isinstance(s, str) else ("" if s is None else str(s))
    toks = summary_tokens(s)
    trows = []
    for tk in toks:
        c = classify_token(tk, idx)
        trows.append({"rcept_no": rcp, "형": tk["형"], "글": tk["글"], "값": T.fmtv(("num", tk["값"])) if tk["형"] == "num" else tk["값"], "분류": c})
    krows = []
    for r in keys.itertuples(index=False):
        strict = loose = False
        if r.형 == "num":
            F = abs(Decimal(r.정답))
            for tk in toks:
                if tk["형"] != "num":
                    continue
                V = abs(Decimal(tk["값"]))
                if V == F:
                    strict = loose = True
                elif abs(V - F) < tk["정밀"]:
                    loose = True
        else:
            for tk in toks:
                if tk["형"] == "date" and tk["값"] == r.정답:
                    strict = loose = True
                elif tk["형"] == "md" and tk["값"] == r.정답[4:]:
                    loose = True
        krows.append({"rcept_no": rcp, "칸": r.칸, "질문이름": r.질문이름, "형": r.형, "정답": r.정답, "엄격": int(strict), "관용": int(loose)})
    c = Counter(x["분류"] for x in trows)
    srow = {"rcept_no": rcp, "글자수": len(s), "문장수": sentences(s), "수": len(trows), "그대로": c["그대로"], "환산": c["환산"], "어림": c["어림"],
            "원문에없음": c["원문에 없음"], "핵심칸": len(krows), "핵심칸_엄격": sum(k["엄격"] for k in krows), "핵심칸_관용": sum(k["관용"] for k in krows), "요약": s}
    return srow, trows, krows


# ================================================================ J5
def norm_ans(v) -> str:
    if v is None:
        return "답 없음"
    s = re.sub(r"\s+", "", str(v)).strip("\"'")
    return {"예": "예", "아니오": "아니오", "판단불가": "판단 불가"}.get(s, "형식 밖")


def quote_check(q, flat: str) -> str:
    if q is None or (isinstance(q, str) and q.strip() in ("", "null")):
        return "근거 없음"
    qf = re.sub(r"\s+", "", str(q))
    if qf and qf in flat:
        return "일치"
    parts = [p for p in re.split(r"…|\.{2,}", qf) if p]
    if len(parts) > 1 and all(len(p) >= 4 and p in flat for p in parts):
        return "줄임표로 이어 붙임"
    return "불일치"


def grade_j5_doc(rcp: str, ans: dict, key: pd.DataFrame) -> list[dict]:
    t, idx = doc(rcp)
    rows = []
    for r in key.itertuples(index=False):
        o = ans.get(r.문항) if isinstance(ans, dict) else None
        a = norm_ans(o.get("답")) if isinstance(o, dict) else "답 없음"
        q = o.get("근거") if isinstance(o, dict) else None
        qc = quote_check(q, idx["flat"]) if isinstance(o, dict) else "답 없음"
        rows.append({"rcept_no": rcp, "kind": r.kind, "문항": r.문항, "출처": r.출처, "정답": r.정답, "답": a, "정오": int(a == r.정답),
                     "인용": qc, "근거": (str(q)[:200] if q is not None else "")})
    return rows


# ================================================================ 집계
def keys():
    kc = pd.read_csv(T5 / "정답_C5.csv", dtype=str, encoding="utf-8-sig").fillna("")
    ks = pd.read_csv(T5 / "정답_S5_칸.csv", dtype=str, encoding="utf-8-sig").fillna("")
    kj = pd.read_csv(T5 / "정답_J5.csv", dtype=str, encoding="utf-8-sig").fillna("")
    kj = kj[kj["뺀_이유"] == ""]
    return kc, ks, kj


def grade_task(task: str, model: str, run: int, salvage: bool = False):
    kc, ks, kj = keys()
    ans, recs = load_answers(task, model, run, salvage)
    out = {"ans": ans, "recs": recs}
    if task == "C5":
        P, Eo = [], []
        for rcp, g in kc.groupby("rcept_no"):
            if rcp in ans:
                p, e = grade_c5_doc(rcp, ans[rcp], g)
                P += p
                Eo += e
        out["pairs"], out["ents"] = pd.DataFrame(P), pd.DataFrame(Eo)
    elif task == "S5":
        S, Tt, K = [], [], []
        s = pd.read_csv(T5 / "S5J5_표본.csv", dtype=str, encoding="utf-8-sig").fillna("")
        kg = {r: g for r, g in ks.groupby("rcept_no")}
        for rcp in s["rcept_no"]:
            if rcp in ans:
                a, b, c = grade_s5_doc(rcp, ans[rcp], kg.get(rcp, ks.iloc[0:0]))
                S.append(a)
                Tt += b
                K += c
        out["sum"], out["toks"], out["keys"] = pd.DataFrame(S), pd.DataFrame(Tt), pd.DataFrame(K)
    else:
        rows = []
        for rcp, g in kj.groupby("rcept_no"):
            if rcp in ans:
                rows += grade_j5_doc(rcp, ans[rcp], g)
        out["items"] = pd.DataFrame(rows)
    return out


def call_table(L: list[str]):
    pre = pd.read_csv(T5 / "프롬프트_해시_사전.csv", dtype=str, encoding="utf-8-sig")
    ph = {(r.task, r.unit): r.prompt_hash for r in pre.itertuples(index=False)}
    L += ["## 호출 · 토큰 · 시간", "", "| 과제 | 모델 | run | 기록 줄 | ok | 파싱실패 | 호출실패 | 입력 평균 | 출력 평균 | 평균(초) | 최대(초) | 해시 불일치 | 요청 모델 없음 | 종료 상태 | 표시 비용 합($) |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|"]
    tot = Counter()
    for f in sorted(RUN5.glob("*_run*.jsonl")):
        task, model, run = f.stem.split("_")
        rows = R.read_jsonl(f)
        last = R.latest(f, "unit")
        st = Counter(r["status"] for r in last.values())
        okr = [r for r in rows if r.get("status") in ("ok", "파싱실패")]
        mis = sum(1 for r in okr if ph.get((task, r["unit"])) not in (None, r["prompt_hash"]))
        nomodel = sum(1 for r in okr if not any(u.startswith(f"claude-{model}-5-5") for u in r.get("model_실제", [])))
        stops = Counter(r.get("stop") for r in okr)
        n = len(okr) or 1
        cost = sum((r.get("cost_표시") or 0) for r in okr)
        tot["호출"] += len(rows)
        tot["입력"] += sum(r.get("in_tok") or 0 for r in okr)
        tot["출력"] += sum(r.get("out_tok") or 0 for r in okr)
        tot["비용"] += cost
        tot["초"] += sum(r.get("sec") or 0 for r in okr)
        L.append(f"| {task} | {model} | {run[3:]} | {len(rows)} | {st['ok']} | {st['파싱실패']} | {st['호출실패']} | {sum(r.get('in_tok') or 0 for r in okr) / n:,.0f} | "
                 f"{sum(r.get('out_tok') or 0 for r in okr) / n:,.0f} | {sum(r.get('sec') or 0 for r in okr) / n:.1f} | {max([r.get('sec') or 0 for r in okr] or [0]):.1f} | {mis} | {nomodel} | {dict(stops)} | {cost:.2f} |")
    L += ["", f"- 합: 기록 줄 {tot['호출']:,} · 입력 {tot['입력']:,} · 출력 {tot['출력']:,} 토큰 · 호출 시간 합 {tot['초'] / 60:.1f}분 · 표시 비용 {tot['비용']:.2f}달러(구독 실행 — 청구액 아님)", ""]


def all_():
    G5.mkdir(parents=True, exist_ok=True)
    kc, ks, kj = keys()
    L = ["# 9편 실험 5단계 — 집계(채점기 `scripts/ep09_grade5.py all` 이 낸 값)", "",
         "비율 = 윌슨 95% 구간. 주 표 = 답이 온 문서만(파싱 실패는 분모에서 뺌), 보조 = 파싱 실패에서 마지막 JSON 객체 채택.", ""]
    main_rows = []
    # ---- C5
    L += ["## C5 정정 공시 비교", "", f"- 대상 문서 {kc['rcept_no'].nunique()}건 · 정답 값 짝 {len(kc)}개", "",
          "| 모델 | 판 | 답 온 문서 | **짝 재현율** | 문서 전부 찾음 | 뒤바뀜 | 한쪽만 맞음 | 없음 | 모델 객체 수(문서당) | 원문에 없는 값이 든 객체 |",
          "|---|---|---:|---|---|---:|---:|---:|---|---|"]
    ov = {}
    for m in MODELS:
        for sal in (False, True):
            g = grade_task("C5", m, 1, sal)
            if not g["ans"]:
                continue
            P, Eo = g["pairs"], g["ents"]
            if P.empty:
                continue
            c = Counter(P["결과"])
            docs_all = P.groupby("rcept_no")["결과"].apply(lambda s: (s == "찾음").all())
            ne = len(Eo)
            nbad = int((Eo["원문에_없는_값"] != "").sum()) if ne else 0
            L.append(f"| {m} | {'보조' if sal else '주'} | {P['rcept_no'].nunique()}/{kc['rcept_no'].nunique()} | {pct(c['찾음'], len(P))} | {pct(int(docs_all.sum()), len(docs_all))} | "
                     f"{c['뒤바뀜']} | {c['한쪽만 맞음']} | {c['없음']} | {ne} ({ne / max(1, P['rcept_no'].nunique()):.1f}) | {pct(nbad, ne)} |")
            if not sal:
                ov[m] = (c["찾음"], len(P))
                main_rows.append({"과제": "C5", "지표": "짝 재현율", "모델": m, "k": c["찾음"], "n": len(P)})
                P.to_csv(G5 / f"C5_{m}_짝.csv", index=False, encoding="utf-8-sig")
                Eo.to_csv(G5 / f"C5_{m}_객체.csv", index=False, encoding="utf-8-sig")
    L += ["", "- 짝 재현율: " + overlap_note(ov), ""]
    # 형별
    L += ["| 모델 | 날짜 짝 | 숫자 짝 | '-'로 바뀐 짝 |", "|---|---|---|---|"]
    kk = kc.assign(갈래=["'-'로" if a == "빈" else ("날짜" if b == "date" else "숫자") for a, b in zip(kc["후_형"], kc["전_형"])])
    for m in MODELS:
        f = G5 / f"C5_{m}_짝.csv"
        if not f.exists():
            continue
        P = pd.read_csv(f, dtype=str).merge(kk[["rcept_no", "짝", "갈래"]], on=["rcept_no", "짝"])
        cells = [pct(int((g["결과"] == "찾음").sum()), len(g)) for g in (P[P["갈래"] == x] for x in ("날짜", "숫자", "'-'로"))]
        L.append(f"| {m} | " + " | ".join(cells) + " |")
    L.append("")

    # ---- J5
    L += ["## J5 판단과 근거", "", f"- 문서 {kj['rcept_no'].nunique()}건 · 문항 {len(kj)}(정답 {dict(Counter(kj['정답']))})", "",
          "| 모델 | 판 | 답 온 문항 | **답 정답률** | **인용 원문 일치** | 정답 + 인용 일치 | 근거 없음 | 줄임표로 이어 붙임 | 형식 밖·답 없음 |",
          "|---|---|---:|---|---|---|---:|---:|---:|"]
    ovj, ovq = {}, {}
    for m in MODELS:
        for sal in (False, True):
            g = grade_task("J5", m, 1, sal)
            I = g.get("items")
            if I is None or I.empty:
                continue
            n = len(I)
            ok = int(I["정오"].sum())
            qn = int((~I["인용"].isin(["근거 없음", "답 없음"])).sum())
            qk = int((I["인용"] == "일치").sum())
            both = int(((I["정오"] == 1) & (I["인용"] == "일치")).sum())
            L.append(f"| {m} | {'보조' if sal else '주'} | {n}/{len(kj)} | {pct(ok, n)} | {pct(qk, qn)} | {pct(both, n)} | {int((I['인용'] == '근거 없음').sum())} | "
                     f"{int((I['인용'] == '줄임표로 이어 붙임').sum())} | {int(I['답'].isin(['형식 밖', '답 없음']).sum())} |")
            if not sal:
                ovj[m], ovq[m] = (ok, n), (qk, qn)
                main_rows += [{"과제": "J5", "지표": "답 정답률", "모델": m, "k": ok, "n": n}, {"과제": "J5", "지표": "인용 일치", "모델": m, "k": qk, "n": qn}]
                I.to_csv(G5 / f"J5_{m}_문항.csv", index=False, encoding="utf-8-sig")
    L += ["", "- 답 정답률: " + overlap_note(ovj), "- 인용 일치: " + overlap_note(ovq), ""]
    L += ["### J5 갈래별 정답률(주)", "", "| 갈래 | " + " | ".join(MODELS) + " |", "|---|" + "---|" * len(MODELS)]
    J = {m: pd.read_csv(G5 / f"J5_{m}_문항.csv", dtype=str).fillna("") for m in MODELS if (G5 / f"J5_{m}_문항.csv").exists()}
    groups = [("출처 = 상수", lambda d: d["출처"] == "상수"), ("출처 = 칸", lambda d: d["출처"] == "칸")] + \
             [(f"정답 = {a}", (lambda a_: lambda d: d["정답"] == a_)(a)) for a in ("예", "아니오", "판단 불가")]
    for name, fn in groups:
        cells = []
        for m in MODELS:
            if m in J:
                d = J[m][fn(J[m])]
                cells.append(pct(int((d["정오"] == "1").sum()), len(d)))
        L.append(f"| {name} | " + " | ".join(cells) + " |")
    L += ["", "### J5 답 분포(정답 × 모델 답, 주)", ""]
    for m in J:
        ct = pd.crosstab(J[m]["정답"], J[m]["답"])
        L += [f"- {m}: " + " / ".join(f"정답 {i} → " + ", ".join(f"{c} {int(ct.loc[i, c])}" for c in ct.columns if ct.loc[i, c]) for i in ct.index)]
    L += ["", "### J5 종류 × 문항 정답률(주)", "", "| 종류 | 문항 | 출처 | 정답(예/아니오/불가) | " + " | ".join(MODELS) + " |", "|---|---|---|---|" + "---|" * len(MODELS)]
    for (kind, jid), g in kj.groupby(["kind", "문항"], sort=False):
        c = Counter(g["정답"])
        cells = []
        for m in MODELS:
            if m in J:
                d = J[m][(J[m]["kind"] == kind) & (J[m]["문항"] == jid)]
                cells.append(f"{int((d['정오'] == '1').sum())}/{len(d)}")
        L.append(f"| {kind} | {jid} | {g['출처'].iloc[0]} | {c['예']}/{c['아니오']}/{c['판단 불가']} | " + " | ".join(cells) + " |")
    L.append("")

    # ---- S5
    s5 = pd.read_csv(T5 / "S5J5_표본.csv", dtype=str, encoding="utf-8-sig")
    L += ["## S5 요약", "", f"- 문서 {len(s5)}건 · 핵심 칸 {len(ks)}(숫자 {int((ks['형'] == 'num').sum())} · 날짜 {int((ks['형'] == 'date').sum())})", "",
          "| 모델 | 판 | 답 온 문서 | 요약 속 수 | 그대로 | 환산 | 어림 | **원문에 없는 수** | **원문에 없는 수가 든 요약** | **핵심 칸(엄격)** | 핵심 칸(관용) | 글자 평균 | 3문장 넘음 |",
          "|---|---|---:|---:|---:|---:|---:|---|---|---|---|---:|---:|"]
    ovs, ovd, ovk = {}, {}, {}
    for m in MODELS:
        for sal in (False, True):
            g = grade_task("S5", m, 1, sal)
            S = g.get("sum")
            if S is None or S.empty:
                continue
            nt = int(S["수"].sum())
            nb = int(S["원문에없음"].sum())
            db = int((S["원문에없음"] > 0).sum())
            K = g["keys"]
            L.append(f"| {m} | {'보조' if sal else '주'} | {len(S)}/{len(s5)} | {nt} | {int(S['그대로'].sum())} | {int(S['환산'].sum())} | {int(S['어림'].sum())} | {pct(nb, nt)} | "
                     f"{pct(db, len(S))} | {pct(int(K['엄격'].sum()), len(K))} | {pct(int(K['관용'].sum()), len(K))} | {S['글자수'].mean():.0f} | {int((S['문장수'] > 3).sum())} |")
            if not sal:
                ovs[m], ovd[m], ovk[m] = (nb, nt), (db, len(S)), (int(K["엄격"].sum()), len(K))
                main_rows += [{"과제": "S5", "지표": "원문에 없는 수(수 단위)", "모델": m, "k": nb, "n": nt},
                              {"과제": "S5", "지표": "원문에 없는 수가 든 요약", "모델": m, "k": db, "n": len(S)},
                              {"과제": "S5", "지표": "핵심 칸 포함(엄격)", "모델": m, "k": int(K["엄격"].sum()), "n": len(K)}]
                S.to_csv(G5 / f"S5_{m}_요약.csv", index=False, encoding="utf-8-sig")
                g["toks"].to_csv(G5 / f"S5_{m}_수.csv", index=False, encoding="utf-8-sig")
                K.to_csv(G5 / f"S5_{m}_칸.csv", index=False, encoding="utf-8-sig")
    L += ["", "- 원문에 없는 수(수 단위): " + overlap_note(ovs), "- 원문에 없는 수가 든 요약: " + overlap_note(ovd), "- 핵심 칸(엄격): " + overlap_note(ovk), ""]
    L += ["### S5 핵심 칸 — 형별(엄격)", "", "| 모델 | 숫자 칸 | 날짜 칸 |", "|---|---|---|"]
    for m in MODELS:
        f = G5 / f"S5_{m}_칸.csv"
        if f.exists():
            K = pd.read_csv(f, dtype=str)
            L.append(f"| {m} | " + " | ".join(pct(int((K[K['형'] == t]['엄격'] == '1').sum()), int((K['형'] == t).sum())) for t in ("num", "date")) + " |")
    L.append("")

    # ---- 재실행
    L += ["## 재실행 — J5 Sonnet 60건 3회", ""]
    rer = json.loads((T5 / "재실행_J5.json").read_text(encoding="utf-8"))
    runs = {}
    for run in (1, 2, 3):
        g = grade_task("J5", "sonnet", run)
        I = g.get("items")
        if I is not None and not I.empty:
            runs[run] = I[I["rcept_no"].isin(rer)].set_index(["rcept_no", "문항"])
    if len(runs) == 3:
        common = runs[1].index.intersection(runs[2].index).intersection(runs[3].index)
        a = [tuple(runs[r].loc[i, "답"] for r in (1, 2, 3)) for i in common]
        q = [tuple(runs[r].loc[i, "근거"] for r in (1, 2, 3)) for i in common]
        same_a = sum(1 for x in a if len(set(x)) == 1)
        same_q = sum(1 for x in q if len(set(x)) == 1)
        pat = Counter("/".join(x) for x in a if len(set(x)) > 1)
        L += [f"- 세 번 모두 답이 온 문항 {len(common)}(문서 {len(set(i[0] for i in common))})",
              f"- 세 번 모두 같은 답: {pct(same_a, len(common))}",
              f"- 세 번 모두 같은 근거 글: {pct(same_q, len(common))}",
              "- 실행별 정답률: " + " / ".join(pct(int(runs[r].loc[common, '정오'].astype(int).sum()), len(common), False) for r in (1, 2, 3)),
              "- 실행별 인용 일치: " + " / ".join(pct(int((runs[r].loc[common, '인용'] == '일치').sum()), len(common), False) for r in (1, 2, 3)),
              "- 갈린 답 무늬(run1/run2/run3): " + ", ".join(f"{k} {v}" for k, v in pat.most_common(8)), ""]
    else:
        L += [f"- 실행 {sorted(runs)} 만 있음", ""]
    call_table(L)
    pd.DataFrame(main_rows).to_csv(G5 / "주표_지표.csv", index=False, encoding="utf-8-sig")
    (G5 / "집계_5단계.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ================================================================ 시험(가짜 답)
def selftest():
    kc, ks, kj = keys()
    ok = True
    # C5: 정답 그대로 → 전부 찾음 · 뒤집으면 뒤바뀜 · 빈 답 → 없음
    for rcp, g in list(kc.groupby("rcept_no"))[:5]:
        perfect = {"바뀐것": [{"항목": r.항목, "정정전": r.전_원문, "정정후": r.후_원문} for r in g.itertuples()]}
        swapped = {"바뀐것": [{"항목": r.항목, "정정전": r.후_원문, "정정후": r.전_원문} for r in g.itertuples()]}
        p1, e1 = grade_c5_doc(rcp, perfect, g)
        p2, _ = grade_c5_doc(rcp, swapped, g)
        p3, _ = grade_c5_doc(rcp, {"바뀐것": []}, g)
        ok &= all(x["결과"] == "찾음" for x in p1) and all(x["결과"] == "뒤바뀜" for x in p2) and all(x["결과"] == "없음" for x in p3)
        ok &= all(x["원문에_없는_값"] == "" for x in e1)
        fake = {"바뀐것": [{"항목": "x", "정정전": "987,654,321,987", "정정후": "2099년 1월 1일"}]}
        _, e4 = grade_c5_doc(rcp, fake, g)
        ok &= e4[0]["원문에_없는_값"] == "전·후"
    print("C5 시험", ok)
    # S5: 핵심 칸 값을 그대로 쓴 요약 → 엄격 100% · 원문에 없음 0 / 지어낸 수 → 원문에 없음
    for rcp, g in list(ks.groupby("rcept_no"))[:5]:
        parts = []
        for r in g.itertuples():
            if r.형 == "num":
                parts.append(f"{r.질문이름}은 {Decimal(r.정답):,}")
            else:
                parts.append(f"{r.질문이름}은 {r.정답[:4]}년 {int(r.정답[4:6])}월 {int(r.정답[6:])}일")
        srow, trows, krows = grade_s5_doc(rcp, {"요약": ", ".join(parts) + "이다."}, g)
        ok2 = srow["핵심칸_엄격"] == srow["핵심칸"]
        srow2, _, _ = grade_s5_doc(rcp, {"요약": "총 98,765,432,101원(9876억 5432만 원)을 2099년 3월 7일에 쓴다."}, g)
        ok2 &= srow2["원문에없음"] == 3
        if not ok2:
            print("  S5 실패", rcp, srow, srow2, [t for t in trows if t["분류"] == "원문에 없음"][:5])
        ok &= ok2
    t, idx = doc(ks["rcept_no"].iloc[0])
    toks = summary_tokens("12억 300만 원, 약 2.5억 원, 3,400만 주, 7.89%, 2026년 3월 4일, 6월 7일, 2026년 8월")
    print("  토큰:", [(x["형"], T.fmtv(("num", x["값"])) if x["형"] == "num" else x["값"]) for x in toks])
    print("S5 시험", ok)
    # J5: 정답 + 원문 첫 줄 인용 → 정오 1 · 일치 / 바꾼 인용 → 불일치
    for rcp, g in list(kj.groupby("rcept_no"))[:5]:
        t, idx = doc(rcp)
        line = [ln for ln in t.splitlines() if len(ln) > 8][3]
        good = {r.문항: {"답": r.정답, "근거": line} for r in g.itertuples()}
        bad = {r.문항: {"답": "예" if r.정답 != "예" else "아니오", "근거": line + "라고 적혀 있다"} for r in g.itertuples()}
        r1 = grade_j5_doc(rcp, good, g)
        r2 = grade_j5_doc(rcp, bad, g)
        ok &= all(x["정오"] == 1 and x["인용"] == "일치" for x in r1) and all(x["정오"] == 0 and x["인용"] == "불일치" for x in r2)
    print("J5 시험", ok)
    print("전체", "통과" if ok else "실패")


if __name__ == "__main__":
    {"all": all_, "selftest": selftest}[sys.argv[1] if len(sys.argv) > 1 else "all"]()
