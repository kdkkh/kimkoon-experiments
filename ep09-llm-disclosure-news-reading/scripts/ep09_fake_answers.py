# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 공개판에서 새로 쓴 파일(원본 없음).
"""가짜 답으로 실행기(ep09_run · run3 · run4 · run5)를 끝까지 돌린다 — 모델·네트워크·`claude` 명령을 부르지 않는다.

하는 일: 각 실행기 모듈의 call_claude(= `claude -p` 를 부르는 함수 하나)만 이 파일의 가짜 함수로 바꿔 끼운다.
  나머지(프롬프트 만들기 · 프롬프트 해시 · 묶음 · 재시도 · 멈춤 규칙 · 기록 줄 · 답 파싱 · 이어 받기)는 실행기 코드 그대로 돈다.
가짜 답은 정답표에서 만든다 — 대부분 맞고, 일부러 틀린 값 · 단위 틀림 · 빈 칸 채움 · 형식 위반(파싱 실패) · 빠진 번호 ·
  다른 문서 값(H4) · 한 번 실패 뒤 재시도를 섞는다. 그래서 채점기의 갈래가 모두 한 번씩은 지나간다. 수치에는 아무 뜻이 없다.
가짜 견본 작업 공간(ep09_fake_data.py 가 만든 폴더, 표시 파일 있음)에서만 돈다 — 실제 실행 기록을 덮어쓰지 않게.

쓰기(이 폴더에서):  python -X utf8 scripts/ep09_fake_answers.py 2|3|4|5     (단계마다 그 단계 실행기의 `prompts` 를 먼저)
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import defaultdict
from decimal import Decimal

import pandas as pd

from ep09_paths import DATA

MARK = "_가짜_견본_작업공간.txt"
ACC = {"haiku": 0.93, "sonnet": 0.96, "opus": 0.985}


def rng_of(*parts) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:12], 16))


def cli(model_id: str, prompt: str, result: str) -> dict:
    """`claude -p --output-format json` 의 결과와 같은 꼴(실행기가 읽는 칸만)."""
    n_in, n_out = 1300 + len(prompt) // 2, 20 + len(result) // 2
    return {"type": "result", "subtype": "success", "is_error": False, "result": result, "_sec": 0.0, "duration_api_ms": 0,
            "num_turns": 1, "stop_reason": "end_turn", "total_cost_usd": 0.0,
            "usage": {"input_tokens": n_in, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": n_out},
            "modelUsage": {model_id: {"inputTokens": n_in, "outputTokens": n_out}}}


FAILED_ONCE = set()


def maybe_fail(tag: str):
    """단계마다 한 건은 첫 시도에서 실패시켜 재시도(tries = 2) 길을 지나게 한다. 한도 문구가 아니어서 멈추지 않는다."""
    if tag not in FAILED_ONCE:
        FAILED_ONCE.add(tag)
        raise RuntimeError("가짜 오류(시간 초과 흉내)")


def log(msg):
    print(msg, flush=True)


def read_csv(p) -> pd.DataFrame:
    return pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")


# ================================================================ 값 하나를 모델 답처럼
def num_text(v: str) -> str:
    d = Decimal(v)
    s = format(d, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def answer_cell(r: random.Random, truth: str, state: str, tp: str, acc: float, raw_unit: str = ""):
    """정답 칸 하나 → 모델 답 하나(대개 정답, 가끔 틀림)."""
    if state != "값":
        u = r.random()
        if u < 0.90:
            return None
        return 0 if (tp == "num" and u < 0.95) else ("1,000" if tp == "num" else "2026-01-02" if tp == "date" else "일반")
    if tp == "date":
        v = f"{truth[:4]}-{truth[4:6]}-{truth[6:]}"
        if r.random() > acc:
            return f"{truth[:4]}-{truth[4:6]}-{'28' if truth[6:] != '28' else '27'}"
        return v
    if tp == "enum":
        return truth if r.random() <= acc else "전혀다른분류"
    v = num_text(truth)
    u = r.random()
    if u <= acc:
        return v if r.random() < 0.7 else (int(Decimal(v)) if Decimal(v) == Decimal(v).to_integral_value() and abs(Decimal(v)) < 10 ** 15 else float(v))
    if u <= acc + (1 - acc) / 3:
        return num_text(str(Decimal(truth) * 1000))                  # 자릿수
    if u <= acc + 2 * (1 - acc) / 3:
        return raw_unit or num_text(str(-Decimal(truth)))            # 원문 단위 그대로(H2·H5) 또는 부호
    return None


def obj_result(r: random.Random, o: dict) -> str:
    """JSON 객체 답. 가끔 코드블록 표시를 붙이고, 아주 가끔 객체를 둘 내서 형식 위반(파싱 실패)을 만든다."""
    s = json.dumps(o, ensure_ascii=False)
    u = r.random()
    if u < 0.03:
        return '먼저 찾은 값: {"q01": null}\n고친 답: ' + s           # 객체 둘 → 파싱 실패(보조 집계의 '마지막 객체 채택'이 살린다)
    if u < 0.12:
        return "```json\n" + s + "\n```"
    return s


def arr_result(r: random.Random, arr: list, broken_ok: bool = True) -> str:
    s = json.dumps(arr, ensure_ascii=False)
    if broken_ok and r.random() < 0.03:
        return s[: len(s) * 2 // 3]                                   # 잘린 배열 → 파싱 실패(보조 집계가 번호·답 짝만 꺼낸다)
    return s


# ================================================================ 2단계
def stage2():
    import ep09_run as R
    key = read_csv(R.EP09 / "sample_A_정답.csv")
    kv = {(k.rcept_no, k.칸): (k.정답, k.상태, k.형) for k in key.itertuples(index=False)}
    fields = R.load_fields()
    look = {}
    for row in R.load_a().itertuples(index=False):
        look[(R.SYSTEM_A, R.prompt_a(row.종류, fields[row.kind], R.doc_text(row.rcept_no)[0]))] = ("A", row.rcept_no, row.kind)
    for i, items in enumerate(R.b_batches(), 1):
        look[(R.SYSTEM_B, R.prompt_b(items))] = ("B", i, items)
    st = {"run": 1}
    first = {"A": sorted(R.c_sample()["A"])[0], "B": sorted(R.c_sample()["B_묶음"])[0]}

    def fake(system, prompt, timeout):
        task, unit, extra = look[(system, prompt)]
        r = rng_of(2, task, unit, st["run"])
        if unit == first[task]:
            maybe_fail(f"2{task}{st['run']}")
        if task == "A":
            o = {f"q{i:02d}": answer_cell(r, *kv[(unit, f["칸"])], ACC["sonnet"]) for i, f in enumerate(fields[extra], 1)}
            return cli(R.MODEL, prompt, obj_result(r, o))
        arr = []
        for i, it in enumerate(extra, 1):
            if r.random() < 0.01:
                continue                                              # 빠진 번호
            a = r.choices(["오름", "내림", "모름"], [0.42, 0.08, 0.50])[0]
            arr.append({"번호": i, "답": a, "근거": "가짜 근거"})
        return cli(R.MODEL, prompt, arr_result(r, arr))

    R.call_claude = fake
    R.save_prompts()
    R.c_sample()
    for run in (1, 2, 3):
        st["run"] = run
        R.run_a(run, 0, log)
        R.run_b(run, 0, log)


# ================================================================ 3단계
def stage3():
    import ep09_run3 as S
    import ep09_tasks3 as T
    ctx = S.Ctx()
    T3 = T.T3
    keys = {"A3": read_csv(T3 / "정답_A3.csv"), "H2": read_csv(T3 / "정답_H2.csv"), "H3": read_csv(T3 / "정답_H3.csv"), "H5": read_csv(T3 / "정답_H5.csv")}
    kv = {t: {(k.rcept_no, k.칸): k._asdict() for k in d.itertuples(index=False)} for t, d in keys.items()}
    look = {}
    for task in S.DOC_TASKS + ("B", "BF"):
        units = set()
        for m in S.MODELS:
            for run in (1, 2):
                units |= set(ctx.units(task, m, run))
        for u in sorted(units):
            b = ctx.build(task, u)
            look[(b["system"], b["prompt"])] = (task, u, b)
    st = {"run": 1}

    def fake(model_id, system, prompt, timeout):
        task, unit, b = look[(system, prompt)]
        model = model_id.split("-")[1]
        r = rng_of(3, task, unit, model, st["run"])
        if unit == sorted(ctx.batches)[0] and task == "B":
            maybe_fail(f"3B{model}{st['run']}")
        if task in ("B", "BF"):
            dk = {"haiku": 0.91, "sonnet": 0.55, "opus": 0.92}[model] if task == "B" else 0.0
            arr = []
            for i, uid in enumerate(b["ids"], 1):
                if r.random() < 0.01:
                    continue
                a = "모름" if r.random() < dk else ("오름" if r.random() < 0.84 else "내림")
                arr.append({"번호": i, "답": a, "근거": "가짜 근거"})
            return cli(model_id, prompt, arr_result(r, arr, broken_ok=(model == "haiku")))
        src = {"A3": "A3", "H1": "A3", "H4": "A3", "H2": "H2", "H3": "H3", "H5": "H5"}[task]
        o = {}
        for i, col in enumerate(b["keys"], 1):
            k = kv[src][(unit, col)]
            tp = k.get("형") or "num"
            raw = num_text(k["원단위_정답"]) if k.get("원단위_정답") else ""
            v = answer_cell(r, k["정답"], k["상태"], tp, ACC[model], raw)
            if task == "H4" and r.random() < 0.02:                        # 같이 넣은 다른 회사 공시의 같은 칸 값
                g = ctx.h4[unit]
                other = [g[f"문서{j}"] for j in (1, 2, 3) if g[f"문서{j}"] != unit][0]
                ok = kv["A3"].get((other, col))
                if ok and ok["상태"] == "값":
                    v = num_text(ok["정답"]) if ok["형"] == "num" else ok["정답"]
            o[f"q{i:02d}"] = v
        return cli(model_id, prompt, obj_result(r, o))

    S.call_claude = fake
    for task, model, run in S.PLAN:
        st["run"] = run
        if not S.run_one(ctx, task, model, run, 0, log):
            sys.exit(f"멈춤: {S.STOP_WHY[0]}")


# ================================================================ 4단계
def stage4():
    import ep09_run4 as S
    ctx = S.Ctx()
    look = {}
    for pan in S.PANS:
        for run in (1, 2):
            for u in ctx.units(pan, "sonnet", run):
                b = ctx.build(pan, u)
                look[(b["system"], b["prompt"])] = (pan, u, b)
    st = {"run": 1}
    dk = {"N": {"haiku": 0.95, "sonnet": 0.92, "opus": 0.87}, "E": {"haiku": 0.65, "sonnet": 0.07, "opus": 0.63}, "F": {"haiku": 0, "sonnet": 0, "opus": 0}}

    def fake(model_id, system, prompt, timeout):
        pan, unit, b = look[(system, prompt)]
        model = model_id.split("-")[1]
        r = rng_of(4, pan, unit, model, st["run"])
        arr = []
        for i, uid in enumerate(b["ids"], 1):
            it = ctx.items[uid]
            o = {"번호": i}
            for q, nm in (("Q1", "앞"), ("Q2", "뒤")):
                if r.random() < dk[pan][model]:
                    o[nm] = "모름"
                else:
                    right = r.random() < 0.62
                    y = it[q] == "1"
                    o[nm] = "예" if (y == right) else "아니오"
            o["근거"] = "가짜 근거"
            arr.append(o)
        return cli(model_id, prompt, arr_result(r, arr, broken_ok=(model != "sonnet")))

    S.call_claude = fake
    for pan, model, run in S.PLAN:
        st["run"] = run
        if not S.run_one(ctx, pan, model, run, 0, log):
            sys.exit(f"멈춤: {S.STOP_WHY[0]}")


# ================================================================ 5단계
def stage5():
    import ep09_run as R
    import ep09_run5 as S
    ctx = S.Ctx()
    T5 = S.T5
    kc = read_csv(T5 / "정답_C5.csv")
    ks = read_csv(T5 / "정답_S5_칸.csv")
    kj = read_csv(T5 / "정답_J5.csv")
    kj = kj[kj["뺀_이유"] == ""]
    c5 = {r: g for r, g in kc.groupby("rcept_no")}
    s5 = {r: g for r, g in ks.groupby("rcept_no")}
    j5 = {r: g for r, g in kj.groupby("rcept_no")}
    look = {}
    for task in S.TASKS:
        for run in (1, 2):
            for u in ctx.units(task, "sonnet", run):
                b = ctx.build(task, u)
                look[(b["system"], b["prompt"])] = (task, u)
    st = {"run": 1}

    def fake(model_id, system, prompt, timeout):
        task, unit = look[(system, prompt)]
        model = model_id.split("-")[1]
        r = rng_of(5, task, unit, model, st["run"])
        acc = ACC[model]
        if task == "C5":
            ents = []
            for x in c5.get(unit, kc.iloc[0:0]).itertuples(index=False):
                u = r.random()
                if u > acc + (1 - acc) / 2:
                    continue                                          # 빠뜨림
                b_, a_ = (x.전_원문, x.후_원문) if u <= acc else (x.후_원문, x.전_원문)   # 가끔 뒤바꿈
                ents.append({"항목": x.항목, "정정전": b_, "정정후": a_})
            if r.random() < 0.1:
                ents.append({"항목": "가짜 항목", "정정전": "1", "정정후": "2099년 1월 1일"})    # 원문에 없는 값
            return cli(model_id, prompt, obj_result(r, {"바뀐것": ents}))
        if task == "S5":
            parts = []
            for x in list(s5.get(unit, ks.iloc[0:0]).itertuples(index=False))[:4]:
                if r.random() > acc:
                    continue
                if x.형 == "num":
                    v = Decimal(x.정답)
                    if r.random() < 0.05:
                        v = v * 10                                    # 열 배 어긋난 수
                    parts.append(f"{x.질문이름}은 {v:,}")
                else:
                    parts.append(f"{x.질문이름}은 {x.정답[:4]}년 {int(x.정답[4:6])}월 {int(x.정답[6:])}일")
            text = ("가짜 견본 회사가 공시를 냈다. " + ", ".join(parts) + "이다.") if parts else "가짜 견본 회사가 공시를 냈다."
            return cli(model_id, prompt, obj_result(r, {"요약": text}))
        doc = R.doc_text(unit)[0]
        quotes = [ln for ln in doc.splitlines() if len(ln) > 8]
        o = {}
        for x in j5.get(unit, kj.iloc[0:0]).itertuples(index=False):
            a = x.정답 if r.random() <= acc else r.choice([v for v in ("예", "아니오", "판단 불가") if v != x.정답])
            q = r.choice(quotes)[:80]
            if r.random() < 0.01:
                q = q + " 등"                                           # 원문과 다른 인용
            o[x.문항] = {"답": a, "근거": q}
        return cli(model_id, prompt, obj_result(r, o))

    S.call_claude = fake
    for task, model, run in S.PLAN:
        st["run"] = run
        if not S.run_one(ctx, task, model, run, 0, log):
            sys.exit(f"멈춤: {S.STOP_WHY[0]}")


def _no_process(*a, **k):
    raise RuntimeError("가짜 답 실행 중에 외부 명령(claude 등)을 부르려 함 — 막음")


def main():
    import subprocess
    subprocess.run = _no_process                       # 바꿔 끼우기가 빠져도 `claude -p` 가 절대 실행되지 않게
    subprocess.Popen = _no_process
    if not (DATA / MARK).exists():
        sys.exit(f"{DATA} 에 가짜 견본 표시 파일({MARK})이 없다 — 실제 실행 기록을 덮어쓰지 않게 멈춤")
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    {"2": stage2, "3": stage3, "4": stage4, "5": stage5}.get(stage, lambda: sys.exit("쓰기: ep09_fake_answers.py 2|3|4|5"))()
    print(f"가짜 답 {stage}단계 끝 — 모델 호출 0")


if __name__ == "__main__":
    main()
