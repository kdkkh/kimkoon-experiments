# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""이식 전략 실시간 실행 — 기본은 dry-run(주문 계획만), 모의 주문은 --paper-order 를 줄 때만. 실전 주문 경로는 없다.

장중에 한투 시세 조회가 되어야 돈다(설정 파일 필요). 네트워크 없이 시험하려면 tests/test_live.py 를 보라.
실행(이 실험 폴더 맨 위에서):
  python -X utf8 scripts/strategy_live.py --codes <종목코드> --strategy supertrend --once            # 지금 닫힌 봉 한 번만 보고 끝(dry-run)
  python -X utf8 scripts/strategy_live.py --codes <종목코드>,<종목코드2> --tf 1 --until 15:20      # 장중 1분봉마다(dry-run)
  python -X utf8 scripts/strategy_live.py --codes <종목코드> --paper-order --amount 500000 --max-orders 3   # 모의 주문
옵션:
  --param 이름=값(여러 번) · --tf 봉 분(기본 1) · --lookback 처음 받을 1분봉 수(기본 120) · --settle 봉 마감 뒤 기다릴 초(기본 3)
  --amount 1회 금액(원, 기본 1,000,000 — kis.order.MAX_ORDER_WON 을 넘지 않음) · --max-orders 하루 진입(매수) 상한(기본 5, 청산은 상한 밖)
  --data-mode 봉·현재가 조회 키(real 기본 = 실전 키 조회만)
기록: logs/strategy_live_YYYYMMDD.jsonl (신호·계획·주문·오류, 단계별 ms 시각)
신호는 전략 규칙의 기계적 결과일 뿐 매매 권유가 아니다.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kis import config  # noqa: E402,F401  (stdout UTF-8 고정)
from strategy import data  # noqa: E402
from strategy.base import parse_params  # noqa: E402
from strategy.live import LiveRunner  # noqa: E402
from strategy.ported import load_strategy  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="이식 전략 실시간 실행(기본 dry-run, 모의 전용)")
    ap.add_argument("--codes", required=True, help="종목코드, 쉼표로 여러 개")
    ap.add_argument("--strategy", default="supertrend")
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--tf", type=int, default=1, help="봉 분")
    ap.add_argument("--amount", type=float, default=1_000_000)
    ap.add_argument("--max-orders", type=int, default=5, help="하루 진입(매수) 상한 — 청산은 세지 않음")
    ap.add_argument("--lookback", type=int, default=120)
    ap.add_argument("--settle", type=float, default=3.0)
    ap.add_argument("--start", default="09:00")
    ap.add_argument("--until", default="15:20")
    ap.add_argument("--once", action="store_true", help="지금 닫힌 봉 한 번만 처리하고 끝")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True, help="주문 계획만(기본)")
    g.add_argument("--paper-order", action="store_true", help="모의 주문을 실제로 보냄(모의 계좌)")
    ap.add_argument("--data-mode", choices=["real", "paper"], default="real")
    a = ap.parse_args()

    codes = [c.strip() for c in a.codes.split(",") if c.strip()]
    strat = load_strategy(a.strategy, **parse_params(a.param))
    mode = "모의 주문(--paper-order)" if a.paper_order else "dry-run(주문 계획만, 실제 주문 없음)"
    print(f"[실시간] {datetime.now():%Y-%m-%d %H:%M:%S}  {mode}  종목 {','.join(codes)}  전략 {strat}  봉 {a.tf}분")
    runner = LiveRunner(codes, strat, tf_minutes=a.tf, amount=a.amount, max_orders=a.max_orders, lookback=a.lookback,
                        paper_order=a.paper_order, data_mode=a.data_mode, settle_sec=a.settle)
    print(f"  1회 금액 {runner.amount:,.0f}원 · 하루 진입 상한 {a.max_orders}회(오늘 {runner.entries_today()}회 사용, 청산은 상한 밖) · "
          f"이 실행기가 연 포지션 {runner.positions or '없음'}")
    print(f"  기록: logs/{runner.log.path.name}")
    runner.run(start=a.start, until=a.until, once=a.once)
    print(f"  API 호출 {data.PACER.calls}회 · 신호는 전략 규칙의 기계적 결과이며 매매 권유가 아닙니다.")


if __name__ == "__main__":
    main()
