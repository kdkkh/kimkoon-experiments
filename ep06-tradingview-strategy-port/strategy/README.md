# strategy/ — Pine 전략을 꽂는 틀

트레이딩뷰에서 만든 Pine 전략을 AI(클로드·GPT·제미나이…)로 파이썬에 옮겨 이 틀에 꽂고 → 백테스트로 트레이딩뷰 거래 목록과 대조 → 실시간 dry-run → 한투 **모의** 주문까지. **Pine 해석기가 아니다.** 전략 이식은 전략마다 한 번 AI 가 하는 일이고, 이 틀은 그 결과가 꽂히는 자리와 앞뒤 경로다.

## 구조

| 파일 | 하는 일 | 받는 것 → 내놓는 것 |
|---|---|---|
| `base.py` | 전략 공통 형식 — `Strategy`(자식은 `name`·`params`·`signals` 만), `empty_signals`, `validate_bars`, `parse_params` | 봉 DataFrame(`time, open, high, low, close, volume`) → 신호 DataFrame(`long_entry, long_exit, short_entry, short_exit` bool, short 는 항상 False) |
| `indicators.py` | Pine `ta.*` 대응 12개: `sma, ema, rma, tr, atr, rsi, supertrend, crossover, crossunder, highest, lowest, change`. Pine v6 공식 문서 정의대로, 외부 지표 라이브러리 안 씀 | pandas Series → 같은 index 의 Series |
| `ported/` | 이식한 전략. 파일 하나 = 전략 하나(`STRATEGY = 클래스`). 정답 예시 `supertrend_strategy.py`(트레이딩뷰 내장 "Supertrend strategy" 를 옮긴 것). `load_strategy("이름" 또는 "파일.py", **params)` | 이름·경로 → `Strategy` 인스턴스 |
| `PORTING_PROMPT.md` | AI 에 붙여 넣는 이식 프롬프트(v1, 한국어·영어) — 틀 규격·대응표 28항목·규칙·출력 템플릿 | Pine 소스 → AI 가 파이썬 파일 하나 |
| `validate.py` | 검증기 로직(→ `scripts/strategy_validate.py`) — 규격·금지·견본 실행·트레이딩뷰 거래 목록 대조·판정 | 전략 파일 (+ 봉, 거래 목록 CSV) → 통과/경고/실패 보고 |
| `data.py` | 봉 로더 — CSV 파일 읽기(`read_bars_csv`, 네트워크 없음) · 한투 일봉 FHKST03010100(100건씩 이어 받기)·당일 분봉 FHKST03010200(30건씩)·과거 분봉 FHKST03010230(`kis.quote.minute_bars_past`), 캐시 `data/bars/{code}_{tf}.csv`. 조회는 실전 키(조회만)가 기본, 호출 사이 0.35초 | 종목코드·기간 또는 CSV 경로 → 봉 DataFrame |
| `backtest.py` | 트레이딩뷰 Strategy Tester 기본 규칙 백테스트 — 신호는 봉 마감, 체결은 다음 봉 시가, 포지션 1개, 금액 기준 정수 주, 비용 기본 0 | 봉 + 신호 → 거래 목록(트레이딩뷰 형식)·거래 표·요약 |
| `live.py` | 실시간 실행기 — 봉이 닫히면 신호 → 기본 dry-run(계획만), `--paper-order` 일 때만 `kis.order.limit_order` 모의 주문. 하루 진입 상한(새 매수만, 청산은 상한 밖)·종목당 1포지션·금액 상한, 기록 `logs/strategy_live_YYYYMMDD.jsonl`(단계별 ms) | 종목코드·전략 → 주문 계획/모의 주문 기록 |

실행 스크립트: `scripts/strategy_backtest.py` · `scripts/strategy_validate.py` · `scripts/strategy_live.py`(머리말에 실행법). 테스트: `python -X utf8 -m pytest tests -q`.

## Pine 전략 하나를 옮기는 순서

1. **Pine 복사** — 트레이딩뷰 Pine 편집기에서 전략 소스를 처음부터 끝까지 전부 복사.
2. **AI 에 붙여 넣기** — `strategy/PORTING_PROMPT.md` 의 "붙여 넣을 프롬프트" 전체 + Pine 소스를 쓰는 AI(각 AI 의 가장 강한 모델)에 붙여 넣는다.
3. **저장** — AI 가 준 파이썬 파일을 `strategy/ported/<이름>_strategy.py` 로(클래스의 `name = "<이름>"` — 아래 `--strategy <이름>` 에 쓰는 값. 파일 이름으로도 찾아진다).
4. **검증기** — `python -X utf8 scripts/strategy_validate.py strategy/ported/<이름>_strategy.py`
   트레이딩뷰 거래 목록을 내보냈으면 `--code <종목코드> --tf 1d --days 365 --tv-trades 거래목록.csv` 까지.
5. **통과한 파일만** 다음으로. 거래 목록 없이 나온 '통과'는 규격·금지·실행 확인까지다 — 트레이딩뷰와 같은지는 거래 목록을 넣어야 확인된다. **AI 마다 결과가 다를 수 있으니 검증기를 통과한 파일만 쓴다.** "경고"면 검증기가 보여 준 첫 갈라진 거래·앞뒤 봉 값을 AI 에 그대로 주고 고치게 한 뒤 다시 4.
6. **백테스트 표 보기** — `python -X utf8 scripts/strategy_backtest.py --code <종목코드> --tf 1d --days 365 --strategy <이름> --dump`
7. **실시간 dry-run** — `python -X utf8 scripts/strategy_live.py --codes <종목코드> --strategy <이름>` (주문 계획만 찍힘)
8. **모의 주문** — 위에 `--paper-order` (모의 계좌로만. 실전 주문 경로는 없다)

## 트레이딩뷰와 대조하는 법
- 차트: 같은 종목·같은 봉(일봉/1분)·**차트 시간대 Asia/Seoul**.
- 전략 속성: 수수료 0·슬리피지 0(기본), "주문 체결 시 재계산"·"매 틱마다 계산"·Bar Magnifier 끔(기본), 초기 자본·수량은 손익 금액에만 영향 → **진입·청산 시각과 가격**으로 대조한다.
- 내장 "Supertrend strategy" 는 하락 전환 때 **short 진입**(롱을 뒤집어 숏)한다. 거래 목록에 숏 거래가 섞여도 검증기는 롱 거래만 본다(롱 청산 시각 = 숏 진입 시각이라 그대로 맞음). 롱만 보고 싶으면 편집기에서 사본을 만들어 숏 진입 줄(`strategy.entry(..., strategy.short)`)을 같은 ID 의 롱 청산(`strategy.close(롱 진입 ID)`)으로 바꿔 저장한 뒤 대조.
- 거래 목록 내보내기: Strategy Tester → 거래 목록(List of trades) → 내보내기(CSV). 열 이름은 도움말 화면 기준 `Trade #, Type, Date/Time, Signal, Price, Position size, Net P&L, Run-up, Drawdown, Cumulative P&L` 로 찾는다(파일 머리글의 정확한 글자·통화 꼬리표는 미확인 — 다르면 `--tv-cols "trade=…,type=…,time=…,price=…"`). 형식 견본은 `sample_data/fake_tv_trades.csv`(가짜 값).
- 봉별로 보려면 백테스트 `--dump` 의 `_봉신호.csv` 의 `supertrend`·`direction` 을 트레이딩뷰 데이터 창 값과 비교.

## 트레이딩뷰와 결과가 다를 수 있는 이유
1. **체결 시점 규칙** — 우리는 Pine 기본(`process_orders_on_close=false`)대로 다음 봉 시가. 트레이딩뷰에서 "봉 마감에 주문 처리"를 켰거나 Bar Magnifier·"매 틱마다 계산"을 켜면 달라진다.
2. **수량 규칙** — 내장 전략은 자기자본 15%(복리), 우리는 금액 기준(기본 100만 원)·정수 주. 손익 금액·누적 수익률은 달라도 시각·가격은 같아야 한다. 트레이딩뷰가 현금 기준 수량을 신호 봉 종가로 계산하는지는 미확인(`--qty-basis fill_open` 으로 바꿔 볼 수 있음).
3. **가격 단위(호가 단위 반올림)** — 원본 작업 실측: 한 종목 일봉 거래 10건에서 트레이딩뷰 체결가는 모두 500원 단위였고, 한투 시가(100원 단위)를 500원 단위로 반올림하면 10건 모두 같았다. 트레이딩뷰가 종목의 가격 단위(mintick)를 KRX 호가 단위와 다르게 잡을 수 있다 → 검증기는 ±0.1% 또는 여러 단위(500·1000·100·50·10·5·1원) 반올림 일치를 같은 가격으로 본다.
4. **수수료·슬리피지** — 양쪽 기본 0. 실제 비용(`--commission-pct`·`--sell-tax-pct`·`--slippage-ticks`)을 넣으면 트레이딩뷰 값과 달라진다. 슬리피지 호가 단위는 우리 `kis.order.tick_size`, 트레이딩뷰는 종목 mintick.
5. **데이터 소스** — 트레이딩뷰 KRX 시세 vs 한투. 수정주가 처리(우리 일봉은 `FID_ORG_ADJ_PRC=0` 수정주가, 트레이딩뷰 "배당 조정" 설정), 시가·고가·저가가 거래소 동시호가를 어떻게 넣는지가 다를 수 있다.
6. **봉 시각 기준** — 일봉 날짜, 분봉은 시작 시각(한투 "14:25" = 14:25:00~14:25:59). 차트 시간대가 서울이 아니면 시각이 밀린다.
7. **거래량·거래 시간 정의** — 거래소(J)만인지 넥스트레이드 포함(통합)인지, 2026-09-14 부터의 애프터마켓(16:00~20:00)이 일봉·분봉에 들어가는지, 15:30 종가 단일가 봉, 거래 없는 분(한투 당일 분봉은 장 마감 뒤에도 거래량 0 봉을 채워 줌 — 실행기는 뺀다)의 처리.
8. **지표 초기값과 데이터 길이** — `rma`(ATR·RSI)는 앞 값이 계속 이어지는 평균이라 시작점에 따라 값이 다르다. 트레이딩뷰는 훨씬 긴 과거부터 계산하므로 우리 첫 몇 거래가 다를 수 있다 → `--days` 를 늘리거나 검증기 `--warmup` 으로 앞 구간을 대조에서 뺀다. 검증기는 순번이 아니라 **진입 봉끼리** 짝지어, 창 시작에 한쪽에만 있는 거래 하나 때문에 전체가 밀리지 않게 한다. `ta.ema` 첫 값(문서 예시 = 첫 값 시작, 내장 함수 실제 동작 미확인)도 같은 이유.
9. **미완성 봉** — 장중에 받은 오늘 일봉은 아직 바뀌는 중. 우리는 20:05 전이면 뺀다(`--keep-today` 로 넣기).
10. **마지막 봉 신호** — 마지막 봉에서 난 신호는 양쪽 다 아직 체결 전. 우리는 "대기"로 따로 보여 준다.
11. **열린 거래** — 트레이딩뷰는 마지막 거래를 Open 으로 두고 평가 손익을 보여 준다. 우리 요약의 "닫힌 거래 수"에는 넣지 않는다.

## 한계
- 봉 안 가격으로 체결하는 주문(`strategy.exit` 의 stop·limit·trail, 지정가 진입)은 아직 없다 — 신호 → 다음 봉 시가만.
- 다른 시간봉 참조(`request.security`)·세션 함수·피라미딩·공매도 없음. 포지션 1개 롱만.
- 실시간은 REST 로 1분봉을 봉 마감 3초 뒤 받는다(웹소켓 봉 만들기 아님) → 신호가 수 초 늦다. 시각은 jsonl 에 남아 잴 수 있다.
- 실시간 지표 예열은 오늘 120봉 + `data/bars/{code}_1m.csv` 캐시(실행기가 끝날 때 저장). 트레이딩뷰보다 짧은 과거라 rma 값이 조금 다를 수 있다.
- 체결통보(웹소켓)는 원본에서 동작을 확인하지 못해 이 공개판에 없다. 포지션은 이 실행기 기록 기준이며 계좌 잔고와 맞추는 단계는 없다(기존 보유분은 건드리지 않음).
- 일 손실 한도·비상 정지는 아직 없다.
- 백테스트 결과는 과거 데이터의 기계적 계산일 뿐, 매매 권유나 수익 보장이 아니다.
