# AGENTS.md — 이 폴더를 읽는 AI 에게

사람용 설명은 `README.md`. 이 파일은 같은 지도를 에이전트가 바로 쓰게 줄인 것이다.

> 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.

## 먼저 지킬 것

1. **모델을 부르는 명령은 사용자가 분명히 시킬 때만 돈다**: `ep09_run.py ping|a|b` · `ep09_run3.py ping|one|all` · `ep09_run4.py one|all` · `ep09_run5.py one|all`. 이 명령들은 `claude -p`(사용자의 구독)를 부르고 한도를 쓴다. `prompts` · `show` · `stats` 와 채점기 · 과제 생성기 · 가짜 검사는 호출하지 않는다.
2. 환경 변수 `ANTHROPIC_API_KEY` · `ANTHROPIC_AUTH_TOKEN` · `CLAUDE_CODE_USE_BEDROCK` · `CLAUDE_CODE_USE_VERTEX` 가운데 하나라도 있으면 실행기는 스스로 멈춘다(사용량 과금 방지). 이 검사를 빼거나 우회하지 않는다.
3. 실제 자료는 이 폴더에 없다. 사용자가 자기 자료를 `data/` 에 두면 그것은 저장소에 올리지 않는다(`.gitignore` 의 `data/`). 뉴스 제목 · 공시 원문 · 분봉은 약관상 다시 나눠 줄 수 없다.
4. 결과 숫자를 매매 판단이나 종목 추천으로 바꿔 말하지 않는다. 수치는 잰 조건(구독 · 추론 강도 low · 제목만 · 비용 전 수익률)과 함께 사실로만 전한다.

## 바로 할 수 있는 것

| 하려는 일 | 명령(이 폴더에서) |
|---|---|
| 전 과정을 가짜 견본으로(호출 0) | `python -X utf8 scripts/ep09_offline_check.py [--data <빈 폴더>]` |
| 채점기 자체 시험 | `scripts/ep09_grade.py selftest` · `ep09_grade3.py selftest` · `ep09_grade4.py selftest` · `ep09_grade5.py selftest` (표본·과제를 먼저 만들어야 함 — 가짜 검사가 순서대로 한다) |
| 보낼 프롬프트 보기(호출 0) | `ep09_run.py show-a <접수번호>` · `ep09_run3.py show H3 <접수번호>` · `ep09_run4.py show N N001` · `ep09_run5.py show J5 <접수번호>` |
| 프롬프트 전문 · 건별 해시 저장(호출 0) | `ep09_run.py prompts` · `ep09_run3.py prompts` · `ep09_run4.py prompts` · `ep09_run5.py prompts` |
| 자료 뿌리 바꾸기 | 어느 명령에나 `--data <폴더>` 또는 환경 변수 `EP09_DATA` |

## 지도(파일 → 하는 일 → 만드는 것)

| 단계 | 과제 생성 | 실행기(모델 호출) | 채점 | 만드는 곳(`data/ep09/`) |
|---|---|---|---|---|
| 1·2 시험 | `ep09_sample.py` | `ep09_run.py` | `ep09_grade.py` | `sample_*.csv` · `run/` · `채점/` |
| 3 읽기·방향 | `ep09_tasks3.py build` | `ep09_run3.py` | `ep09_grade3.py all` · `ep09_review3.py` · `ep09_answer_returns.py`(탐색) | `과제3/` · `sample_B3.csv` · `run3/` · `채점3/` |
| 4 가격 갈래 | `ep09_tasks4.py build` · `baseline` | `ep09_run4.py` | `ep09_grade4.py all` | `과제4/` · `run4/` · `채점4/` |
| 5 따지기 | `ep09_tasks5.py build` | `ep09_run5.py` | `ep09_grade5.py all` · `ep09_review5.py review|examples` | `과제5/` · `run5/` · `채점5/` |

공통 모듈: `ep09_paths.py`(자료 뿌리) · `dart_doc.py`(원문 zip → 글) · `dart_tables.py`(정정 표 읽기) · `prepost_features.py`(제목 특징, kiwipiepy).
가짜 견본: `ep09_fake_data.py`(작업 공간) · `ep09_fake_answers.py`(실행기의 `call_claude` 만 가짜로 바꿔 끝까지 돌림, `subprocess` 막음) · `sample_data/`(앞 몇 줄 — 형식 보기용).

## 부품 경계(받는 것 → 내놓는 것)

- 표본·과제 생성기: 자료 뿌리의 원문 zip · 구조화 CSV · events.csv · prepost_events.csv · 종목 이름표 → `data/ep09/` 의 표본 · 정답표 · 묶음(시드 고정, 같은 입력이면 같은 결과).
- 실행기: 표본 · 정답 없는 프롬프트 → `run*/<과제>_<모델>_run<N>.jsonl`(호출 한 번 = 한 줄: 모델 ID · 프롬프트 해시 · 토큰 · 원문 답 · 파싱한 답 · 상태). 끝난 건은 다시 돌려도 건너뛴다.
- 채점기: 실행 기록 + 정답표 → 건별 CSV + 집계 md. 모델을 부르지 않는다. 정답은 회사가 낸 구조화 값 · 가격이고, 채점은 결정적 코드다.
- 자료 형식(열 이름 · 뜻)은 README 5절, 없는 자료와 구하는 법은 README 6절, 모델 호출 방식과 멈춤 규칙은 README 7절.

## 자주 받는 요청 → 볼 곳

- "프롬프트 전문이 뭐야" → `ep09_run.py` 의 `SYSTEM_A` · `RULES_A` · `SYSTEM_B` · `HEAD_B` · `TAIL_B`, `ep09_run3.py` 의 `SYSTEM_H2` · `RULES_H2` · `SYSTEM_H3` · `RULES_H3` · `SYSTEM_H5` · `RULES_H5` · `TAIL_BF`, `ep09_run4.py` 의 `DEF_LINE` · `Q_LINES` · `TAIL_N` · `TAIL_F` · `EX_HEAD`, `ep09_run5.py` 의 `SYSTEM` · `TAIL_C5` · `TAIL_S5` · `TAIL_J5`. 질문 목록: `ep09_sample.FIELDS`(+ `ep09_tasks3.A3_RENAME`) · `ep09_tasks3.H1_Q` · `ep09_tasks3.H3_ITEMS` · `ep09_tasks5.J5_BANK`.
- "채점 기준이 뭐야" → `ep09_grade.py` 머리 주석(엄격/관용 · 자릿수 · 부호 · 지어내기), `ep09_grade3.py` 머리 주석(반올림 과제 · 원문 단위 그대로 · 다른 문서 값), `ep09_grade4.py` 머리 주석(균형 정확도 · 모름 = 오답 판), `ep09_grade5.py` 머리 주석(짝 재현율 · 요약 속 수 대조 · 인용 일치).
- "내 자료로 돌리려면" → README 5·6절대로 자료를 두고 `ep09_tasks3.CORRECTION_OVERRIDE` · `ep09_tasks3.H5_DOCS` 를 자기 것으로 바꾼다(지금 값은 가짜 견본용).
- "영상 수치가 어디서 나왔나" → README 2절 표의 '만든 코드' 칸. 영상 S06 · S06b(가격으로 가른 뉴스 등)는 이 폴더에 없다.
