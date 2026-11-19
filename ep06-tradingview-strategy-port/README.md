# ep06 — 트레이딩뷰 전략을 AI 로 옮겨 내 프로그램에서 돌리기

유튜브 **김쿤 | AI 자동매매** 6편 "트레이딩뷰 전략을 AI 로 옮겨 내 프로그램에서"의 코드입니다.
영상: https://youtu.be/_aBWbUn3JUA

> **모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.**
> 이 코드에는 **실전 주문 경로가 없습니다**(주문은 모의투자 설정일 때만 나가고, 기본은 주문 계획만 찍는 dry-run).
> 백테스트·신호는 과거 데이터와 규칙의 기계적 계산이며 매매 권유나 수익 보장이 아닙니다.

이 폴더 하나만 떼어 가도 돌아갑니다(폴더 밖 모듈에 기대지 않음). Python 3.11 에서 시험했습니다. 라이선스는 MIT(저장소 맨 위 `LICENSE`).
문서와 주석의 "원본" · "원본 작업"은 영상을 만들 때 쓴 비공개 작업본을 가리킵니다(이 공개판은 거기서 골라 다듬은 것).

## 무엇을 하나

트레이딩뷰 Pine 전략 → (AI 가 옮김) → 파이썬 전략 파일 → **검증기**로 규격·트레이딩뷰 거래 목록 대조 → 백테스트 → 실시간 dry-run → 한국투자증권 **모의** 주문.

Pine 해석기가 아닙니다. 전략마다 한 번, 각자의 AI 가 `strategy/PORTING_PROMPT.md` 의 프롬프트로 옮기고, 이 틀은 그 결과를 꽂아 시험하는 자리입니다.

## 막혔던 자리 (왜 이렇게 만들었나)

1. **트레이딩뷰 알림·웹훅으로는 주문을 낼 수 없다(약관).** 우리가 읽은 트레이딩뷰 이용약관(Terms of Use) 3조는 알림·웹훅을
   표시 전용(display-only)으로만 허락한다 — 원문 "charts, alerts, webhooks, and any other forms of information, are licensed for exclusive display-only use",
   금지 예시에 automated trading · automated order generation 이 들어 있다(https://www.tradingview.com/policies/ , 2026-11-03 과 2026-11-19 에 읽은 판.
   요금제와 무관. 우리의 읽기이며 법률 해석이 아니다. 약관은 바뀔 수 있으니 직접 확인하세요). 그래서 "트레이딩뷰가 신호를 보내면 내 프로그램이 주문"하는 구조 대신,
   **전략 자체를 파이썬으로 옮겨** 내 프로그램 안에서 계산합니다. 트레이딩뷰는 차트·거래 목록을 눈으로 대조하는 데만 씁니다.
2. **AI 마다 옮긴 결과가 다를 수 있다.** 같은 Pine 이라도 AI·모델·시도마다 다르게 옮길 수 있어, 사람이 코드를 읽는 대신
   검증기(`scripts/strategy_validate.py`)가 규격·금지 import·견본 실행·트레이딩뷰 거래 목록 대조로 판정하고 **통과한 파일만** 씁니다.
3. **트레이딩뷰와 결과를 맞출 때 걸린 것** (자세히는 `strategy/README.md` "결과가 다를 수 있는 이유" 11가지)
   - 체결 규칙: Pine 기본은 신호 봉 마감 → **다음 봉 시가 체결**. 백테스트 러너를 그 규칙에 맞췄다.
   - 초기 자본·수량: 내장 전략은 자기자본 15%, 우리는 금액 기준 정수 주 → 손익 금액은 달라도 **진입·청산 시각과 가격**으로 대조.
   - 가격 단위 반올림: 원본 작업 실측에서 트레이딩뷰 체결가가 KRX 호가 단위와 다른 단위(500원)로 반올림돼 나왔다 →
     검증기는 ±0.1% 또는 여러 가격 단위 반올림이 같으면 같은 가격으로 본다.
   - 지표 예열: ATR·RSI 의 rma 는 시작점에 따라 값이 달라 처음 몇 거래가 어긋날 수 있다 → 진입 봉끼리 짝짓고 `--warmup` 으로 앞 구간 제외.
   - 공매도: 내장 "Supertrend strategy" 는 하락 전환 때 숏으로 뒤집는다. 이 틀은 롱만 → 같은 시점을 롱 청산으로 옮겼다.
4. **한국투자 API 에서 막히는 것** (자세히는 `kis/README.md`)
   - 접근 토큰은 1일 1회 발급이 원칙, 잦은 발급은 이용 제한 → 캐시를 다시 쓴다.
   - 초당 호출 한도(`EGW00201`) → 호출 사이 0.35초, 걸리면 1초 쉬고 한 번 더.
   - 일봉은 한 번 100건, 당일 분봉은 한 번 30건, 과거 분봉은 한 번 120건 → 이어 받는다.
   - 과거 분봉(FHKST03010230)은 공식 목록상 모의투자 미지원 → 시세 조회는 실전 키(조회만)가 기본.
   - 현재가가 호가 단위 사이 값으로 올 때가 있다 → 주문 전에 호가 단위로 맞춘다.

## 지도

| 경로 | 하는 일 | 입력 | 출력 |
|---|---|---|---|
| `strategy/base.py` | 전략 공통 형식(`Strategy`·`empty_signals`·봉/신호 검사) | 봉 DataFrame `time, open, high, low, close, volume` | 신호 DataFrame `long_entry, long_exit, short_entry, short_exit`(bool) |
| `strategy/indicators.py` | Pine `ta.*` 대응 12개(sma·ema·rma·tr·atr·rsi·supertrend·crossover·crossunder·highest·lowest·change) | pandas Series | 같은 index 의 Series |
| `strategy/ported/` | 옮긴 전략 모음. 정답 예시 `supertrend_strategy.py` | — | `load_strategy("이름")` |
| `strategy/PORTING_PROMPT.md` | AI 에 붙여 넣는 이식 프롬프트(한국어·영어) | Pine 소스 | AI 가 파이썬 파일 하나 |
| `strategy/validate.py` | 검증기 로직 | 전략 파일 (+ 봉, 트레이딩뷰 거래 목록 CSV) | 통과/경고/실패 보고 |
| `strategy/backtest.py` | 트레이딩뷰 기본 규칙 백테스트 | 봉 + 신호 | 거래 목록·거래 표·요약 |
| `strategy/data.py` | 봉 로더: CSV 읽기(네트워크 없음) · 한투 일봉/분봉 조회 + `data/bars/` 캐시 | CSV 경로 또는 종목코드·기간 | 봉 DataFrame |
| `strategy/live.py` | 실시간 실행기(기본 dry-run, `--paper-order` 일 때만 모의 주문) | 종목코드·전략 | 화면 + `logs/strategy_live_YYYYMMDD.jsonl` |
| `kis/` | 한투 API 연결(설정·토큰·REST·시세·모의 주문 안전장치) | 설정 파일 `kis_devlp.yaml` | — |
| `scripts/strategy_backtest.py` | 백테스트 실행 | `--csv` 또는 `--code` | 화면 + `data/backtest/*_거래목록.csv`·`_거래.csv`·`_요약.json` |
| `scripts/strategy_validate.py` | 검증기 실행 | 전략 파일·이름 (+ `--csv`/`--code`, `--tv-trades`) | 화면 판정, 실패면 끝내는 코드 1 |
| `scripts/strategy_live.py` | 실시간 실행 | `--codes` | 화면 + jsonl 기록 |
| `sample_data/` | **가짜** 일봉 400개 + 트레이딩뷰 거래 목록 형식 견본 | — | 네트워크 없는 실행용 |
| `tests/` | 지표 손 계산·백테스트 규칙·검증기·실행기 가드·견본 실행 | — | `pytest` |
| `config.example.yaml` | 설정 파일 예시(값 비어 있음) | — | — |

실행 중에 생기는 `data/`(봉 캐시·백테스트 결과)·`logs/`(주문·실행 기록)는 저장소에 싣지 않습니다.

## 실행

```
pip install -r requirements.txt

# 1) 네트워크 없이 — 시험과 견본 실행 (설정 파일 없어도 됨)
python -X utf8 -m pytest tests -q
python -X utf8 scripts/strategy_validate.py strategy/ported/supertrend_strategy.py
python -X utf8 scripts/strategy_validate.py supertrend --csv sample_data/fake_daily_bars.csv --tv-trades sample_data/fake_tv_trades.csv
python -X utf8 scripts/strategy_backtest.py --csv sample_data/fake_daily_bars.csv --strategy supertrend

# 2) 한투 조회로 (설정 파일 필요, 주문 없음)
python -X utf8 scripts/strategy_backtest.py --code <종목코드> --tf 1d --days 365 --strategy supertrend --dump
python -X utf8 scripts/strategy_validate.py supertrend --code <종목코드> --tf 1d --days 365 --tv-trades 거래목록.csv

# 3) 장중 실시간 — 기본 dry-run(주문 계획만)
python -X utf8 scripts/strategy_live.py --codes <종목코드> --strategy supertrend --once

# 4) 모의 주문 (모의투자 계좌로만)
python -X utf8 scripts/strategy_live.py --codes <종목코드> --strategy supertrend --paper-order --amount 500000 --max-orders 3
```

`<종목코드>` 는 직접 넣습니다(6자리 국내 주식 단축코드). 이 저장소는 어떤 종목도 고르거나 권하지 않습니다.

## 들어 있지 않은 것과 구하는 법

| 없는 것 | 구하는 법 |
|---|---|
| 한국투자 앱키·시크릿·계좌 | 한국투자증권 계좌를 열고 KIS Developers 에서 Open API 를 신청(실전·모의투자 앱키 따로). `config.example.yaml` 을 `~/KIS/config/kis_devlp.yaml` 로 복사해 채운다(저장소 밖). 공식 예제 저장소(github.com/koreainvestment/open-trading-api)의 `kis_devlp.yaml` 을 그대로 써도 된다 |
| 실제 일봉·분봉 데이터 | 설정을 채우고 `--code` 로 실행하면 한투에서 받아 `data/bars/` 에 캐시. 다른 곳에서 받은 일봉은 `time, open, high, low, close, volume` 열 CSV 로 만들어 `--csv` |
| 트레이딩뷰 거래 목록 | 트레이딩뷰 Strategy Tester → 거래 목록 → 내보내기(CSV). 차트 시간대 Asia/Seoul. 영상에서는 내보내기를 쓰지 않고 화면의 거래 목록을 같은 열 형식으로 옮겨 적어 썼다 |
| 트레이딩뷰 내장 "Supertrend strategy" Pine 원문 | 싣지 않았다(이용 조건 미확인). 트레이딩뷰 Pine 편집기에서 내장 전략을 직접 연다. `strategy/ported/supertrend_strategy.py` 머리말에 원본이 하는 일을 우리말로 적었다 |
| 체결통보(웹소켓)·일 손실 한도·비상 정지·계좌 잔고와 포지션 맞추기 | 없음(원본에서도 미완성) |
| 실전 주문 경로 | 없음. 넣지 않았다 |

## AI 에게 이렇게 시키면 됩니다

- "이 폴더의 `AGENTS.md` 와 `README.md` 를 읽고, 네트워크 없이 `pytest` 와 `sample_data` 견본 실행을 돌려서 결과를 알려 줘. 설정 파일이나 주문은 건드리지 마."
- "`strategy/PORTING_PROMPT.md` 의 한국어 프롬프트대로 아래 Pine 전략을 `strategy/ported/my_strategy.py` 로 옮기고, `scripts/strategy_validate.py` 로 검증해서 '통과'가 나올 때까지 고쳐 줘. (Pine 소스 붙여 넣기)"
- "내 프로그램에 `strategy/indicators.py` 의 `supertrend` 와 `strategy/backtest.py` 의 체결 규칙만 가져가고 싶어. 두 파일이 기대는 것(`strategy/base.py`, `kis/order.py` 의 `tick_size`)까지 포함해 필요한 부분만 골라 옮겨 줘."

## 부품을 떼어 갈 때

- `strategy/indicators.py` 는 pandas · numpy 만 쓴다. 혼자 떼어 가도 된다.
- `strategy/backtest.py` 는 `kis.order` 에서 `tick_size` 하나만 쓰는데, 그 import 가 `kis/` 전체(`requests` · `PyYAML`)를 끌어온다. 백테스트만 가져갈 때는 `tick_size`(순수 함수 몇 줄)를 복사해 import 를 바꾸면 `kis/` 가 필요 없다.
- `kis/config.py` 는 import 될 때 표준 출력을 UTF-8 로 바꾼다(윈도우 한글 깨짐 방지). 다른 프로그램에 넣을 때 알아 둘 것.
- 전략 파일은 `from strategy.base import …` 처럼 패키지 이름 `strategy` 에 맞춰 쓴다. 폴더 이름을 바꾸면 import 도 같이 바꾼다.
- 봉 CSV 의 `time` 은 `2024-01-02T00:00:00+09:00` 꼴(시간대가 없으면 한국 시간으로 읽는다). 실시간 실행기는 PC 시계가 한국 시간이라고 가정한다.
- 옮긴 전략 파일 이름은 `<이름>_strategy.py`, 실행할 때는 `--strategy <이름>`(클래스의 `name`). 파라미터는 `--param 이름=값` 을 여러 번.
