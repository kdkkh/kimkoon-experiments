# AGENTS.md — AI 도구가 먼저 읽는 지도

이 폴더는 유튜브 **김쿤 | AI 자동매매** 6편(https://youtu.be/_aBWbUn3JUA)의 코드다.
트레이딩뷰 Pine 전략을 파이썬으로 옮겨(이식) 검증 → 백테스트 → 실시간 dry-run → 한국투자증권 **모의** 주문까지 하는 틀.
사람용 설명은 `README.md`, 막혔던 자리와 트레이딩뷰 대조법은 `strategy/README.md`, 한투 API 는 `kis/README.md`.

모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.

## 이 폴더에서 일할 때 지킬 것
1. **주문을 내지 않는다.** `scripts/strategy_live.py --paper-order` 는 사용자가 직접 요청할 때만. 기본은 dry-run(계획만).
   실전 주문 경로는 없다 — 새로 만들지 않는다(`kis/order.py` 의 `check` 가 모의 설정이 아니면 거절).
2. **설정·토큰을 열거나 출력하지 않는다.** `~/KIS/config/kis_devlp.yaml`(또는 `KIS_CONFIG_DIR`), `tk_v.json`·`tk_p.json`.
   설정이 맞는지만 보려면 `python -X utf8 -c "from kis import config; print(config.status())"` (키별 채워짐 여부만 나옴).
   설정 파일이 아직 없으면 이 명령은 `FileNotFoundError` 로 끝난다 — 정상이다. 견본 실행과 pytest 에는 설정이 필요 없다.
3. **네트워크 없이 먼저 확인한다.** `python -X utf8 -m pytest tests -q` 와 `sample_data/` 견본 실행은 설정·네트워크 없이 돈다.
4. 옮긴 전략은 `strategy/PORTING_PROMPT.md` 규격으로, **검증기 판정이 '통과'인 파일만** 쓴다.
   - 옮기는 일의 시작점은 `strategy/README.md` 의 "Pine 전략 하나를 옮기는 순서" → `strategy/PORTING_PROMPT.md`(대응표·템플릿) → 예시 `strategy/ported/supertrend_strategy.py`.
   - 파일은 `strategy/ported/<이름>_strategy.py`, 클래스의 `name = "<이름>"`. `--strategy <이름>` 은 클래스 `name` 으로도, 파일 이름(확장자 뺀 것)으로도 찾는다(`strategy/ported/__init__.py`).
   - **트레이딩뷰 거래 목록(`--tv-trades`) 없이 나온 '통과'는 규격·금지 import·실행 확인까지다.** 지표 값·신호가 트레이딩뷰와 같다는 뜻이 아니다. 사용자에게 보고할 때 "트레이딩뷰 대조 안 함"을 밝힌다.
   - `sample_data/fake_tv_trades.csv` 는 Supertrend 전용 견본이다. 다른 전략에 넣으면 '실패'가 나오는 것이 정상이다.
   - dry-run(`strategy_live.py`)도 시세 조회는 실제로 나간다 → 설정 파일이 필요하다. 설정 없이 되는 것은 `--csv` 견본 실행과 pytest 뿐이다.
5. 종목을 고르거나 권하지 않는다. 종목코드는 사용자가 준 값만 쓴다.

## 지도 (파일 → 하는 일 → 입력 → 출력)

| 경로 | 하는 일 | 입력 | 출력 |
|---|---|---|---|
| `strategy/base.py` | 전략 형식 `Strategy`(name·params·signals), `empty_signals`, `validate_bars`, `validate_signals`, `parse_params` | 봉 DataFrame(`time, open, high, low, close, volume`, time 은 KST) | 같은 index 의 신호 DataFrame(`long_entry, long_exit, short_entry, short_exit` bool, short 는 항상 False) |
| `strategy/indicators.py` | Pine `ta.*` 대응: `sma ema rma tr atr rsi supertrend crossover crossunder highest lowest change` | Series | Series(같은 index). `supertrend` 는 (선, 방향 -1 상승/1 하락) |
| `strategy/ported/__init__.py` | `load_strategy(이름 또는 .py 경로, **params)`, `strategy_class` | 이름·경로 | Strategy 인스턴스 |
| `strategy/ported/supertrend_strategy.py` | 정답 예시: 트레이딩뷰 내장 "Supertrend strategy" 이식(롱만) | — | — |
| `strategy/PORTING_PROMPT.md` | AI 이식 프롬프트 v1(한국어·영어), 대응표 28항목, 출력 템플릿 | Pine 소스 | 파이썬 파일 하나 |
| `strategy/validate.py` | `validate(target, bars, params, tv_trades, tv_cols, amount, tf_minutes, warmup_bars)` → `Report`(verdict 통과/경고/실패), `sample_bars()` 합성 봉, `read_tv_trades()` | 전략·봉·트레이딩뷰 거래 목록 CSV | Report |
| `strategy/backtest.py` | `run_backtest(bars, sig, amount, commission_pct, sell_tax_pct, slippage_ticks, qty_basis)` → `BacktestResult(trades, tv_list, summary, equity, pending, notes)` | 봉·신호 | 결과 |
| `strategy/data.py` | `read_bars_csv(path)`(네트워크 없음), `load_daily`, `fetch_daily`, `fetch_minute_today`, `fetch_minute_past`, `resample_minutes`, `drop_unfinished_*`, 캐시 `data/bars/` | CSV 또는 종목코드 | 봉 DataFrame |
| `strategy/live.py` | `LiveRunner(codes, strategy, tf_minutes, amount, max_orders, lookback, paper_order=False, data_mode="real")`, `round_tick` | 종목·전략 | `logs/strategy_live_YYYYMMDD.jsonl` |
| `kis/config.py` | `load("paper")` / `load("real")` → `KisConfig`, `status()`, `mask_account()` | `kis_devlp.yaml` | 설정(비밀값은 repr 에 안 나옴) |
| `kis/auth.py` | `get_token(cfg)` 토큰 캐시 재사용 | 설정 | 토큰(출력 안 함) |
| `kis/client.py` | `get`, `post`, `KisError` | 경로·tr_id·인자 | 응답 dict |
| `kis/quote.py` | `current_price`, `minute_bars_past` | 종목코드 | 응답 |
| `kis/order.py` | `limit_order`(모의만), `check`, `tick_size`, `MAX_ORDER_WON`(100만 원) | 모의 설정·주문 | 주문 기록 `logs/orders.jsonl` |
| `scripts/strategy_backtest.py` | 백테스트 CLI (`--csv` 또는 `--code`) | — | 화면 + `data/backtest/` |
| `scripts/strategy_validate.py` | 검증기 CLI (`--csv`·`--code`·`--tv-trades`·`--tv-cols`·`--warmup`) | — | 화면, 실패면 끝내는 코드 1 |
| `scripts/strategy_live.py` | 실시간 CLI (`--codes` 필수, 기본 dry-run, `--paper-order`) | — | 화면 + jsonl |
| `sample_data/` | 가짜 일봉 `fake_daily_bars.csv`(=`sample_bars()`), 가짜 거래 목록 `fake_tv_trades.csv` | — | — |
| `tests/` | pytest 36개(지표 손 계산·백테스트 규칙·검증기·실행기 가드·견본 실행) | — | — |

부품 경계: 전략(`ported/`)은 **신호만** 낸다(주문·수량·가격 코드 없음, import 는 pandas·numpy·math·`strategy.base`·`strategy.indicators` 만).
체결 규칙은 `backtest.py`(다음 봉 시가)와 `live.py`(현재가 지정가)가 정한다. 한투 호출은 `kis/` 와 `strategy/data.py` 에만 있다.

## 실행 명령
```
pip install -r requirements.txt
python -X utf8 -m pytest tests -q
python -X utf8 scripts/strategy_validate.py supertrend --csv sample_data/fake_daily_bars.csv --tv-trades sample_data/fake_tv_trades.csv
python -X utf8 scripts/strategy_backtest.py --csv sample_data/fake_daily_bars.csv --strategy supertrend
python -X utf8 scripts/strategy_backtest.py --code <종목코드> --tf 1d --days 365 --strategy supertrend   # 설정 필요, 조회만
python -X utf8 scripts/strategy_live.py --codes <종목코드> --strategy supertrend --once                 # 설정 필요, dry-run
```

## 들어 있지 않은 것
- 한투 앱키·계좌(사용자가 KIS Developers 에서 받아 `~/KIS/config/kis_devlp.yaml` 에, 형식은 `config.example.yaml`).
- 실제 시세 데이터(한투에서 받거나 같은 열의 CSV 로). `sample_data/` 는 가짜 값이다.
- 트레이딩뷰 내장 전략 Pine 원문(이용 조건 미확인으로 싣지 않음 — 트레이딩뷰 Pine 편집기에서 연다).
- 체결통보·일 손실 한도·비상 정지·실전 주문 경로.
