# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 4단계 — 실행기 (2026-11-17). Claude Code 헤드리스(`claude -p`, 구독)만 쓴다. API 결제 없음.

3단계 실행기(ep09_run3.py)를 복사해 과제만 바꿨다. 호출 방식 그대로:
  claude -p --model <모델> --output-format json --tools "" --strict-mcp-config --no-session-persistence
  --system-prompt <고정> --effort low · 프롬프트는 표준 입력 · 빈 폴더에서 실행 · 동시 2개 · 한 건 최대 2번 시도.
환경 변수 ANTHROPIC_API_KEY 가 있으면 시작하지 않는다. 연속 3번 실패·한도 문구·요청한 모델이 답에 없으면 멈춘다. 다시 돌리면 끝난 건은 건너뛴다.

판(과제 정의는 ep09_tasks4.py → data/ep09/과제4/):
  N = 맨손(설명만) · E = 예시 판(앞 절반 정답 달린 예시 40건) · F = 강제 판(모름 없음, Sonnet · 50묶음)
  묶음 하나 = 20건 = 호출 하나. 재실행 = N Sonnet 20묶음 run2·run3.
기록: data/ep09/run4/<판>_<모델>_run<N>.jsonl  (3단계 기록과 같은 항목)

쓰기(이 폴더에서):
  python -X utf8 scripts/ep09_run4.py prompts                 # 프롬프트 전문 + 건별 프롬프트 해시 목록(호출 없음)
  python -X utf8 scripts/ep09_run4.py show N N001
  python -X utf8 scripts/ep09_run4.py one N sonnet --run 1 [--limit 2]
  python -X utf8 scripts/ep09_run4.py all                     # 사전 등록한 순서대로 전부(멈추면 exit 2, 다시 돌리면 이어서)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
import ep09_run as R  # noqa: E402  (호출 도구·파서만 씀 — 고치지 않음)

EP09 = DATA / "ep09"
T4 = EP09 / "과제4"
RUN4 = EP09 / "run4"
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
EFFORT = "low"
WORKERS = 2
MAX_FAIL = 3
TIMEOUT = 300
PANS = ("N", "E", "F")
PAN_NAME = {"N": "맨손", "E": "예시", "F": "강제(모름 없음)"}

# ================================================================ 프롬프트
SYSTEM = R.SYSTEM_B          # 3단계 B 와 같은 시스템 프롬프트
HEAD = R.HEAD_B              # 3단계 B 와 같은 머리

DEF_LINE = ("'평소보다 크게' = 오른 쪽이든 내린 쪽이든, 그 종목의 평소 30분 움직임 크기 가운데 큰 쪽 10% 에 드는 움직임이다. "
            "방향(오름·내림)은 묻지 않는다.")
Q_LINES = ("[질문]\n기사마다 두 가지를 답한다.\n"
           "- 앞: 이 기사가 나오기 전 30분에 이 종목 가격이 평소보다 크게 움직였는가\n"
           "- 뒤: 이 기사가 나온 뒤 30분에 이 종목 가격이 평소보다 크게 움직였는가\n" + DEF_LINE)
TAIL_N = Q_LINES + """

[답 형식]
- JSON 배열 하나, 객체 {n}개, 입력 순서대로. 각 객체: {{"번호": <기사 번호>, "앞": "예" | "아니오" | "모름", "뒤": "예" | "아니오" | "모름", "근거": "<한 줄, 30자 이내>"}}
- "앞"·"뒤"는 각각 예·아니오·모름 셋 중 하나만. 제목만으로 판단할 수 없으면 "모름"."""
TAIL_F = Q_LINES + """

[답 형식]
- JSON 배열 하나, 객체 {n}개, 입력 순서대로. 각 객체: {{"번호": <기사 번호>, "앞": "예" | "아니오", "뒤": "예" | "아니오", "근거": "<한 줄, 30자 이내>"}}
- "앞"·"뒤"는 각각 예·아니오 둘 중 하나만. "모름"은 쓸 수 없다. 제목만으로 판단하기 어려워도 더 가능성이 높다고 보는 쪽을 고른다."""
EX_HEAD = ("[보기] 아래 <보기> {k}건은 다른 기간의 기사와, 그 기사 앞뒤 30분 가격으로 실제로 잰 답이다(아래 질문 기사와 겹치지 않는다). "
           "'예' = 평소보다 크게 움직였음, '아니오' = 그렇지 않았음.")


def yn(v) -> str:
    return "예" if int(v) == 1 else "아니오"


def examples_block(ex: list[dict]) -> str:
    body = "\n".join(f'<보기 번호="{i}">{e["종목명"]} | {e["title"]} → 앞: {yn(e["Q1"])} · 뒤: {yn(e["Q2"])}</보기>' for i, e in enumerate(ex, 1))
    return EX_HEAD.format(k=len(ex)) + "\n" + body


def prompt_of(pan: str, items: list[dict], ex: list[dict]) -> str:
    body = "\n".join(f'<기사 번호="{i}">{it["종목명"]} | {it["title"]}</기사>' for i, it in enumerate(items, 1))
    n = len(items)
    if pan == "E":
        return HEAD.format(n=n) + "\n" + examples_block(ex) + "\n\n[질문 기사]\n" + body + "\n\n" + TAIL_N.format(n=n)
    tail = TAIL_F if pan == "F" else TAIL_N
    return HEAD.format(n=n) + "\n" + body + "\n\n" + tail.format(n=n)


class Ctx:
    def __init__(self):
        s = pd.read_csv(T4 / "표본4.csv", dtype=str, encoding="utf-8-sig").fillna("")
        self.items = s.set_index("id").to_dict("index")
        ex = pd.read_csv(T4 / "예시4.csv", dtype=str, encoding="utf-8-sig").fillna("")
        self.ex = ex.sort_values("예시번호", key=lambda c: c.astype(int)).to_dict("records")
        b = json.loads((T4 / "묶음4.json").read_text(encoding="utf-8"))
        self.batches, self.forced, self.rerun = b["묶음"], b["강제"], b["재실행"]

    def units(self, pan: str, model: str, run: int) -> list[str]:
        keys = sorted(self.batches)
        if run > 1:
            return [k for k in keys if k in self.rerun]
        if pan == "F":
            return [k for k in keys if k in self.forced]
        return keys

    def build(self, pan: str, unit: str) -> dict:
        items = [{"id": i, **self.items[i]} for i in self.batches[unit]]
        return {"system": SYSTEM, "prompt": prompt_of(pan, items, self.ex), "timeout": TIMEOUT, "ids": [it["id"] for it in items]}


# ================================================================ 호출(3단계와 같음)
LOCK = threading.Lock()
STOP = threading.Event()
FAILS = [0]
STOP_WHY = [""]
TALLY = Counter()


def call_claude(model_id: str, system: str, prompt: str, timeout: int) -> dict:
    R.WORK_CWD.mkdir(parents=True, exist_ok=True)
    cmd = [R.claude_exe(), "-p", "--model", model_id, "--output-format", "json", "--tools", "", "--strict-mcp-config",
           "--no-session-persistence", "--system-prompt", system, "--effort", EFFORT]
    t0 = time.time()
    p = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, timeout=timeout, cwd=str(R.WORK_CWD))
    dt = time.time() - t0
    out = p.stdout.decode("utf-8", "replace")
    try:
        j = json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError(f"출력이 JSON 아님(rc {p.returncode}): {out[:300]} {p.stderr.decode('utf-8', 'replace')[:300]}")
    j["_sec"] = round(dt, 1)
    if j.get("is_error") or j.get("subtype") != "success":
        raise RuntimeError(f"오류 답: {str(j.get('result'))[:300]} api_error={j.get('api_error_status')}")
    used = sorted((j.get("modelUsage") or {}).keys())
    if not any(u.startswith(model_id) for u in used):
        raise RuntimeError(f"모델 대체: 요청 {model_id} 인데 답의 모델은 {used}")
    return j


def one_call(model_id: str, system: str, prompt: str, timeout: int, log, label: str):
    err = ""
    for attempt in (1, 2):
        if STOP.is_set():
            return None, err or "멈춤", attempt - 1
        try:
            j = call_claude(model_id, system, prompt, timeout)
            with LOCK:
                FAILS[0] = 0
                TALLY["시도"] += 1
            return j, "", attempt
        except Exception as ex:
            err = f"{type(ex).__name__}: {str(ex)[:400]}"
            log(f"  {label} 시도 {attempt} 실패: {err}")
            with LOCK:
                TALLY["시도"] += 1
                TALLY["실패 시도"] += 1
                FAILS[0] += 1
                if R.LIMIT_PAT.search(err) or "모델 대체" in err:
                    STOP.set()
                    STOP_WHY[0] = "구독 한도 또는 모델 대체로 보이는 오류: " + err[:200]
                elif FAILS[0] >= MAX_FAIL:
                    STOP.set()
                    STOP_WHY[0] = f"연속 {MAX_FAIL}번 실패: " + err[:200]
    return None, err, 2


def path_of(pan: str, model: str, run: int) -> Path:
    return RUN4 / f"{pan}_{model}_run{run}.jsonl"


def append(path: Path, rec: dict):
    with LOCK:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def parse_answers(result: str, ids: list[str]) -> dict:
    arr = R.parse_arr(result)
    byno = {}
    for o in arr:
        if isinstance(o, dict):
            try:
                byno[int(str(o.get("번호")).strip())] = o
            except (TypeError, ValueError):
                pass
    ans, miss = {}, []
    for i, uid in enumerate(ids, 1):
        o = byno.get(i)
        if o is None:
            miss.append(i)
        else:
            ans[uid] = {"앞": o.get("앞"), "뒤": o.get("뒤"), "근거": o.get("근거")}
    return {"answers": ans, "번호_빠짐": miss, "객체수": len(arr)}


def job(ctx: Ctx, pan: str, model: str, run: int, unit: str, path: Path, log) -> dict:
    if STOP.is_set():
        return {"skip": True}
    b = ctx.build(pan, unit)
    rec = {"task": pan, "unit": unit, "run": run, "model_요청": MODELS[model], "effort": EFFORT, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "prompt_hash": R.phash(b["system"], b["prompt"]), "prompt_chars": len(b["prompt"]), "timeout": b["timeout"], "ids": b["ids"]}
    j, err, tries = one_call(MODELS[model], b["system"], b["prompt"], b["timeout"], log, f"{pan} {model} {unit}")
    rec["tries"] = tries
    if j is None:
        if tries == 0:
            return {"skip": True}
        append(path, {**rec, "status": "호출실패", "err": err})
        return {"ok": False}
    rec.update(R.meta_of(j))
    try:
        rec.update(status="ok", **parse_answers(rec["result"], b["ids"]))
    except Exception as ex:
        rec.update(status="파싱실패", err=f"{type(ex).__name__}: {str(ex)[:200]}")
    append(path, rec)
    return {"ok": True, "status": rec["status"], "sec": rec["sec"], "in": rec["in_tok"], "out": rec["out_tok"]}


def run_one(ctx: Ctx, pan: str, model: str, run: int, limit: int, log) -> bool:
    path = path_of(pan, model, run)
    units = ctx.units(pan, model, run)
    done = {k for k, r in R.latest(path, "unit").items() if r["status"] in ("ok", "파싱실패")}
    todo = [u for u in units if u not in done]
    if limit:
        todo = todo[:limit]
    log(f"== {pan} {model} run{run}: 대상 {len(units)} · 끝난 건 {len(done & set(units))} · 이번에 {len(todo)}")
    if not todo:
        return True
    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(job, ctx, pan, model, run, u, path, log): u for u in todo}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
            except Exception as e_:
                log(f"  [{i}/{len(todo)}] {futs[f]} 예외 {type(e_).__name__}: {e_}")
                continue
            if r.get("skip"):
                continue
            if r["ok"]:
                if i % 10 == 0 or i == len(todo) or r["status"] != "ok":
                    log(f"  [{i}/{len(todo)}] {futs[f]} {r['status']} · {r['sec']}초 · 입력 {r['in']} · 출력 {r['out']} · {(time.time() - t0) / 60:.1f}분")
            else:
                log(f"  [{i}/{len(todo)}] {futs[f]} 호출 실패 — 연속 실패 시도 {FAILS[0]}")
            if STOP.is_set():
                for ff in futs:
                    ff.cancel()
                break
    log(f"   끝 {pan} {model} run{run}: {(time.time() - t0) / 60:.1f}분 · 누적 시도 {TALLY['시도']} · 실패 시도 {TALLY['실패 시도']}" + (f" · 멈춤({STOP_WHY[0]})" if STOP.is_set() else ""))
    return not STOP.is_set()


# 사전 등록한 실행 순서(위가 먼저)
PLAN = ([("N", m, 1) for m in ("sonnet", "haiku", "opus")]
        + [("E", m, 1) for m in ("sonnet", "haiku", "opus")]
        + [("F", "sonnet", 1)]
        + [("N", "sonnet", 2), ("N", "sonnet", 3)])


def save_prompts(ctx: Ctx):
    ex_b = [{"종목명": "<종목명 1>", "title": "<제목 1>"}, {"종목명": "<종목명 2>", "title": "<제목 2>"}]
    for pan in PANS:
        L = [f"# 4단계 {PAN_NAME[pan]} 판 프롬프트 전문 (scripts/ep09_run4.py 가 만든 것)", "",
             f"effort {EFFORT} · 도구 없음 · 한 호출에 20건(묶음 구성은 과제4/묶음4.json) · 입력은 종목명 + 제목만(날짜·시각·가격 없음)", "",
             "## 시스템 프롬프트(--system-prompt)", "", SYSTEM, "", "## 사용자 메시지 틀(아래는 질문 기사 2건짜리 보기 — 실제는 20건)", ""]
        if pan == "E":
            L += ["보기 40건은 모든 호출에 같은 것(과제4/예시4.csv, 순서 고정)이 그대로 들어간다. 아래 틀에는 실제 보기 40건을 그대로 넣었다.", ""]
        L += [prompt_of(pan, ex_b, ctx.ex), ""]
        (T4 / f"prompt_4_{PAN_NAME[pan].split('(')[0]}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    rows = []
    for pan in PANS:
        for u in ctx.units(pan, "sonnet", 1):
            b = ctx.build(pan, u)
            rows.append({"task": pan, "unit": u, "prompt_hash": R.phash(b["system"], b["prompt"]), "prompt_chars": len(b["prompt"])})
    pd.DataFrame(rows).to_csv(T4 / "프롬프트_해시_사전.csv", index=False, encoding="utf-8-sig")
    return rows


def main():
    ap = argparse.ArgumentParser(description="9편 실험 4단계 실행기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prompts")
    sub.add_parser("all")
    p = sub.add_parser("show")
    p.add_argument("pan")
    p.add_argument("unit")
    p = sub.add_parser("one")
    p.add_argument("pan")
    p.add_argument("model")
    p.add_argument("--run", type=int, default=1)
    p.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    RUN4.mkdir(parents=True, exist_ok=True)
    ctx = Ctx()
    if a.cmd == "prompts":
        rows = save_prompts(ctx)
        print("건별 해시", len(rows), "줄", Counter(r["task"] for r in rows))
        return
    if a.cmd == "show":
        print(ctx.build(a.pan, a.unit)["prompt"])
        return
    R.stop_if_billing_env()
    logf = RUN4 / "실행.log"

    def log(msg):
        line = f"{datetime.now():%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        with LOCK:
            with logf.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    if a.cmd == "one":
        ok = run_one(ctx, a.pan, a.model, a.run, a.limit, log)
        sys.exit(0 if ok else 2)
    t0 = time.time()
    log(f"#### 전체 실행 시작(계획 {len(PLAN)}단계)")
    for pan, model, run in PLAN:
        if not run_one(ctx, pan, model, run, 0, log):
            log(f"#### 멈춤 — {pan} {model} run{run} 에서: {STOP_WHY[0]} · 이번 실행 {(time.time() - t0) / 60:.1f}분")
            sys.exit(2)
    log(f"#### 전체 실행 끝 · 이번 실행 {(time.time() - t0) / 60:.1f}분 · 시도 {TALLY['시도']} · 실패 시도 {TALLY['실패 시도']}")


if __name__ == "__main__":
    main()
