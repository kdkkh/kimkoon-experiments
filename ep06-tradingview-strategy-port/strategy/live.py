# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""실시간 실행기(뼈대) — 모의 전용. 기본은 dry-run(주문 계획만 출력, 주문 함수를 아예 부르지 않음).

실전 주문 경로는 없다: 주문은 kis.order.limit_order 를 **모의 설정(config.load("paper"))으로만** 부르고,
  kis.order.check 가 모의 설정이 아니거나 보내는 주소가 모의투자 서버가 아니면 거절한다.

흐름(종목 1~N개, 봉 tf 분):
  봉이 닫히면(+ settle 초) → 당일 1분봉 받기(처음엔 lookback 개, 그다음엔 최신 30개만 이어 붙임) → 진행 중인 봉 빼기
  → tf 분봉으로 묶기 → 전략 signals → '방금 닫힌 봉'의 신호만 본다
  → long_entry 이고 이 실행기가 연 포지션이 없으면: 현재가 기준 지정가 매수(수량 = 금액 // 가격, 정수 주)
  → long_exit 이고 이 실행기가 연 포지션이 있으면: 그 수량 매도
주문:
  - paper_order=False(기본) 이면 주문 함수를 부르지 않고 계획만 기록한다.
  - 지정가: 매수는 현재가를 호가 단위 위로, 매도는 아래로 맞춘다.
    막혔던 자리: 한투 현재가가 호가 단위 사이 값으로 올 때가 있었다(원본 작업 실측) → 그대로 주문하면 호가 단위 오류.
가드:
  - 하루 진입 상한(기본 5) — 새 매수만 센다. 청산(매도)은 상한 밖이라 들고 있는 포지션은 언제든 닫힌다.
    왜: 매수·매도를 같이 세면 상한에 닿은 뒤 청산 신호가 막혀 포지션이 남는다(원본 작업에서 실제로 겪음).
    오늘 기록 파일의 매수 주문을 세므로 재시작해도 이어진다.
  - 종목당 포지션 1개 · 1회 금액 상한(min(amount, kis.order.MAX_ORDER_WON)) · kis.order.check 의 중복 주문·호가 단위·실전 차단.
  - 이 실행기가 열지 않은 기존 보유분은 건드리지 않는다(포지션은 이 실행기 기록 기준, 계좌 잔고와 맞추는 단계는 없음).
기록: 이 폴더의 logs/strategy_live_YYYYMMDD.jsonl — 모든 단계에 ms 시각(봉 마감·조회 시작/끝·신호·주문 보냄/응답).
  '신호 → 주문 몇 ms' 는 이 파일로 잰다. 계좌·키·토큰은 적지 않는다.
한계: REST 로 1분봉을 봉 마감 settle 초 뒤 받는다(웹소켓으로 봉을 만들지 않음) → 신호가 수 초 늦다.
  체결통보(웹소켓)는 원본에서 아직 동작을 확인하지 못해 이 공개판에서 뺐다.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from kis import config, order, quote
from strategy import data
from strategy.base import Strategy

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"


def now_ms() -> int:
    return int(time.time() * 1000)


def round_tick(price: float, side: str) -> int:
    """호가 단위에 맞춘 지정가: 매수는 위로, 매도는 아래로."""
    p = int(price)
    t = order.tick_size(p)
    if side == "buy":
        p = -(-p // t) * t
        t2 = order.tick_size(p)          # 올리다 단위 경계를 넘었으면 다시
        return -(-p // t2) * t2
    return (p // t) * t


class JsonlLog:
    def __init__(self, day: str | None = None):
        LOG_DIR.mkdir(exist_ok=True)
        self.path = LOG_DIR / f"strategy_live_{day or datetime.now().strftime('%Y%m%d')}.jsonl"
        self.lock = threading.Lock()

    def write(self, event: str, **kw) -> dict:
        rec = {"ts_ms": now_ms(), "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], "event": event, **kw}
        with self.lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec

    def today_events(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out


class LiveRunner:
    def __init__(self, codes: list[str], strategy: Strategy, tf_minutes: int = 1, amount: float = 1_000_000,
                 max_orders: int = 5, lookback: int = 120, paper_order: bool = False, data_mode: str = "real",
                 settle_sec: float = 3.0, printer=print):
        self.codes = codes
        self.strategy = strategy
        self.tf = tf_minutes
        self.amount = min(float(amount), float(order.MAX_ORDER_WON))
        self.max_orders = max_orders
        self.lookback = lookback
        self.paper_order = paper_order
        self.data_mode = data_mode
        self.settle = settle_sec
        self.say = printer
        self.log = JsonlLog()
        self.bars: dict[str, pd.DataFrame] = {}
        self.last_bar: dict[str, pd.Timestamp] = {}
        self.order_cfg = None
        if paper_order:
            cfg = config.load("paper")
            if not cfg.is_paper:                       # 모의 설정이 아니면 멈춘다(주소 검사는 kis.order.check)
                raise PermissionError("모의 설정이 아닙니다 — 주문하지 않습니다")
            self.order_cfg = cfg
        self.positions = self._restore_positions()

    # ---------- 상태 ----------
    def _restore_positions(self) -> dict[str, dict]:
        """오늘 기록에서 이 실행기가 연(체결 여부와 상관없이 주문을 보낸) 포지션을 되살린다. dry-run 은 계획 기준."""
        pos: dict[str, dict] = {}
        kind = "order_sent" if self.paper_order else "order_plan"
        for e in self.log.today_events():
            if e.get("event") != kind or e.get("code") not in self.codes:
                continue
            if e.get("side") == "buy":
                pos[e["code"]] = {"qty": e["qty"], "price": e["price"], "since": e["at"]}
            elif e.get("side") == "sell":
                pos.pop(e["code"], None)
        return pos

    def entries_today(self) -> int:
        """오늘 보낸(또는 계획한) 새 진입(매수) 수 — 하루 상한은 이것만 센다."""
        kind = "order_sent" if self.paper_order else "order_plan"
        return sum(1 for e in self.log.today_events() if e.get("event") == kind and e.get("side") == "buy")

    # ---------- 봉 ----------
    def _update_bars(self, code: str) -> tuple[pd.DataFrame, int, int]:
        t0 = now_ms()
        first = code not in self.bars
        new = data.fetch_minute_today(code, bars=self.lookback if first else 30, mode=self.data_mode)
        t1 = now_ms()
        if first:
            hist = data.read_cache(code, "1m")            # 앞 날짜 1분봉 캐시가 있으면 앞에 붙임(지표 예열용, 호출 없음)
            today = datetime.now().strftime("%Y%m%d")
            hist = hist[hist["time"].dt.strftime("%Y%m%d") < today]
            parts = [x for x in (hist, new) if not x.empty]
            base = pd.concat(parts) if parts else data.empty_bars()
        else:
            base = pd.concat([self.bars[code], new])
        base = base.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)
        self.bars[code] = base
        return base, t0, t1

    def closed_bars(self, code: str, now: datetime | None = None) -> pd.DataFrame:
        one = data.drop_unfinished_minute(self.bars.get(code, data.empty_bars()), now, 1)
        # 거래 없는 분은 뺀다 — 한투 당일 분봉은 장 마감 뒤에도 거래량 0 봉을 채워 준다.
        # 트레이딩뷰는 체결 없는 분에 봉을 그리지 않는 것으로 보고 맞췄다(추정).
        one = one[one["volume"] > 0]
        tf = data.resample_minutes(one, self.tf)
        return data.drop_unfinished_minute(tf, now, self.tf)

    # ---------- 한 번 돌기 ----------
    def step(self, bar_close_ms: int | None = None) -> list[dict]:
        """모든 종목에 대해 방금 닫힌 봉을 처리. 돌려주는 값 = 이번에 만든 계획/주문 목록."""
        actions = []
        for code in self.codes:
            try:
                _, t0, t1 = self._update_bars(code)
                bars = self.closed_bars(code)
                if len(bars) < 2:
                    self.log.write("bar", code=code, note="봉 부족", n_bars=len(bars), t_fetch_start_ms=t0, t_fetch_end_ms=t1)
                    self.say(f"  {code}: 닫힌 봉 {len(bars)}개 — 부족")
                    continue
                last_t = bars["time"].iloc[-1]
                if self.last_bar.get(code) == last_t:
                    continue                                  # 이미 처리한 봉
                self.last_bar[code] = last_t
                sig = self.strategy.run(bars)
                row = sig.iloc[-1]
                t_sig = now_ms()
                close_ms = bar_close_ms or int((last_t + pd.Timedelta(minutes=self.tf)).timestamp() * 1000)
                self.log.write("bar", code=code, bar_time=last_t.isoformat(), close=float(bars["close"].iloc[-1]),
                               n_bars=len(bars), t_bar_close_ms=close_ms, t_fetch_start_ms=t0, t_fetch_end_ms=t1)
                kind = "long_entry" if row["long_entry"] else "long_exit" if row["long_exit"] else None
                extra = {k: (float(row[k]) if pd.notna(row[k]) else None) for k in sig.columns
                         if k not in ("long_entry", "long_exit", "short_entry", "short_exit")}
                if kind is None:
                    self.say(f"  {code} {last_t:%H:%M} 봉: 신호 없음 (종가 {bars['close'].iloc[-1]:,.0f}, {extra})")
                    continue
                self.log.write("signal", code=code, bar_time=last_t.isoformat(), kind=kind, t_signal_ms=t_sig,
                               ms_after_bar_close=t_sig - close_ms, indicators=extra)
                self.say(f"  {code} {last_t:%H:%M} 봉: 신호 {kind} ({extra})")
                act = self._act(code, kind, t_sig)
                if act:
                    actions.append(act)
            except Exception as e:                            # 한 종목 오류가 다른 종목을 멈추지 않게
                self.log.write("error", code=code, where="step", error=f"{type(e).__name__}: {str(e)[:200]}")
                self.say(f"  {code}: 오류 {type(e).__name__}: {str(e)[:120]}")
        return actions

    def _act(self, code: str, kind: str, t_sig: int) -> dict | None:
        held = self.positions.get(code)
        if kind == "long_entry" and held:
            return self._skip(code, "이미 포지션 있음(종목당 1개)")
        if kind == "long_exit" and not held:
            return self._skip(code, "이 실행기가 연 포지션 없음 — 청산할 것 없음")
        if kind == "long_entry" and self.entries_today() >= self.max_orders:
            return self._skip(code, f"오늘 진입 상한 {self.max_orders}회에 닿음(청산은 상한 밖)")
        side = "buy" if kind == "long_entry" else "sell"
        t_q0 = now_ms()
        px_now = int(float(data.PACER.call(quote.current_price, data.cfg_of(self.data_mode), code)["stck_prpr"]))
        t_q1 = now_ms()
        price = round_tick(px_now, side)
        qty = int(self.amount // price) if side == "buy" else int(held["qty"])
        if qty <= 0:
            return self._skip(code, f"금액 {self.amount:,.0f}원으로 1주도 못 삼(가격 {price:,})")
        if qty * price > self.amount and side == "buy":
            return self._skip(code, "금액 상한 초과")
        plan = {"code": code, "side": side, "qty": qty, "price": price, "current": px_now, "amount": qty * price,
                "t_signal_ms": t_sig, "t_quote_start_ms": t_q0, "t_quote_end_ms": t_q1}
        if not self.paper_order:
            self.log.write("order_plan", **plan, dry_run=True)
            self.say(f"  [계획만 · dry-run] {code} {'매수' if side == 'buy' else '매도'} {qty}주 × {price:,}원 "
                     f"= {qty * price:,}원 (현재가 {px_now:,}) — 실제 주문 안 함")
            self._apply(code, side, qty, price)
            return plan
        t_send = now_ms()
        try:
            rec = order.limit_order(self.order_cfg, side, code, qty, price)     # 모의 설정으로만
        except Exception as e:
            self.log.write("error", code=code, where="order", error=f"{type(e).__name__}: {str(e)[:200]}", **plan)
            self.say(f"  [모의 주문 실패] {code}: {type(e).__name__}: {str(e)[:120]}")
            return None
        t_resp = now_ms()
        self.log.write("order_sent", **plan, odno=rec.get("odno"), ord_tmd=rec.get("ord_tmd"), msg=rec.get("msg"),
                       t_send_ms=t_send, t_resp_ms=t_resp, ms_signal_to_send=t_send - t_sig)
        self.say(f"  [모의 주문] {code} {'매수' if side == 'buy' else '매도'} {qty}주 × {price:,}원 → 주문번호 {rec.get('odno')} "
                 f"(신호→응답 {t_resp - t_sig} ms)")
        self._apply(code, side, qty, price)
        return {**plan, "odno": rec.get("odno")}

    def _apply(self, code: str, side: str, qty: int, price: int):
        if side == "buy":
            self.positions[code] = {"qty": qty, "price": price, "since": datetime.now().strftime("%H:%M:%S")}
        else:
            self.positions.pop(code, None)

    def _skip(self, code: str, why: str) -> None:
        self.log.write("order_skip", code=code, reason=why)
        self.say(f"  [건너뜀] {code}: {why}")
        return None

    # ---------- 반복 ----------
    def next_close(self, now: datetime | None = None) -> datetime:
        now = now or datetime.now()
        m = (now.hour * 60 + now.minute) // self.tf * self.tf + self.tf
        return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=m)

    def run(self, start: str = "09:00", until: str = "15:20", once: bool = False):
        self.log.write("start", codes=self.codes, strategy=type(self.strategy).__name__, params=self.strategy.params,
                       tf=self.tf, amount=self.amount, max_orders=self.max_orders,
                       mode="paper-order" if self.paper_order else "dry-run", positions=self.positions)
        if once:
            self.step()
            self.save_bars()
            self.log.write("stop", reason="once")
            return
        try:
            while True:
                now = datetime.now()
                if now.strftime("%H:%M") >= until:
                    self.say(f"  {until} 지남 — 끝")
                    break
                close = self.next_close(now)
                if close.strftime("%H:%M") <= start:
                    close = now.replace(hour=int(start[:2]), minute=int(start[3:]), second=0, microsecond=0) \
                        + timedelta(minutes=self.tf)
                wait = (close - now).total_seconds() + self.settle
                time.sleep(max(wait, 0))
                self.step(bar_close_ms=int(close.timestamp() * 1000))
        except KeyboardInterrupt:
            self.say("  Ctrl+C — 멈춤")
        finally:
            self.save_bars()
            self.log.write("stop", reason="end", positions=self.positions)

    def save_bars(self):
        """받은 1분봉을 data/bars/{code}_1m.csv 에 이어 저장(다음 날 지표 예열용). 진행 중인 봉은 빼고."""
        for code, df in self.bars.items():
            done = data.drop_unfinished_minute(df)
            if not done.empty:
                data.merge_save(code, "1m", done)
