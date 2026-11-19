# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""접근 토큰 — 캐시 재사용이 원칙.

막히는 자리: 한국투자 안내는 "접근 토큰은 1일 1회 발급 원칙, 유효기간(24시간) 안에 잦은 발급 시 이용 제한"이다.
  → 실행할 때마다 새로 받으면 제한에 걸릴 수 있어서, 받은 토큰을 파일에 두고 만료 전까지 다시 쓴다.
- 캐시(설정 폴더의 tk_v.json(모의)·tk_p.json(실전), 형식 {"tok", "exp"})가 있고 만료 전이면 그대로 쓴다.
- 만료 시각이 지났을 때만 새로 발급한다.
- 캐시 파일이 깨져 있으면 덮어쓰지 않고 멈춘다(함부로 새로 받으면 '잦은 발급'이 될 수 있어 사람이 확인).
- 같은 실행 안에서도 만료 시각이 지나면 캐시 파일을 다시 읽고(다른 프로그램이 먼저 새로 받았을 수 있음),
  그래도 만료면 새로 발급한다 — 종일 켜 두는 프로그램이 만료된 토큰을 계속 들고 있지 않게.
- 토큰 값은 화면·로그에 출력하지 않는다.
"""
from __future__ import annotations

import json
from datetime import datetime

import requests

from .config import KisConfig

_FMT = "%Y-%m-%d %H:%M:%S"
_memory: dict[str, tuple[str, datetime]] = {}   # mode → (토큰, 만료시각). 만료 전까지는 파일도 다시 읽지 않는다


def _read_cache(cfg: KisConfig) -> tuple[str, datetime] | None:
    f = cfg.token_file
    if not f.exists():
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        return d["tok"], datetime.strptime(d["exp"], _FMT)
    except Exception:
        raise RuntimeError(f"토큰 캐시를 읽을 수 없습니다: {f.name} (자동 재발급하지 않음 — 파일을 확인하세요)")


def _issue(cfg: KisConfig) -> tuple[str, datetime]:
    """새 토큰 발급(POST /oauth2/tokenP) — 캐시가 없거나 만료됐을 때만 호출된다."""
    r = requests.post(
        f"{cfg.rest_url}/oauth2/tokenP",
        json={"grant_type": "client_credentials", "appkey": cfg.app_key, "appsecret": cfg.app_secret},
        headers={"content-type": "application/json", "User-Agent": cfg.user_agent},
        timeout=10,
    )
    d = r.json()
    if r.status_code != 200 or "access_token" not in d:
        # 응답에 비밀값은 없지만, 안내 문구만 보여 준다
        raise RuntimeError(f"토큰 발급 실패: HTTP {r.status_code} {d.get('error_code', '')} {d.get('error_description', '')}")
    tok, exp = d["access_token"], datetime.strptime(d["access_token_token_expired"], _FMT)
    cfg.token_file.write_text(json.dumps({"tok": tok, "exp": exp.strftime(_FMT)}), encoding="utf-8")
    return tok, exp


def get_token(cfg: KisConfig, verbose: bool = True) -> str:
    now = datetime.now()
    held = _memory.get(cfg.mode)
    if held and now < held[1]:
        return held[0]
    label = "모의" if cfg.is_paper else "실전"
    cached = _read_cache(cfg)
    if cached and now < cached[1]:
        tok, exp = cached
        if verbose:
            print(f"[토큰] {label}: 캐시 재사용 (만료 {exp:%m-%d %H:%M}, 남은 {_left(exp)})")
    else:
        why = "캐시 없음" if not cached else f"만료됨({cached[1]:%m-%d %H:%M})"
        if verbose:
            print(f"[토큰] {label}: {why} → 새로 발급")
        tok, exp = _issue(cfg)
        if verbose:
            print(f"[토큰] {label}: 발급 완료 (만료 {exp:%m-%d %H:%M}) — 한국투자에서 발급 안내가 올 수 있습니다")
    _memory[cfg.mode] = (tok, exp)
    return tok


def _left(exp: datetime) -> str:
    s = int((exp - datetime.now()).total_seconds())
    return f"{s // 3600}시간 {s % 3600 // 60}분"
