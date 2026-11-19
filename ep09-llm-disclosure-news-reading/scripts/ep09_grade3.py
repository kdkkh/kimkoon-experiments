# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 3단계 — 채점·집계 (2026-11-17). 결정적 코드만 — 모델·외부 API 를 부르지 않는다.

2단계 채점기(ep09_grade.py)의 정규화·칸 채점·통계 함수를 그대로 쓴다. 3단계에서 더한 것:
  · H2·H3·H5(반올림해 답하는 과제)의 기준:  엄격 = 반올림 규칙대로 낸 정답과 정확히 같음
                                          관용 = 반올림 전 값과의 차가 끝자리 1단위 이하(버림·올림 허용).  2단계의 '상대 오차 0.5%'는 쓰지 않는다.
  · H2 오답 갈래에 '원문 단위 그대로'(환산하지 않고 원·주 값 그대로 답함)
  · H4 '다른 문서 값'(같이 넣은 다른 회사 공시의 같은 칸 값과 같은 답)
  · 정답표는 과제3/정답_*.csv (A3·H1·H4 = 정답_A3: 대조한 정정 칸만 '정정 후 값')

쓰기(이 폴더에서):
  python -X utf8 scripts/ep09_grade3.py selftest     # 정답지를 답으로 넣으면 만점인지
  python -X utf8 scripts/ep09_grade3.py all          # run3/ 에 있는 것 전부 채점 → 채점3/
"""
from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
import ep09_grade as G  # noqa: E402
import ep09_run as R  # noqa: E402
import ep09_tasks3 as T  # noqa: E402

EP09 = DATA / "ep09"
RUN3 = EP09 / "run3"
OUT3 = EP09 / "채점3"
MODELS = ("haiku", "sonnet", "opus")
MNAME = {"haiku": "Haiku 5.5", "sonnet": "Sonnet 5.5", "opus": "Opus 5.5"}
TASKS = ("A3", "H1", "H2", "H3", "H4", "H5")
TNAME = {"A3": "쉬운 읽기(A)", "H1": "H1 말 바꾼 질문", "H2": "H2 단위 바꿔 답하기", "H3": "H3 계산형", "H4": "H4 섞인 문서", "H5": "H5 재무제표(4건)"}
ROUND_TASKS = ("H2", "H3", "H5")


def read_csv(p) -> pd.DataFrame:
    return pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")


def load_key(task: str) -> pd.DataFrame:
    if task in ("A3", "H1", "H4"):
        k = read_csv(T.T3 / "정답_A3.csv")
        if task == "H4":
            h = read_csv(T.T3 / "H4_묶음.csv")
            k = k[k["rcept_no"].isin(h[h["뺀_이유"] == ""]["rcept_no"])]
        return k
    return read_csv(T.T3 / f"정답_{task}.csv")


def load_ans(task: str, model: str, run: int = 1, salvage: bool = False) -> dict[str, dict]:
    """→ 건(문서 또는 묶음) → 답. Sonnet 의 A3 는 2단계 답(대량보유 아닌 246건) + 3단계에서 새로 돌린 대량보유 20건."""
    out = {}
    if task == "A3" and model == "sonnet" and run == 1:
        kinds = read_csv(EP09 / "sample_A.csv").set_index("rcept_no")["kind"].to_dict()
        for r in R.latest(EP09 / "run" / "A_run1.jsonl", "rcept_no").values():
            if r["status"] == "ok" and kinds[r["rcept_no"]] != "majorstock":
                out[r["rcept_no"]] = r["answer"]
    for u, r in R.latest(RUN3 / f"{task}_{model}_run{run}.jsonl", "unit").items():
        if r["status"] == "ok":
            out[u] = r["answer"] if "answer" in r else r["answers"]
        elif salvage and r["status"] == "파싱실패":
            a = salvage_obj(task, r)
            if a is not None:
                out[u] = a
    return out


_KEYS = {}


def keys_of(task: str, r: dict) -> list[str]:
    """질문 번호 순서의 칸 이름(실행기와 같은 순서)."""
    if task == "H5":
        if "H5" not in _KEYS:
            k5 = read_csv(T.T3 / "정답_H5.csv")
            _KEYS["H5"] = {rc: list(g["칸"]) for rc, g in k5.groupby("rcept_no", sort=False)}
        return _KEYS["H5"][r["unit"]]
    src = "A3" if task == "H4" else task
    if src not in _KEYS:
        _KEYS[src] = {kind: [f["칸"] for f in fs] for kind, fs in T.fields_for(src).items()}
    return _KEYS[src][r["kind"]]


def salvage_obj(task: str, r: dict):
    """형식 위반(JSON 객체 하나가 아님)으로 파싱에 실패한 답에서 '마지막 JSON 객체'를 꺼낸다 — 보조 집계용(등록 뒤 추가)."""
    import re as _re
    objs = []
    for m in _re.finditer(r"\{[^{}]*\}", r.get("result") or ""):
        try:
            o = json.loads(m.group(0))
            if isinstance(o, dict) and any(_re.fullmatch(r"q\d\d", k) for k in o):
                objs.append(o)
        except json.JSONDecodeError:
            pass
    if not objs:
        return None
    keys = keys_of(task, r)
    return {c: objs[-1].get(f"q{i:02d}") for i, c in enumerate(keys, 1) if f"q{i:02d}" in objs[-1]}


def grade_doc(task: str, answers: dict[str, dict], key: pd.DataFrame | None = None) -> pd.DataFrame:
    key = load_key(task) if key is None else key
    other = {}
    if task == "H4":                                             # 같이 넣은 다른 두 문서의 같은 칸 정답
        h = read_csv(T.T3 / "H4_묶음.csv").set_index("rcept_no")
        full = read_csv(T.T3 / "정답_A3.csv")
        tv = {(r.rcept_no, r.칸): (r.정답, r.상태, r.형) for r in full.itertuples(index=False)}
        for rcp in key["rcept_no"].unique():
            other[rcp] = [d for d in (h.loc[rcp, "문서1"], h.loc[rcp, "문서2"], h.loc[rcp, "문서3"]) if d != rcp]
    rows = []
    for k in key.itertuples(index=False):
        a = answers.get(k.rcept_no)
        doc_ok = a is not None
        present = bool(doc_ok and k.칸 in a)
        val = a[k.칸] if present else None
        base = {"task": task, "kind": k.kind, "rcept_no": k.rcept_no, "칸": k.칸, "형": k.형, "단위": k.단위, "정답": k.정답, "정답상태": k.상태, "문서답있음": int(doc_ok),
                "답_원문": "" if val is None else (json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val), "다른문서값": ""}
        if k.상태 == "값":
            c = G.grade_cell(k.형, k.단위, k.정답, val, present)
            if task in ROUND_TASKS and c["엄격"] != "답없음" and c["오답갈래"] != "답 해석 못 함":
                a_num, raw = G.parse_num(val), Decimal(k.정답_반올림전)
                unit = Decimal(1).scaleb(-int(k.소수))
                if a_num == Decimal(k.정답):
                    c.update(엄격="정답", 관용="정답", 오답갈래="")
                elif abs(a_num - raw) <= unit:
                    c.update(엄격="오답", 관용="정답", 오답갈래="반올림 차이")
                else:
                    c.update(엄격="오답", 관용="오답")
                    if c["오답갈래"] in ("", "반올림 차이"):
                        c["오답갈래"] = "값 다름"
                    if task in ("H2", "H5") and getattr(k, "원단위_정답", "") and a_num == Decimal(k.원단위_정답) and a_num != Decimal(k.정답):
                        c["오답갈래"] = "원문 단위 그대로"
            base.update(c)
        elif k.상태 == "빈칸":
            base["빈칸결과"] = G.grade_empty(k.형, val, present)
        if task == "H4" and present and not G.is_blank(val) and (base.get("엄격") == "오답" or base.get("빈칸결과") == "값 채움"):
            mine = R.norm_cell(k.형, val)
            for d in other[k.rcept_no]:
                tval, tst, ttp = tv[(d, k.칸)]
                if tst == "값" and tval != k.정답 and R.norm_cell(ttp, tval) == mine:
                    base["다른문서값"] = d
        rows.append(base)
    cells = pd.DataFrame(rows).fillna("")
    for c in ("엄격", "관용", "오답갈래", "빈칸결과", "자릿수일치", "부호일치", "답_정규", "배수_k"):
        if c not in cells:
            cells[c] = ""
    return cells


def pct(k, n, ci=False):
    return G.pct(int(k), int(n), ci)


def summarize(cells: pd.DataFrame) -> dict:
    c = cells[cells["문서답있음"] == 1]
    a = G.agg_a(c)
    docs = G.doc_table(c) if len(c) else pd.DataFrame()
    a["문서"] = len(docs)
    a["문서_대상"] = cells["rcept_no"].nunique()
    a["문서전부_엄격"] = int(docs["전부맞음_엄격"].sum()) if len(docs) else 0
    a["문서전부_엄격빈칸"] = int(docs["전부맞음_엄격+빈칸지킴"].sum()) if len(docs) else 0
    a["다른문서값"] = int((c["다른문서값"] != "").sum())
    v = c[(c["정답상태"] == "값") & (c["엄격"] == "오답")]
    a["오답갈래"] = dict(Counter(v["오답갈래"]).most_common())
    return a


# ================================================================ 읽기 과제 전체
def grade_reading(L: list[str]) -> dict:
    OUT3.mkdir(parents=True, exist_ok=True)
    res, allc = {}, {}
    for task in TASKS:
        for m in MODELS:
            ans = load_ans(task, m)
            if not ans:
                continue
            cells = grade_doc(task, ans)
            cells.insert(0, "model", m)
            cells.to_csv(OUT3 / f"{task}_{m}_칸.csv", index=False, encoding="utf-8-sig")
            res[(task, m)], allc[(task, m)] = summarize(cells), cells
    # 2단계 Sonnet 답(질문 이름 고치기 전)을 3단계 정답표로 다시 채점 — 나란히 보기용
    old = {r["rcept_no"]: r["answer"] for r in R.latest(EP09 / "run" / "A_run1.jsonl", "rcept_no").values() if r["status"] == "ok"}
    c_old = grade_doc("A3", old)
    c_old.insert(0, "model", "sonnet_2단계")
    c_old.to_csv(OUT3 / "A3_sonnet2단계답_칸.csv", index=False, encoding="utf-8-sig")
    res[("A3", "sonnet_2단계")] = summarize(c_old)
    allc[("A3", "sonnet_2단계")] = c_old

    def row(lab, a):
        lo, hi = G.wilson(a["정답_엄격"], a["칸_값"])
        return (f"| {lab} | {a['문서']}/{a['문서_대상']} | {a['칸_값']} | {pct(a['정답_엄격'], a['칸_값'])} [{100 * lo:.1f}~{100 * hi:.1f}] | {pct(a['정답_관용'], a['칸_값'])} | {a['오답_엄격']} | {a['답없음']} | "
                f"{pct(a['빈칸_값채움'], a['칸_빈칸'])} | {a['빈칸_0채움']} | {pct(a['문서전부_엄격'], a['문서'])} | {pct(a['문서전부_엄격빈칸'], a['문서'])} |")
    L += ["## 읽기 과제 — 과제별·모델별(칸 단위, 답이 온 문서만)", "",
          "| 과제 · 모델 | 답 온 문서/대상 | 값 칸 | 정답(엄격) [윌슨 95%] | 정답(관용) | 오답(엄격) | 답 없음 | 빈 칸 값 채움 | 빈 칸 0 채움 | 문서 전부 정답(엄격) | 엄격 + 빈 칸 지킴 |",
          "|---|---|---:|---|---|---:|---:|---|---:|---|---|"]
    for task in TASKS:
        for m in (("sonnet_2단계",) if task == "A3" else ()) + MODELS:
            if (task, m) in res:
                lab = f"{TNAME[task]} · " + ("Sonnet 5.5 — 2단계 답 그대로(대량보유 옛 질문 이름)" if m == "sonnet_2단계" else MNAME[m])
                L.append(row(lab, res[(task, m)]))
    L += ["", "## 읽기 과제 — 형식 위반(JSON 객체 하나가 아니어서 파싱 실패)과, 마지막 JSON 객체를 답으로 채택했을 때(보조)", "",
          "| 과제 · 모델 | 파싱 실패 문서 | 그중 마지막 객체를 꺼낸 문서 | 채택 시 값 칸 | 채택 시 정답(엄격) | 채택 시 정답(관용) | 채택 시 빈 칸 값 채움 | 파싱 실패 문서만: 정답(엄격) |", "|---|---:|---:|---:|---|---|---|---|"]
    for task in TASKS:
        for m in MODELS:
            if (task, m) not in res:
                continue
            fails = [r for r in R.latest(RUN3 / f"{task}_{m}_run1.jsonl", "unit").values() if r["status"] == "파싱실패"]
            if not fails:
                continue
            ans2 = load_ans(task, m, 1, salvage=True)
            c2 = grade_doc(task, ans2)
            c2.insert(0, "model", m)
            c2.to_csv(OUT3 / f"{task}_{m}_칸_마지막객체채택.csv", index=False, encoding="utf-8-sig")
            a2 = summarize(c2)
            got = [r["unit"] for r in fails if r["unit"] in ans2]
            af = G.agg_a(c2[c2["rcept_no"].isin(got)])
            res[(task, m)]["파싱실패"] = len(fails)
            L.append(f"| {TNAME[task]} · {MNAME[m]} | {len(fails)} | {len(got)} | {a2['칸_값']} | {pct(a2['정답_엄격'], a2['칸_값'])} | {pct(a2['정답_관용'], a2['칸_값'])} | {pct(a2['빈칸_값채움'], a2['칸_빈칸'])} | {pct(af['정답_엄격'], af['칸_값'])} |")
    L += ["", "## 읽기 과제 — 값/자릿수/부호 분해와 오답 갈래", "",
          "| 과제 · 모델 | 숫자 칸 답함 | 자릿수 일치 | 부호 일치 | 자릿수만 틀림 | 부호만 틀림 | 반올림 차이 | 답 해석 못 함 | 다른 문서 값(H4) | 오답 갈래 전체 |", "|---|---:|---|---|---:|---:|---:|---:|---:|---|"]
    for (task, m), a in res.items():
        L.append(f"| {TNAME[task]} · {MNAME.get(m, m)} | {a['숫자_답함']} | {pct(a['자릿수_일치'], a['숫자_답함'])} | {pct(a['부호_일치'], a['숫자_답함'])} | {a['오답_자릿수만']} | {a['오답_부호만']} | {a['오답_반올림차이']} | "
                 f"{a['오답_해석못함']} | {a['다른문서값'] if task == 'H4' else '–'} | {', '.join(f'{k or chr(63)} {n}' for k, n in a['오답갈래'].items()) or '없음'} |")
    L += ["", "## 읽기 과제 — 종류별 정답률(엄격, 값 칸) · 빈 칸 값 채움", ""]
    kinds = list(dict.fromkeys(read_csv(EP09 / "sample_A.csv")["kind"]))
    for task in TASKS:
        ms = [m for m in MODELS if (task, m) in allc]
        if not ms or task == "H5":
            continue
        L += [f"### {TNAME[task]}", "", "| 종류 | " + " | ".join(f"{MNAME[m]} 정답 | {MNAME[m]} 값 채움" for m in ms) + " |", "|---|" + "---|---|" * len(ms)]
        for kd in kinds:
            cellsrow = []
            for m in ms:
                c = allc[(task, m)]
                c = c[(c["kind"] == kd) & (c["문서답있음"] == 1)]
                a = G.agg_a(c)
                cellsrow += [pct(a["정답_엄격"], a["칸_값"]), f"{a['빈칸_값채움']}/{a['칸_빈칸']}"]
            L.append(f"| {kd} | " + " | ".join(cellsrow) + " |")
        L.append("")
    # 문항(칸)별 — 오답이 몰린 문항
    L += ["## 읽기 과제 — 오답·값 채움이 3개 이상 몰린 문항(과제 × 종류 × 칸, 세 모델 합)", "", "| 과제 | 종류 | 칸 | 값 칸(모델 합) | 오답 | 답 없음 | 빈 칸 | 값 채움 |", "|---|---|---|---:|---:|---:|---:|---:|"]
    for task in TASKS:
        cs = [allc[(task, m)] for m in MODELS if (task, m) in allc]
        if not cs:
            continue
        c = pd.concat(cs)
        c = c[c["문서답있음"] == 1]
        for (kd, col), g in c.groupby(["kind", "칸"], sort=False):
            a = G.agg_a(g)
            if a["오답_엄격"] + a["빈칸_값채움"] >= 3:
                L.append(f"| {task} | {kd} | {col} | {a['칸_값']} | {a['오답_엄격']} | {a['답없음']} | {a['칸_빈칸']} | {a['빈칸_값채움']} |")
    L.append("")
    # 불일치 목록(원문 대조용)
    bad = []
    for (task, m), c in allc.items():
        b = c[(c["문서답있음"] == 1) & ((c["엄격"] == "오답") | (c["엄격"] == "답없음") | (c["빈칸결과"].isin(["값 채움", "0 채움"])))]
        bad.append(b)
    if bad:
        pd.concat(bad).to_csv(OUT3 / "불일치_전체.csv", index=False, encoding="utf-8-sig")
    return res


# ================================================================ B
def b_key(sub_only: bool) -> pd.DataFrame:
    k = read_csv(EP09 / "sample_B3.csv")
    return k[k["부분"] == "1"] if sub_only else k


def flat_b(task: str, model: str, run: int = 1, salvage: bool = False) -> dict[str, str]:
    """salvage=True 면 JSON 이 깨져 파싱에 실패한 묶음에서 '"번호": n, "답": "…"' 짝만 정규식으로 꺼낸다(보조 집계용, 등록 뒤 추가)."""
    import re as _re
    out = {}
    for u, r in R.latest(RUN3 / f"{task}_{model}_run{run}.jsonl", "unit").items():
        if r["status"] == "ok":
            for i, a in r["answers"].items():
                out[i] = a["answer"]
        elif salvage and r["status"] == "파싱실패":
            for m in _re.finditer(r'"번호"\s*:\s*"?(\d+)"?\s*,\s*"답"\s*:\s*"([^"]*)"', r.get("result") or ""):
                n = int(m.group(1))
                if 1 <= n <= len(r["ids"]):
                    out[r["ids"][n - 1]] = m.group(2)
    return out


def grade_b_all(L: list[str]) -> dict:
    sets = [("B-주 · Sonnet · 7,000건(모름 허용)", "B", "sonnet", False, "B주_sonnet"),
            ("B-세 급 · Sonnet · 부분 2,000건(모름 허용, B-주에서 그 건만)", "B", "sonnet", True, "B부분_sonnet"),
            ("B-세 급 · Haiku · 부분 2,000건(모름 허용)", "B", "haiku", True, "B부분_haiku"),
            ("B-세 급 · Opus · 부분 2,000건(모름 허용)", "B", "opus", True, "B부분_opus"),
            ("B-강제 · Sonnet · 부분 2,000건(모름 없이)", "BF", "sonnet", True, "B강제_sonnet"),
            ("(보조) B-세 급 · Haiku · 부분 2,000건 — JSON 이 깨진 묶음에서 번호·답 짝만 꺼내 넣었을 때", "B", "haiku", True, "B부분_haiku_깨진묶음포함")]
    out = {}
    L += ["## 뉴스 제목 방향(B) — 묶음별", "",
          "적중률 = 오름/내림으로 답했고 수익률이 0 이 아닌 건 가운데 방향이 맞은 비율. '0 을 오답으로' = 수익률 0 인 건도 분모에 넣고 못 맞힌 것으로 침. 대괄호 = 윌슨 95%.",
          "목록형 제목 = use==1 전체에서 글자가 같은 제목이 10줄 이상(2단계의 '틀 제목'과 같은 기준).", ""]
    for title, task, model, sub, name in sets:
        ans = flat_b(task, model, salvage=name.endswith("포함"))
        key = b_key(sub)
        ans = {i: a for i, a in ans.items() if i in set(key["id"])}
        if not ans:
            continue
        kp = T.T3 / ("sample_B3_부분.csv" if sub else "sample_B3_전체.csv")
        key.to_csv(kp, index=False, encoding="utf-8-sig")
        g = G.grade_b(ans, kp)
        g = g[g["답있음"] == 1]                                   # 답이 온 건만(한도로 멈춘 경우 남은 건은 뺌)
        res = G.report_b(g, name, OUT3)
        out[name] = (res, len(g), len(key))
        L += [f"### {title} — 답이 온 건 {len(g):,}/{len(key):,}", ""]
        for h, lab in (("post5", "5분"), ("post30", "30분")):
            L += [f"**기사 뒤 {lab}**", "", "| 묶음 | 표본 | 변화 없음 | 답한 것 중 적중률 | 0 을 오답으로 | 모름 비율 | 답 오름/내림/모름 | 전부 오름 | 전부 내림 | 무작위 범위 |", "|---|---:|---:|---|---|---|---|---|---|---|"]
            for (lab2, hh), s in res.items():
                if hh != h or lab2 == "앞-뒤":
                    continue
                L.append(f"| {lab2} | {s['n']} | {s['변화없음']} | {G.pct(s['적중'], s['답함'])} | {G.pct(s['적중_0포함'], s['답함_0포함'], False)} | {G.pct(s['모름'] + s['형식밖'] + s['답없음'], s['n'], False)} | "
                         f"{s['답_오름']}/{s['답_내림']}/{s['모름'] + s['형식밖']} | {G.pct(s['기준_전부오름'], s['방향있음'], False)} | {G.pct(s['기준_전부내림'], s['방향있음'], False)} | {100 * s['무작위_lo']:.1f}~{100 * s['무작위_hi']:.1f}% |")
            for tag, la, lb in (("", "일반 기사 · 앞", "일반 기사 · 뒤"), (" (목록형 제목 뺌)", "일반 기사 · 앞 (틀 제목 뺌)", "일반 기사 · 뒤 (틀 제목 뺌)")):
                a, b = res.get((la, h)), res.get((lb, h))
                if a and b and a["답함"] and b["답함"]:
                    for zero, ka, na in ((False, "적중", "답함"), (True, "적중_0포함", "답함_0포함")):
                        pa, pb = a[ka] / a[na], b[ka] / b[na]
                        se = math.sqrt(pa * (1 - pa) / a[na] + pb * (1 - pb) / b[na])
                        L.append(f"- 일반 기사 앞 − 뒤{tag}{' · 0 을 오답으로' if zero else ''} = {100 * (pa - pb):+.1f}%p (95% 구간 {100 * (pa - pb - 1.96 * se):+.1f} ~ {100 * (pa - pb + 1.96 * se):+.1f}%p · 앞 {a[ka]}/{a[na]} · 뒤 {b[ka]}/{b[na]})")
            L.append("")
    return out


# ================================================================ 재실행 일치
def rerun(L: list[str]):
    L += ["## 재실행 — 같은 설정으로 3회(Sonnet)", ""]
    L += ["| 과제 | 세 번 모두 답이 온 문서 | 칸 | 세 번 모두 같은 답(정규화 뒤) | 값 칸에서 | 빈 칸에서 | 문서 단위(전 칸 같음) | 실행별 정답(엄격) run1 / run2 / run3 | 실행별 빈 칸 값 채움 |", "|---|---:|---:|---|---|---|---|---|---|"]
    for task in ("H1", "H2", "H3", "H4"):
        runs = {r: load_ans(task, "sonnet", r) for r in (1, 2, 3)}
        both = sorted(set(runs[2]) & set(runs[3]) & set(runs[1]))
        if not both:
            continue
        key = load_key(task)
        key = key[key["rcept_no"].isin(both) & key["상태"].isin(["값", "빈칸"])]
        tot, same, docsame = Counter(), Counter(), defaultdict(lambda: True)
        for k in key.itertuples(index=False):
            vals = [R.norm_cell(k.형, runs[r][k.rcept_no].get(k.칸)) for r in (1, 2, 3)]
            s = len(set(vals)) == 1
            for grp in ("전체", k.상태):
                tot[grp] += 1
                same[grp] += s
            docsame[k.rcept_no] = docsame[k.rcept_no] and s
        acc, fill = [], []
        for r in (1, 2, 3):
            c = grade_doc(task, {d: runs[r][d] for d in both}, key)
            a = G.agg_a(c)
            acc.append(f"{a['정답_엄격']}/{a['칸_값']}")
            fill.append(f"{a['빈칸_값채움']}/{a['칸_빈칸']}")
        L.append(f"| {TNAME[task]} | {len(both)} | {tot['전체']} | {G.pct(same['전체'], tot['전체'])} | {G.pct(same['값'], tot['값'], False)} | {G.pct(same['빈칸'], tot['빈칸'], False)} | "
                 f"{G.pct(sum(docsame[d] for d in both), len(both), False)} | {' / '.join(acc)} | {' / '.join(fill)} |")
    L.append("")
    runs = {r: flat_b("B", "sonnet", r) for r in (1, 2, 3)}
    ids = sorted(set(runs[2]) & set(runs[3]) & set(runs[1]))
    if ids:
        sb = read_csv(EP09 / "sample_B3.csv").set_index("id")
        tot, same, pat = Counter(), Counter(), Counter()
        for i in ids:
            vals = [G.norm_b(runs[r][i]) for r in (1, 2, 3)]
            s = len(set(vals)) == 1
            for grp in ("전체", f"{sb.loc[i, '갈래']} · {sb.loc[i, '구간']}"):
                tot[grp] += 1
                same[grp] += s
            pat["세 번 같음: " + vals[0] if s else "갈림: " + "/".join(sorted(set(vals)))] += 1
        L += [f"### B-주 재실행 — 세 번 모두 답이 온 건 {len(ids)}", "", "| 묶음 | 건 | 세 번 모두 같은 답 |", "|---|---:|---|"]
        for grp in tot:
            L.append(f"| {grp} | {tot[grp]} | {G.pct(same[grp], tot[grp])} |")
        L += ["", "답 무늬: " + ", ".join(f"{k} {n}" for k, n in pat.most_common()), "", "| 실행 | 5분 적중률(답한 것 중) | 30분 | 모름 |", "|---|---|---|---:|"]
        for r in (1, 2, 3):
            cell = []
            for h in ("post5", "post30"):
                hit = said = 0
                for i in ids:
                    v, x = G.norm_b(runs[r][i]), float(sb.loc[i, h])
                    if v in ("오름", "내림") and x != 0:
                        said += 1
                        hit += (v == "오름") == (x > 0)
                cell.append(G.pct(hit, said, False))
            L.append(f"| run{r} | {cell[0]} | {cell[1]} | {sum(G.norm_b(runs[r][i]) == '모름' for i in ids)} |")
        L.append("")


# ================================================================ 호출 통계
def call_stats(L: list[str]):
    L += ["## 호출 통계(run3/ 기록의 모든 줄)", "",
          "| 파일 | 줄 | ok | 파싱실패 | 호출실패 | 재시도(tries=2) | 입력 토큰 평균 | 출력 토큰 평균 | 걸린 시간 평균(초) | 최대(초) | 시간 합(분) | 입력 합 | 출력 합 | 표시 비용 합($, 청구 아님) | 처음 ~ 끝 | 실제 모델 ID | stop |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|"]
    tot = Counter()
    for p in sorted(RUN3.glob("*_run*.jsonl")):
        rs = R.read_jsonl(p)
        if not rs:
            continue
        got = [r for r in rs if r.get("sec") is not None]
        st = Counter(r["status"] for r in rs)
        mean = lambda k: (sum(r.get(k) or 0 for r in got) / len(got)) if got else 0
        models = sorted({m for r in got for m in r.get("model_실제", [])})
        stops = dict(Counter(r.get("stop") for r in got))
        sin, sout, cost = sum(r.get("in_tok") or 0 for r in got), sum(r.get("out_tok") or 0 for r in got), sum(r.get("cost_표시") or 0 for r in got)
        tot.update({"줄": len(rs), "in": sin, "out": sout, "sec": sum(r.get("sec") or 0 for r in got), "실패": st["호출실패"], "파싱": st["파싱실패"], "재시도": sum(1 for r in rs if r.get("tries") == 2)})
        tot["cost"] += cost
        L.append(f"| {p.name} | {len(rs)} | {st['ok']} | {st['파싱실패']} | {st['호출실패']} | {sum(1 for r in rs if r.get('tries') == 2)} | {mean('in_tok'):,.0f} | {mean('out_tok'):,.0f} | {mean('sec'):.1f} | "
                 f"{max((r.get('sec') or 0) for r in got) if got else 0:.1f} | {sum(r.get('sec') or 0 for r in got) / 60:.1f} | {sin:,} | {sout:,} | {cost:.2f} | {rs[0]['ts'][5:]} ~ {rs[-1]['ts'][5:]} | {', '.join(models)} | {stops} |")
    L += [f"| **합** | {tot['줄']} | | {tot['파싱']} | {tot['실패']} | {tot['재시도']} | | | | | {tot['sec'] / 60:.1f} | {tot['in']:,} | {tot['out']:,} | {tot['cost']:.2f} | | | |", ""]


def selftest():
    for task in TASKS:
        key = load_key(task)
        ans = defaultdict(dict)
        for k in key.itertuples(index=False):
            ans[k.rcept_no][k.칸] = (k.정답 if k.상태 == "값" else None)
            if k.상태 == "값" and k.형 == "date":
                ans[k.rcept_no][k.칸] = f"{k.정답[:4]}-{k.정답[4:6]}-{k.정답[6:]}"
        a = summarize(grade_doc(task, dict(ans), key))
        assert a["정답_엄격"] == a["칸_값"] and a["빈칸_값채움"] == 0 and a["다른문서값"] == 0, (task, a)
        print(task, "정답지 그대로 → 만점", a["칸_값"], "칸 · 빈 칸", a["칸_빈칸"])
    # 반올림 과제의 엄격·관용·갈래
    k = load_key("H2")
    r = k[(k["상태"] == "값") & (k["정답"] != k["정답_반올림전"]) & (k["정답"] != "0")].iloc[0]
    one = k[(k["rcept_no"] == r.rcept_no) & (k["칸"] == r.칸)]
    lo = Decimal(r.정답) - Decimal("0.01")
    for val, want in ((r.정답, ("정답", "정답", "")), (str(lo), None), (r.원단위_정답, ("오답", "오답", "원문 단위 그대로")), (str(Decimal(r.정답) * 10), ("오답", "오답", "자릿수만 틀림"))):
        c = grade_doc("H2", {r.rcept_no: {r.칸: val}}, one).iloc[0]
        got = (c["엄격"], c["관용"], c["오답갈래"])
        if want:
            assert got == want, (val, got, want)
        print("H2", r.정답, "답", val, "→", got)
    print("자체 시험 통과")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "selftest":
        return selftest()
    OUT3.mkdir(parents=True, exist_ok=True)
    L = ["# 9편 3단계 채점 집계 (ep09_grade3.py all)", ""]
    grade_reading(L)
    grade_b_all(L)
    rerun(L)
    call_stats(L)
    (OUT3 / "집계_3단계.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
