# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""시세 조회 — 현재가, 과거 1분봉. (주문 코드 없음)"""
from __future__ import annotations

from .client import get
from .config import KisConfig

QUOTE = "/uapi/domestic-stock/v1/quotations"     # 국내주식 시세 경로 앞부분


def current_price(cfg: KisConfig, code: str) -> dict:
    """주식현재가 시세 (FHKST01010100, 경로 끝 inquire-price) — 실전·모의 같은 tr_id. output 의 stck_prpr 가 현재가."""
    d = get(cfg, f"{QUOTE}/inquire-price", "FHKST01010100",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code})
    return d["output"]


def minute_bars_past(cfg: KisConfig, code: str, date: str, hour: str = "153000") -> list[dict]:
    """주식일별분봉조회 (FHKST03010230) — date(YYYYMMDD) 의 hour(HHMMSS) 이전 1분봉 최대 120개, 거래소 J.
    한국투자 공식 TR 목록에는 '모의투자 미지원'으로 표시돼 있다. 원본 작업에서는 모의 키로도 응답이 왔지만(실측),
    문서와 다르므로 기본은 실전 키로 조회만 한다(strategy/data.py 의 mode="real")."""
    d = get(cfg, f"{QUOTE}/inquire-time-dailychartprice", "FHKST03010230", {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": code,
        "FID_INPUT_HOUR_1": hour,
        "FID_INPUT_DATE_1": date,
        "FID_PW_DATA_INCU_YN": "Y",      # 과거 데이터 포함
        "FID_FAKE_TICK_INCU_YN": "",
    })
    return [b for b in d.get("output2", []) if b.get("stck_cntg_hour")]
