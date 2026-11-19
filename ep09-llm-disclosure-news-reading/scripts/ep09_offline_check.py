# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 공개판에서 새로 쓴 파일(원본 없음).
"""가짜 견본으로 전 과정을 한 번에 돌려 본다 — 모델·네트워크·`claude` 명령을 부르지 않는다.

순서: 가짜 작업 공간 → 1단계 표본 → 채점기 자체 시험 → (단계마다) 과제 만들기 → 프롬프트 전문·해시 → 가짜 답으로 실행기 돌리기
      → 채점 · 집계 → 원문 대조 자료. 한 걸음이라도 실패하면 거기서 멈추고 0 이 아닌 값으로 끝난다.
결과는 자료 뿌리(기본 data/) 아래 ep09/ 에 실제 실행과 같은 이름으로 쌓인다. 숫자는 가짜 답의 것이라 뜻이 없다.

쓰기(이 폴더에서):  python -X utf8 scripts/ep09_offline_check.py [--data <빈 폴더 또는 가짜 작업 공간>]
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from ep09_paths import DATA

HERE = Path(__file__).resolve().parent
EP = "ep09"


def steps():
    a1 = str(DATA / EP / "run" / "답_A_run1.jsonl")
    b1 = str(DATA / EP / "run" / "답_B_run1.jsonl")
    return [
        ("가짜 작업 공간", ["ep09_fake_data.py"]),
        ("1단계 표본", ["ep09_sample.py"]),
        ("2단계 채점기 자체 시험", ["ep09_grade.py", "selftest"]),
        ("2단계 가짜 답(실행기 ep09_run)", ["ep09_fake_answers.py", "2"]),
        ("2단계 채점 A", ["ep09_grade.py", "a", "--answers", a1, "--name", "run1"]),
        ("2단계 채점 B", ["ep09_grade.py", "b", "--answers", b1, "--name", "run1"]),
        ("2단계 집계", ["ep09_run.py", "stats"]),
        ("3단계 과제", ["ep09_tasks3.py", "build"]),
        ("3단계 정답표 점검", ["ep09_tasks3.py", "check"]),
        ("3단계 프롬프트 전문·해시", ["ep09_run3.py", "prompts"]),
        ("3단계 채점기 자체 시험", ["ep09_grade3.py", "selftest"]),
        ("3단계 가짜 답(실행기 ep09_run3)", ["ep09_fake_answers.py", "3"]),
        ("3단계 채점·집계", ["ep09_grade3.py", "all"]),
        ("3단계 원문 대조 자료", ["ep09_review3.py"]),
        ("3단계 답별 수익률(탐색)", ["ep09_answer_returns.py"]),
        ("4단계 과제", ["ep09_tasks4.py", "build"]),
        ("4단계 기준선", ["ep09_tasks4.py", "baseline"]),
        ("4단계 채점기 자체 시험", ["ep09_grade4.py", "selftest"]),
        ("4단계 프롬프트 전문·해시", ["ep09_run4.py", "prompts"]),
        ("4단계 가짜 답(실행기 ep09_run4)", ["ep09_fake_answers.py", "4"]),
        ("4단계 채점·집계", ["ep09_grade4.py", "all"]),
        ("5단계 과제", ["ep09_tasks5.py", "build"]),
        ("5단계 프롬프트 전문·해시", ["ep09_run5.py", "prompts"]),
        ("5단계 채점기 자체 시험", ["ep09_grade5.py", "selftest"], "전체 통과"),
        ("5단계 가짜 답(실행기 ep09_run5)", ["ep09_fake_answers.py", "5"]),
        ("5단계 채점·집계", ["ep09_grade5.py", "all"]),
        ("5단계 원문 대조 자료", ["ep09_review5.py", "review"]),
        ("5단계 실례", ["ep09_review5.py", "examples"]),
    ]


def main():
    env = dict(os.environ, EP09_DATA=str(DATA), PYTHONUTF8="1")
    env.pop("ANTHROPIC_API_KEY", None)                     # 이 검사는 호출을 하지 않지만, 자식 과정에 키를 넘기지도 않는다
    t0 = time.time()
    done = []
    for st in steps():
        label, args = st[0], st[1]
        must = st[2] if len(st) > 2 else None
        t = time.time()
        p = subprocess.run([sys.executable, "-X", "utf8", str(HERE / args[0]), *args[1:]], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        ok = p.returncode == 0 and (must is None or must in out)
        print(f"[{'통과' if ok else '실패'}] {label} · {time.time() - t:.1f}초", flush=True)
        if not ok:
            print(out[-3000:])
            sys.exit(1)
        done.append(label)
    print(f"\n전 과정 {len(done)}걸음 통과 · {time.time() - t0:.0f}초 · 모델 호출 0 · 결과 {DATA / EP}")


if __name__ == "__main__":
    main()
