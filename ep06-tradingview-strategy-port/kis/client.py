# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""REST 호출 공통 — 헤더 구성, 응답 오류 확인. 비밀값은 오류 메시지에 넣지 않는다(msg_cd·msg1 만)."""
from __future__ import annotations

import requests

from .auth import get_token
from .config import KisConfig


class KisError(RuntimeError):
    pass


def _headers(cfg: KisConfig, tr_id: str) -> dict:
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {get_token(cfg)}",
        "appkey": cfg.app_key,
        "appsecret": cfg.app_secret,
        "tr_id": tr_id,
        "custtype": "P",          # 개인
        "User-Agent": cfg.user_agent,
    }


def _check(r: requests.Response, tr_id: str) -> dict:
    try:
        d = r.json()
    except ValueError:
        raise KisError(f"[{tr_id}] HTTP {r.status_code} (JSON 아님)") from None
    if r.status_code != 200 or d.get("rt_cd") != "0":
        raise KisError(f"[{tr_id}] HTTP {r.status_code} {d.get('msg_cd', '')} {d.get('msg1', '')}".strip())
    return d


def get(cfg: KisConfig, path: str, tr_id: str, params: dict) -> dict:
    r = requests.get(f"{cfg.rest_url}{path}", headers=_headers(cfg, tr_id), params=params, timeout=10)
    return _check(r, tr_id)


def post(cfg: KisConfig, path: str, tr_id: str, body: dict) -> dict:
    r = requests.post(f"{cfg.rest_url}{path}", headers=_headers(cfg, tr_id), json=body, timeout=10)
    return _check(r, tr_id)
