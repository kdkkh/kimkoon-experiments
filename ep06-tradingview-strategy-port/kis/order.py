# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""주문 — 모의투자 지정가 주문만. 안전장치(check)를 먼저 통과해야 나간다.

- 이 공개판에는 실전 주문 경로가 없다: 설정이 모의(paper)가 아니면 check 가 거절한다. tr_id 도 모의용(V…)만 쓴다.
- 1회 최대 금액 MAX_ORDER_WON, 같은 주문 DUP_WINDOW_SEC 초 안 재요청 차단, 호가 단위 검사.
- 주문 기록은 이 폴더의 logs/orders.jsonl (계좌번호·키는 적지 않는다).
- 아직 없는 것: 일 손실 한도, 비상 정지.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from .client import post
from .config import KisConfig

MAX_ORDER_WON = 1_000_000
DUP_WINDOW_SEC = 60
LOG = Path(__file__).resolve().parents[1] / "logs" / "orders.jsonl"
TRADING = "/uapi/domestic-stock/v1/trading"      # 국내주식 주문 경로 앞부분
PAPER_HOST = "openapivts.koreainvestment.com"    # 모의투자 REST 도메인(공식 예제 kis_devlp.yaml 의 vps, 2026-11-19 확인)
PAPER_TR = {"buy": "VTTC0012U", "sell": "VTTC0011U"}   # 모의 현금 매수·매도 (실전은 T 로 시작 — 여기서는 쓰지 않음)


def tick_size(price: int) -> int:
    """KRX 주식 호가 단위 (2023-01-25 개편 기준)"""
    for limit, tick in ((2_000, 1), (5_000, 5), (20_000, 10), (50_000, 50), (200_000, 100), (500_000, 500)):
        if price < limit:
            return tick
    return 1_000


def check(cfg: KisConfig, side: str, code: str, qty: int, price: int) -> None:
    """안전장치. 통과 못 하면 예외."""
    if not cfg.is_paper:
        raise PermissionError("이 프로그램은 모의투자 주문만 냅니다 — 실전 주문 경로는 없습니다")
    if PAPER_HOST not in cfg.rest_url:
        # 모드 이름만 보면 설정 파일의 vps 칸에 실전 주소를 잘못 적은 경우를 못 막는다 → 보내는 주소도 본다.
        raise PermissionError(f"모의투자 서버 주소({PAPER_HOST})가 아닙니다 — 설정 파일의 vps 값을 확인하세요")
    if side not in ("buy", "sell"):
        raise ValueError("side 는 buy / sell")
    if qty <= 0 or price <= 0:
        raise ValueError("수량·가격은 0보다 커야 합니다")
    if price % tick_size(price):
        raise ValueError(f"{price:,}원은 호가 단위({tick_size(price):,}원)에 맞지 않습니다")
    # 1회 한도는 매수에만 건다. 매도(청산)에도 걸면, 산 뒤 값이 올라 금액이 한도를 넘는 순간 청산이 거절돼 포지션이 남는다.
    if side == "buy" and qty * price > MAX_ORDER_WON:
        raise ValueError(f"주문 금액 {qty * price:,}원이 1회 한도 {MAX_ORDER_WON:,}원을 넘습니다")
    if LOG.exists():
        now = time.time()
        for line in LOG.read_text(encoding="utf-8").splitlines()[-50:]:
            o = json.loads(line)
            if (o["mode"], o["side"], o["code"], o["qty"], o["price"]) == (cfg.mode, side, code, qty, price) \
                    and now - o["ts"] < DUP_WINDOW_SEC:
                raise RuntimeError(f"같은 주문을 {DUP_WINDOW_SEC}초 안에 다시 넣으려 합니다 (중복 방지)")


def limit_order(cfg: KisConfig, side: str, code: str, qty: int, price: int) -> dict:
    """모의 지정가 현금 주문 (매수 VTTC0012U, 매도 VTTC0011U). 반환: 주문번호·주문시각."""
    check(cfg, side, code, qty, price)
    # 보내기 전에 먼저 적는다. 서버는 받았는데 응답이 늦어 예외가 나도, 같은 주문을 60초 안에 다시 보내지 않게.
    _append({"ts": time.time(), "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "mode": cfg.mode, "side": side,
             "code": code, "qty": qty, "price": price, "odno": None, "msg": "보냄(응답 전)"})
    d = post(cfg, f"{TRADING}/order-cash", PAPER_TR[side], {
        "CANO": cfg.account,
        "ACNT_PRDT_CD": cfg.product,
        "PDNO": code,
        "ORD_DVSN": "00",            # 지정가
        "ORD_QTY": str(qty),
        "ORD_UNPR": str(price),
        "EXCG_ID_DVSN_CD": "KRX",
        "SLL_TYPE": "",
        "CNDT_PRIC": "",
    })
    out = d["output"]
    rec = {"ts": time.time(), "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "mode": cfg.mode, "side": side,
           "code": code, "qty": qty, "price": price, "odno": out.get("ODNO"), "ord_tmd": out.get("ORD_TMD"),
           "msg": d.get("msg1", "").strip()}
    _append(rec)
    return rec


def _append(rec: dict) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
