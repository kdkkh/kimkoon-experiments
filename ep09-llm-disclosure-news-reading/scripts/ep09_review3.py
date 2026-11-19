# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 3단계 — 불일치 건 원문 대조용 자료 뽑기 (2026-11-17). 모델 호출 없음.

사전 등록(실행 전에 파일로 못 박은 규칙)대로: 어려운 읽기(H1~H5)의 불일치(오답·답 없음·빈 칸 값 채움)를 과제마다 최대 30건,
30건이 넘으면 고정 시드(20261117+40)로 모델별 10건씩(모자라면 다른 모델에서 채움) 뽑는다.
뽑은 건마다 질문·정답·답과, 원문에서 관련 값이 나오는 자리의 앞뒤 글을 채점3/대조_<과제>.md 에 적는다(판정은 사람이 읽고 내린다).

쓰기:  python -X utf8 scripts/ep09_review3.py [H1 H2 …]
"""
from __future__ import annotations

import random
import re
import sys
from pathlib import Path

import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
import ep09_grade as G  # noqa: E402
import ep09_run as R  # noqa: E402
import ep09_tasks3 as T  # noqa: E402

EP09 = DATA / "ep09"
OUT3 = EP09 / "채점3"
N_MAX, PER_MODEL = 30, 10


def read_csv(p):
    return pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")


def pick(task: str) -> pd.DataFrame:
    b = read_csv(OUT3 / "불일치_전체.csv")
    b = b[(b["task"] == task) & b["model"].isin(["haiku", "sonnet", "opus"])].sort_values(["model", "rcept_no", "칸"]).reset_index(drop=True)
    if len(b) <= N_MAX:
        return b
    rng = random.Random(T.SEED3 + 40)
    chosen, rest = [], []
    for m in ("sonnet", "haiku", "opus"):
        idx = list(b[b["model"] == m].index)
        rng.shuffle(idx)
        chosen += idx[:PER_MODEL]
        rest += idx[PER_MODEL:]
    rng.shuffle(rest)
    chosen += rest[:N_MAX - len(chosen)]
    return b.loc[sorted(chosen)]


def snippets(text: str, needles: list[str], width: int = 110, limit: int = 4) -> list[str]:
    out, seen = [], set()
    flat = text.replace("\n", " / ")
    for nd in needles:
        if not nd or len(nd) < 2:
            continue
        for m in list(re.finditer(re.escape(nd), flat))[:limit]:
            s = max(0, m.start() - width)
            key = s // 60
            if key in seen:
                continue
            seen.add(key)
            out.append(f"  - 「{nd}」 …{flat[s:m.end() + width]}…")
    return out


def variants(v: str) -> list[str]:
    """숫자 답 → 원문에서 찾을 표기(쉼표 있는 꼴 · 없는 꼴)."""
    x = G.parse_num(v)
    if x is None:
        d, _ = G.parse_date(v)
        if d:
            y, m, dd = d[:4], int(d[4:6]), int(d[6:])
            return [f"{y}년 {m:02d}월 {dd:02d}일", f"{y}.{m:02d}.{dd:02d}", f"{y}-{m:02d}-{dd:02d}"]
        return [str(v)]
    x = abs(x)
    s = format(x.normalize(), "f")
    if "." in s:
        i, f = s.split(".")
        return [f"{int(i):,}.{f}", s]
    return [f"{int(s):,}", s] if len(s) > 3 else [s]


def main():
    tasks = sys.argv[1:] or ["H1", "H2", "H3", "H4", "H5"]
    a3 = read_csv(T.T3 / "정답_A3.csv")
    raw = {(r.rcept_no, r.칸): r.원값 for r in a3.itertuples(index=False)}
    h4 = read_csv(T.T3 / "H4_묶음.csv").set_index("rcept_no")
    for task in tasks:
        b = pick(task)
        q = {}
        if task != "H5":
            src = "A3" if task == "H4" else task
            q = {(r.kind, r.칸): r.질문 for r in read_csv(T.T3 / f"{src}_질문.csv").itertuples(index=False)}
        key = read_csv(T.T3 / f"정답_{task}.csv") if task in ("H2", "H3", "H5") else None
        allb = read_csv(OUT3 / "불일치_전체.csv")
        n_all = int(((allb["task"] == task) & allb["model"].isin(["haiku", "sonnet", "opus"])).sum())
        L = [f"# 3단계 원문 대조 자료 — {task} (불일치 전체 {n_all}건 중 {len(b)}건)", ""]
        for n, r in enumerate(b.itertuples(index=False), 1):
            text = R.doc_text(r.rcept_no)[0]
            kind_res = r.빈칸결과 or r.엄격
            L += [f"## {n}. {r.model} · {r.kind} · {r.rcept_no} · {r.칸} — {kind_res} {('(' + r.오답갈래 + ')') if r.오답갈래 else ''}",
                  f"- 질문: {q.get((r.kind, r.칸), '')}", f"- 정답: `{r.정답 or '∅(빈 칸)'}` · 답: `{r.답_원문}` · 관용: {r.관용} · 다른문서값: {r.다른문서값}"]
            needles = variants(r.답_원문) if r.답_원문 else []
            if task in ("A3", "H1", "H4"):
                needles = [raw.get((r.rcept_no, r.칸), "")] + needles
            elif task == "H2":
                needles = [raw.get((r.rcept_no, r.칸), "")] + needles
            elif task == "H3":
                k = key[(key["rcept_no"] == r.rcept_no) & (key["칸"] == r.칸)].iloc[0]
                L.append(f"- 식: `{k.식}` · 입력: {k.입력} · 반올림 전: {k.정답_반올림전}")
                names = sorted(set(re.findall(r"[a-z][a-z0-9_]+", k.식)) - {"days"})
                needles = [raw.get((r.rcept_no, nm), "") for nm in names] + needles
            elif task == "H5":
                k = key[(key["rcept_no"] == r.rcept_no) & (key["칸"] == r.칸)].iloc[0]
                L.append(f"- 문항: {k.범위} · {k.기간} · {k.항목} · 구조화 값(원 단위) {k.원단위_정답} · 열 {k.재무_열} · 코드 {k.재무_코드}")
                v = int(k.원단위_정답)
                needles = [f"{abs(v):,}", f"{abs(v) // 1000:,}", f"{round(abs(v) / 1e6):,}"] + needles
            sn = snippets(text, needles)
            if task == "H4" and r.다른문서값:
                sn += ["  - (다른 문서 " + r.다른문서값 + ")"] + snippets(R.doc_text(r.다른문서값)[0], variants(r.답_원문), limit=2)
            if task == "H4":
                L.append(f"- 세 문서: {h4.loc[r.rcept_no, '문서1']} · {h4.loc[r.rcept_no, '문서2']} · {h4.loc[r.rcept_no, '문서3']} (대상 위치 {h4.loc[r.rcept_no, '대상_위치']}) · 회사명 {h4.loc[r.rcept_no, '회사명']}")
            L += ["- 원문에서:"] + (sn or ["  - (관련 값의 글자 그대로를 찾지 못함)"]) + [""]
        (OUT3 / f"대조_{task}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        b.to_csv(OUT3 / f"대조_{task}_목록.csv", index=False, encoding="utf-8-sig")
        print(task, "대조 자료", len(b), "건")


if __name__ == "__main__":
    main()
