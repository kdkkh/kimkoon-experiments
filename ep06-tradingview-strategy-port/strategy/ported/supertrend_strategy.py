# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""Supertrend strategy — 트레이딩뷰 Pine 전략 이식 (정답 예시)

[Pine 원본]
- 출처: 트레이딩뷰 내장 전략 "Supertrend strategy"(차트 위 짧은 이름 "Supertrend str")
- 원본 버전: 내장 스크립트 9.0 (트레이딩뷰 갱신 2026-09-29, Pine Script v6). 옮긴 날 2026-11-03 기준 —
  트레이딩뷰가 내장 스크립트를 고치면 달라질 수 있으니 대조 전에 편집기에서 버전을 확인할 것
- 원문: 이 공개판에는 싣지 않았다(원문의 이용 조건을 확인하지 못함).
  트레이딩뷰 Pine 편집기에서 내장 전략 "Supertrend strategy" 를 직접 열어 보면 된다.
- 원본이 하는 일(우리말 설명):
  1. 입력 두 개: ATR 길이(입력 이름 "ATR Length", 기본 10) · 배수(입력 이름 "Factor", 기본 3.0)
  2. ta.supertrend(배수, ATR 길이) 로 추세 방향(direction: -1 상승, 1 하락)을 구한다.
  3. 방향 값이 줄어든 봉(하락 → 상승 전환, ta.change(direction) < 0)에 롱 진입.
  4. 방향 값이 늘어난 봉(상승 → 하락 전환, ta.change(direction) > 0)에 숏 진입(= 들고 있던 롱을 뒤집음).
  5. 그림(plot) 줄은 원본에서도 주석 처리돼 있어 매매에 영향이 없다.
- 원본의 전략 속성 기본값: 초기 자본 100000, 주문 수량 자기자본의 15%, 피라미딩 1,
  수수료 0, 슬리피지 0, process_orders_on_close=false(다음 봉 시가 체결)

[이식]
- 이식 날짜: 2026-11-03
- 이식한 AI: Claude (Opus 5.5)
- 바꾼 점:
  1. 공매도 없음: 원본은 하락 전환 때 short 진입(= long 을 뒤집어 short)한다. 이 틀은 공매도를 하지 않으므로
     같은 시점을 long 청산(long_exit)으로만 쓰고 short_entry/short_exit 는 항상 False.
     → 이식본은 "상승 전환 때 매수 → 하락 전환 때 전량 청산(현금 보유)"만 한다. 하락 구간의 숏 손익은 없다.
  2. 수량: 원본은 자기자본의 15%. 우리는 러너(backtest/live)가 금액 기준(기본 100만 원)·정수 주로 정한다 — 전략은 신호만.
  3. 체결 시점: 원본과 같다(신호는 봉 마감, 체결은 다음 봉 시가) — 러너가 처리.
"""
from __future__ import annotations

import pandas as pd

from strategy import indicators as ta
from strategy.base import Strategy, empty_signals


class SupertrendStrategy(Strategy):
    name = "supertrend"
    params = {
        "atrPeriod": 10,     # Pine 입력 "ATR Length", 기본 10 (변수 이름은 원본과 같게)
        "factor": 3.0,       # Pine 입력 "Factor", 기본 3.0
    }

    def signals(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        sig = empty_signals(df)

        # Pine: ta.supertrend(factor, atrPeriod) 의 방향 값
        supertrend, direction = ta.supertrend(df["high"], df["low"], df["close"], p["factor"], p["atrPeriod"])

        # Pine: ta.change(direction) < 0 일 때 롱 진입
        sig["long_entry"] = (ta.change(direction) < 0).astype(bool)
        # Pine: ta.change(direction) > 0 일 때 숏 진입 → 공매도 없음 → 같은 시점에 long 청산만 (바꾼 점 1)
        sig["long_exit"] = (ta.change(direction) > 0).astype(bool)

        # 대조용 지표 열(러너는 보지 않음) — 트레이딩뷰 데이터 창의 Supertrend 값과 비교
        sig["supertrend"] = supertrend
        sig["direction"] = direction
        return sig


STRATEGY = SupertrendStrategy

# ── 자기 점검 표 ────────────────────────────────────────────────────────────
# [사용한 Pine 함수 → 대응 함수]
#   input(정수, "ATR Length")                  → params["atrPeriod"] = 10
#   input.float(실수, "Factor")                → params["factor"] = 3.0
#   ta.supertrend(factor, atrPeriod) 의 방향   → supertrend, direction = ta.supertrend(df["high"], df["low"], df["close"], f, n)
#   ta.change(direction)                       → ta.change(direction)
#   strategy.entry(롱)                         → sig["long_entry"]
#   strategy.entry(숏)                         → sig["long_exit"] (공매도 없음 — 바꾼 점 1)
#   strategy(...) 의 수량 속성                 → 러너 인자 --amount (바꾼 점 2)
# [미지원 항목]
#   없음 (그림 줄은 원본에서도 주석이라 옮기지 않음)
# [의도적으로 바꾼 점]
#   1. short 진입 → long 청산만   2. 수량 15% → 금액 기준 정수 주
