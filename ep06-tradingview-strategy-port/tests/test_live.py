# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""live.py 시험 — 네트워크 없이(조회 함수를 가짜로 바꿔) dry-run 은 주문 함수를 부르지 않는지, 가드가 도는지.
종목코드 자리에는 가짜 문자열(TEST01·TEST02)을 쓴다. 현재가 61234 도 가짜 값이다."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strategy import live  # noqa: E402
from strategy.ported import load_strategy  # noqa: E402

A, B = "TEST01", "TEST02"     # 가짜 종목코드


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "LOG_DIR", tmp_path)
    monkeypatch.setattr(live.order, "limit_order", lambda *a, **k: (_ for _ in ()).throw(AssertionError("주문 호출됨")))
    monkeypatch.setattr(live.data.PACER, "call", lambda fn, *a, **k: {"stck_prpr": "61234"})
    monkeypatch.setattr(live.data, "cfg_of", lambda mode: None)
    return live.LiveRunner([A], load_strategy("supertrend"), max_orders=1, printer=lambda *a: None)


def test_round_tick():
    assert live.round_tick(61234, "buy") == 61300      # 50,000~200,000 원은 100원 단위 → 위로
    assert live.round_tick(61234, "sell") == 61200     # 아래로
    assert live.round_tick(1999, "buy") == 1999


def test_dry_run_plans_without_ordering(runner):
    p = runner._act(A, "long_entry", live.now_ms())
    assert p["side"] == "buy" and p["price"] == 61300 and p["qty"] == 1_000_000 // 61300
    assert runner._act(A, "long_entry", live.now_ms()) is None          # 종목당 1포지션
    s = runner._act(A, "long_exit", live.now_ms())
    assert s["side"] == "sell" and s["qty"] == p["qty"]
    assert runner._act(A, "long_entry", live.now_ms()) is None          # 하루 진입 상한 1회(청산은 안 셈)
    kinds = [e["event"] for e in runner.log.today_events()]
    assert kinds.count("order_plan") == 2 and "order_sent" not in kinds
    assert runner.entries_today() == 1


def test_exit_allowed_after_entry_cap(runner):
    # 매수·매도를 같이 세면 상한에 닿은 뒤 청산 신호가 막혀 포지션이 남는다 → 청산은 상한 밖이어야 한다
    assert runner._act(A, "long_entry", live.now_ms())["side"] == "buy"
    assert runner._act(B, "long_entry", live.now_ms()) is None        # 진입 상한
    s = runner._act(A, "long_exit", live.now_ms())
    assert s is not None and s["side"] == "sell"                      # 상한에 닿아도 청산은 나간다


def test_exit_without_position_skipped(runner):
    assert runner._act(A, "long_exit", live.now_ms()) is None
    assert runner.log.today_events()[-1]["event"] == "order_skip"


def test_amount_capped_by_order_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "LOG_DIR", tmp_path)
    r = live.LiveRunner([A], load_strategy("supertrend"), amount=5_000_000, printer=lambda *a: None)
    assert r.amount == live.order.MAX_ORDER_WON


def test_closed_bars_drop_unfinished(runner):
    # 거래량 0 인 분과 아직 진행 중인 분은 빠져야 한다
    t = pd.date_range("2026-11-03 10:00", periods=4, freq="min", tz="Asia/Seoul")
    runner.bars[A] = pd.DataFrame({"time": t, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                                   "volume": [5.0, 0.0, 5.0, 5.0]})
    out = runner.closed_bars(A, now=pd.Timestamp("2026-11-03 10:03:30").to_pydatetime())
    assert list(out["time"].dt.strftime("%H:%M")) == ["10:00", "10:02"]       # 10:01 거래 없음, 10:03 진행 중


def test_order_refuses_non_paper():
    # 실전 주문 경로가 없음을 확인 — 모의가 아닌 설정이면 check 가 거절한다(네트워크 호출 전)
    from kis.config import KisConfig
    cfg = KisConfig(mode="real", app_key="x", app_secret="x", account="x", product="01", rest_url="", user_agent="")
    with pytest.raises(PermissionError):
        live.order.check(cfg, "buy", A, 1, 61300)


def _paper_cfg(url="https://openapivts.koreainvestment.com:29443"):
    from kis.config import KisConfig
    return KisConfig(mode="paper", app_key="x", app_secret="x", account="x", product="01", rest_url=url, user_agent="")


def test_order_limit_applies_to_buy_only(tmp_path, monkeypatch):
    # 1회 한도는 매수에만 — 산 뒤 값이 올라 금액이 한도를 넘어도 청산(매도)은 거절되지 않아야 한다.
    monkeypatch.setattr(live.order, "LOG", tmp_path / "orders.jsonl")
    with pytest.raises(ValueError):
        live.order.check(_paper_cfg(), "buy", A, 16, 63000)       # 1,008,000원 매수 → 거절
    live.order.check(_paper_cfg(), "sell", A, 16, 63000)          # 같은 금액 매도 → 통과


def test_order_refuses_non_paper_host(tmp_path, monkeypatch):
    # 모드가 paper 여도 보내는 주소가 모의투자 서버가 아니면 거절한다.
    monkeypatch.setattr(live.order, "LOG", tmp_path / "orders.jsonl")
    with pytest.raises(PermissionError):
        live.order.check(_paper_cfg("https://openapi.koreainvestment.com:9443"), "buy", A, 1, 61300)
