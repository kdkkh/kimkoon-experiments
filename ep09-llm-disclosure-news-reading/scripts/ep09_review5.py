# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 5단계 — 원문 대조 자료 · 화면용 실례 뽑기 (2026-11-18, 실행 전에 정해 둔 규칙대로). 파일만 읽는다.

  python -X utf8 scripts/ep09_review5.py review     # → 채점5/대조_<과제>.md (과제마다 최대 20건, 모델별 고르게, 시드 20261118)
  python -X utf8 scripts/ep09_review5.py examples   # → 채점5/실례_<과제>.md (세 모델 답이 서로 다른 공시 3건)
"""
from __future__ import annotations

import bisect
import json
import random
import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
import ep09_run as R  # noqa: E402
import ep09_grade5 as G  # noqa: E402
import ep09_tasks5 as T  # noqa: E402

EP09 = DATA / "ep09"
T5 = EP09 / "과제5"
G5 = EP09 / "채점5"
MODELS = ("haiku", "sonnet", "opus")
SEED = 20261118
MAXN = 20


class Doc:
    def __init__(self, rcp: str):
        self.text, _ = R.doc_text(rcp)
        self.lines = self.text.splitlines()
        self.starts, flat = [], []
        pos = 0
        for ln in self.lines:
            self.starts.append(pos)
            f = re.sub(r"\s+", "", ln)
            flat.append(f)
            pos += len(f)
        self.flat = "".join(flat)

    def line_of(self, s: str) -> list[int]:
        """공백 뺀 글 s 가 든 줄 번호(1부터) — 처음 3곳."""
        q = re.sub(r"\s+", "", str(s or ""))
        out, i = [], 0
        while q and len(out) < 3:
            j = self.flat.find(q, i)
            if j < 0:
                break
            out.append(bisect.bisect_right(self.starts, j))
            i = j + 1
        return out

    def ctx(self, ln: int, a: int = 3, b: int = 3) -> str:
        lo, hi = max(1, ln - a), min(len(self.lines), ln + b)
        return "\n".join(f"{k:>5}| {self.lines[k - 1][:160]}" for k in range(lo, hi + 1))


def fmt_num(v: str) -> list[str]:
    try:
        d = Decimal(v)
    except Exception:
        return [v]
    s = format(d, "f")
    if "." in s:
        ip, fp = s.split(".")
        return [f"{int(ip):,}.{fp}", s]
    return [f"{int(d):,}", s]


def fmt_date(v: str) -> list[str]:
    y, m, d = v[:4], v[4:6], v[6:]
    return [f"{y}년 {m}월 {d}일", f"{y}년 {int(m)}월 {int(d)}일", f"{y}.{m}.{d}", f"{y}-{m}-{d}"]


def results(task: str, model: str, run: int = 1) -> dict:
    return {u: r for u, r in R.latest(EP09 / "run5" / f"{task}_{model}_run{run}.jsonl", "unit").items()}


def spread(items: list[dict]) -> list[dict]:
    """모델별로 섞은 뒤 돌아가며 뽑기(최대 MAXN)."""
    rng = random.Random(SEED)
    by = {m: [x for x in items if x["모델"] == m] for m in MODELS}
    for m in by:
        rng.shuffle(by[m])
    out = []
    while len(out) < MAXN and any(by.values()):
        for m in MODELS:
            if by[m] and len(out) < MAXN:
                out.append(by[m].pop())
    return out


def review():
    kj = pd.read_csv(T5 / "정답_J5.csv", dtype=str, encoding="utf-8-sig").fillna("")
    kjq = pd.read_csv(T5 / "J5_질문.csv", dtype=str, encoding="utf-8-sig").fillna("")
    qtext = {(r.kind, r.문항): r.질문 for r in kjq.itertuples()}
    used = {(r.rcept_no, r.문항): r.쓴_칸 for r in kj.itertuples()}
    ks = pd.read_csv(T5 / "정답_S5_칸.csv", dtype=str, encoding="utf-8-sig").fillna("")
    # ---- C5
    items = []
    for m in MODELS:
        P = pd.read_csv(G5 / f"C5_{m}_짝.csv", dtype=str).fillna("")
        for r in P[P["결과"] != "찾음"].itertuples():
            items.append({"모델": m, "갈래": f"정답 짝 {r.결과}", "rcept_no": r.rcept_no, "짝": r.짝, "항목": r.항목, "전": r.전_원문, "후": r.후_원문})
        Eo = pd.read_csv(G5 / f"C5_{m}_객체.csv", dtype=str).fillna("")
        for r in Eo[Eo["원문에_없는_값"] != ""].itertuples():
            items.append({"모델": m, "갈래": f"원문에 없는 값({r.원문에_없는_값})", "rcept_no": r.rcept_no, "짝": f"객체{r.객체}", "항목": r.항목, "전": r.정정전, "후": r.정정후})
    pick = spread(items)
    L = ["# C5 원문 대조 자료", "", f"불일치 전체 {len(items)}건(모델별 {dict(Counter(x['모델'] for x in items))}) 중 {len(pick)}건", ""]
    for i, x in enumerate(pick, 1):
        d = Doc(x["rcept_no"])
        res = results("C5", x["모델"])[x["rcept_no"]]
        L += [f"## {i}. {x['모델']} · {x['rcept_no']} · {x['갈래']} · {x['짝']}", "", f"- 항목: {x['항목']} · 전: `{x['전']}` · 후: `{x['후']}`", "",
              "모델 답 전문:", "", "```", res.get("result", "")[:3000], "```", ""]
        for v in (x["전"], x["후"]):
            for ln in d.line_of(v)[:1]:
                L += ["```", d.ctx(ln, 4, 4), "```", ""]
    (G5 / "대조_C5.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    # ---- S5
    items = []
    for m in MODELS:
        if not (G5 / f"S5_{m}_수.csv").exists():
            continue
        Tk = pd.read_csv(G5 / f"S5_{m}_수.csv", dtype=str).fillna("")
        for r in Tk[Tk["분류"] == "원문에 없음"].itertuples():
            items.append({"모델": m, "rcept_no": r.rcept_no, "글": r.글, "값": r.값, "형": r.형})
    pick = spread(items)
    L = ["# S5 원문 대조 자료(원문에 없는 수)", "", f"전체 {len(items)}건(모델별 {dict(Counter(x['모델'] for x in items))}) 중 {len(pick)}건", ""]
    for i, x in enumerate(pick, 1):
        res = results("S5", x["모델"])[x["rcept_no"]]
        kf = ks[ks["rcept_no"] == x["rcept_no"]]
        L += [f"## {i}. {x['모델']} · {x['rcept_no']} · 수 `{x['글']}` (= {x['값']}, {x['형']})", "", "요약:", "", "> " + str((res.get("answer") or {}).get("요약", ""))[:1500], "",
              "핵심 칸: " + " · ".join(f"{r.질문이름}={r.정답}" for r in kf.itertuples()), ""]
        d = Doc(x["rcept_no"])
        digits = re.sub(r"\D", "", x["값"])[:3]
        hits = [k + 1 for k, ln in enumerate(d.lines) if digits and digits in re.sub(r"\D", "", ln)][:4]
        for ln in hits:
            L += ["```", d.ctx(ln, 1, 1), "```", ""]
    (G5 / "대조_S5.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    # ---- J5
    items = []
    for m in MODELS:
        I = pd.read_csv(G5 / f"J5_{m}_문항.csv", dtype=str).fillna("")
        for r in I[(I["정오"] == "0") | (I["인용"] == "불일치")].itertuples():
            gal = ("오답" if r.정오 == "0" else "") + ("+" if r.정오 == "0" and r.인용 == "불일치" else "") + ("인용 불일치" if r.인용 == "불일치" else "")
            items.append({"모델": m, "갈래": gal, "rcept_no": r.rcept_no, "kind": r.kind, "문항": r.문항, "정답": r.정답, "답": r.답, "근거": r.근거})
    pick = spread(items)
    L = ["# J5 원문 대조 자료(오답 · 인용 불일치)", "", f"전체 {len(items)}건(모델별 {dict(Counter(x['모델'] for x in items))}, 갈래 {dict(Counter(x['갈래'] for x in items))}) 중 {len(pick)}건", ""]
    for i, x in enumerate(pick, 1):
        d = Doc(x["rcept_no"])
        L += [f"## {i}. {x['모델']} · {x['rcept_no']} · {x['kind']} {x['문항']} · {x['갈래']}", "",
              f"- 질문: {qtext[(x['kind'], x['문항'])]}", f"- 정답 {x['정답']} · 모델 {x['답']} · 쓴 칸: {used.get((x['rcept_no'], x['문항']), '')}", f"- 근거: `{x['근거']}`", ""]
        lns = d.line_of(x["근거"])
        if not lns and x["근거"]:
            frag = re.sub(r"\s+", "", x["근거"])[:12]
            lns = d.line_of(frag)
        for ln in lns[:1]:
            L += ["```", d.ctx(ln, 3, 3), "```", ""]
        for c in re.findall(r"([a-z_]+)=([^ ·]+)", used.get((x["rcept_no"], x["문항"]), "")):
            v = c[1]
            cands = fmt_date(v) if re.fullmatch(r"\d{8}", v) and v.startswith("20") else fmt_num(v)
            for cv in cands:
                got = d.line_of(cv)
                if got:
                    L += [f"{c[0]}:", "```", d.ctx(got[0], 2, 1), "```", ""]
                    break
    (G5 / "대조_J5.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("대조 자료 씀")


def examples():
    kc = pd.read_csv(T5 / "정답_C5.csv", dtype=str, encoding="utf-8-sig").fillna("")
    kj = pd.read_csv(T5 / "정답_J5.csv", dtype=str, encoding="utf-8-sig").fillna("")
    kjq = pd.read_csv(T5 / "J5_질문.csv", dtype=str, encoding="utf-8-sig").fillna("")
    qtext = {(r.kind, r.문항): r.질문 for r in kjq.itertuples()}
    ks = pd.read_csv(T5 / "정답_S5_칸.csv", dtype=str, encoding="utf-8-sig").fillna("")
    res = {t: {m: results(t, m) for m in MODELS} for t in ("C5", "S5", "J5")}

    def dump(task, rcp, L, extra_lines):
        d = Doc(rcp)
        for m in MODELS:
            r = res[task][m].get(rcp, {})
            L += [f"**{m}** ({r.get('status', '없음')}):", "", "```", str(r.get("result", ""))[:4000], "```", ""]
        L += ["원문 해당 대목(모델이 받은 글의 줄 번호):", ""]
        for name, ln in extra_lines(d):
            L += [f"- {name}: {ln}번 줄", "", "```", d.ctx(ln, 2, 2), "```", ""]

    # C5
    P = {m: pd.read_csv(G5 / f"C5_{m}_짝.csv", dtype=str) for m in MODELS}
    cand = []
    for rcp, g in kc.groupby("rcept_no"):
        cnt = tuple(int(((P[m]["rcept_no"] == rcp) & (P[m]["결과"] == "찾음")).sum()) for m in MODELS)
        if len(set(cnt)) > 1:
            cand.append((-len(set(cnt)), -len(g), rcp, cnt))
    cand.sort()
    n_first = len(cand)
    if len(cand) < 3:          # 등록 뒤 더함: 찾은 짝 수로 갈린 문서가 3건이 안 되면, 적은 객체(바뀐 것) 수가 모델끼리 다른 문서로 채움
        Eo = {m: pd.read_csv(G5 / f"C5_{m}_객체.csv", dtype=str) for m in MODELS}
        more = []
        for rcp, g in kc.groupby("rcept_no"):
            if any(c[2] == rcp for c in cand):
                continue
            cnt = tuple(int((Eo[m]["rcept_no"] == rcp).sum()) for m in MODELS)
            if len(set(cnt)) > 1:
                more.append((-len(set(cnt)), -len(g), rcp, cnt))
        more.sort()
        cand += [(a, b, r, ("객체 수",) + c) for a, b, r, c in more[:3 - len(cand)]]
    L = ["# C5 실례 — 세 모델 답이 다른 정정 공시", "",
         f"찾은 짝 수가 모델끼리 다른 문서 {n_first}건(실행 전에 정한 순서). 3건이 안 돼 나머지는 '모델이 적은 객체 수가 셋 다 다른 문서'에서 정답 짝 수가 많은 순으로 채움(등록 뒤 더함). "
         "객체 수로 고른 문서의 제목 줄 숫자는 haiku/sonnet/opus 의 객체 수다.", ""]
    for _, _, rcp, cnt in cand[:3]:
        g = kc[kc["rcept_no"] == rcp]
        lab = "객체 수" if cnt[0] == "객체 수" else "찾은 짝"
        cnt = cnt[1:] if cnt[0] == "객체 수" else cnt
        L += [f"## {rcp} · {g['kind'].iloc[0]} · 정답 짝 {len(g)} · {lab} haiku/sonnet/opus = {cnt[0]}/{cnt[1]}/{cnt[2]}", "",
              "정답 짝: " + " / ".join(f"{r.항목}: {r.전_원문} → {r.후_원문}" for r in g.itertuples()), ""]
        dump("C5", rcp, L, lambda d: [("정정사항 표", (d.line_of("3.정정사항") or d.line_of("정정사항") or [1])[0])] +
             [(f"{r.항목[:20]} 정정 후 값", (d.line_of(r.후_원문) or [0])[0]) for r in g.itertuples() if d.line_of(r.후_원문)][:3])
    (G5 / "실례_C5.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    # S5
    S = {m: pd.read_csv(G5 / f"S5_{m}_요약.csv", dtype=str).set_index("rcept_no") for m in MODELS}
    cand = []
    for rcp in S["sonnet"].index:
        if not all(rcp in S[m].index for m in MODELS):
            continue
        v = [(int(S[m].loc[rcp, "원문에없음"]), int(S[m].loc[rcp, "핵심칸_엄격"])) for m in MODELS]
        if len(set(v)) > 1:
            ks_ = [x[1] for x in v]
            cand.append((-len(set(v)), -(max(ks_) - min(ks_)), rcp, v))
    cand.sort()
    L = ["# S5 실례 — 세 모델 요약이 다른 공시", "", f"후보 {len(cand)}건 중 앞 3건. (원문에 없는 수, 핵심 칸 엄격) haiku/sonnet/opus 를 적음.", ""]
    for _, _, rcp, v in cand[:3]:
        kf = ks[ks["rcept_no"] == rcp]
        L += [f"## {rcp} · {kf['kind'].iloc[0]} · 핵심 칸 {len(kf)} · " + " / ".join(f"{m} 없는 수 {a} · 칸 {b}" for m, (a, b) in zip(MODELS, v)), "",
              "핵심 칸: " + " · ".join(f"{r.질문이름}={r.정답}" for r in kf.itertuples()), ""]
        for m in MODELS:
            tk = pd.read_csv(G5 / f"S5_{m}_수.csv", dtype=str).fillna("")
            bad = tk[(tk["rcept_no"] == rcp) & (tk["분류"] == "원문에 없음")]["글"].tolist()
            L.append(f"- {m} 원문에 없는 수: {bad}")
        L.append("")

        def lines_s5(d, kf=kf):
            out = []
            for r in kf.itertuples():
                for cv in (fmt_date(r.정답) if r.형 == "date" else fmt_num(r.정답)):
                    got = d.line_of(cv)
                    if got:
                        out.append((r.질문이름, got[0]))
                        break
            return out[:4]
        dump("S5", rcp, L, lines_s5)
    (G5 / "실례_S5.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    # J5
    J = {m: pd.read_csv(G5 / f"J5_{m}_문항.csv", dtype=str).fillna("").set_index(["rcept_no", "문항"]) for m in MODELS}
    cand = []
    for rcp, g in kj[kj["뺀_이유"] == ""].groupby("rcept_no"):
        n3 = n2 = 0
        for jid in g["문항"]:
            k_ = (rcp, jid)
            if not all(k_ in J[m].index for m in MODELS):
                continue
            a = {J[m].loc[k_, "답"] for m in MODELS}
            n3 += len(a) == 3
            n2 += len(a) == 2
        if n3 or n2:
            cand.append((-n3, -n2, rcp))
    cand.sort()
    L = ["# J5 실례 — 세 모델 판단이 다른 공시", "", f"후보(한 문항이라도 답이 갈린 문서) {len(cand)}건 · 세 답이 다 다른 문항이 있는 문서 {sum(1 for c in cand if c[0] < 0)}건 → 앞 3건.", ""]
    for n3, n2, rcp in cand[:3]:
        g = kj[(kj["rcept_no"] == rcp) & (kj["뺀_이유"] == "")]
        kind = g["kind"].iloc[0]
        L += [f"## {rcp} · {kind} · 세 답이 다 다른 문항 {-n3} · 둘로 갈린 문항 {-n2}", ""]
        for r in g.itertuples():
            L.append(f"- {r.문항} {qtext[(kind, r.문항)]} — 정답 **{r.정답}** · " + " · ".join(f"{m} {J[m].loc[(rcp, r.문항), '답']}({J[m].loc[(rcp, r.문항), '인용']})" for m in MODELS if (rcp, r.문항) in J[m].index))
        L.append("")

        def lines_j5(d, rcp=rcp, g=g):
            out = []
            for r in g.itertuples():
                for m in MODELS:
                    if (rcp, r.문항) in J[m].index:
                        q = J[m].loc[(rcp, r.문항), "근거"]
                        got = d.line_of(q)
                        if got:
                            out.append((f"{r.문항} {m} 근거", got[0]))
            seen, uniq = set(), []
            for nm, ln in out:
                if ln not in seen:
                    seen.add(ln)
                    uniq.append((nm, ln))
            return uniq[:5]
        dump("J5", rcp, L, lines_j5)
    (G5 / "실례_J5.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("실례 씀")


if __name__ == "__main__":
    {"review": review, "examples": examples}[sys.argv[1]]()
