# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""설정 읽기 — 설정 파일 하나(kis_devlp.yaml)에서만 읽는다.

위치: 기본은 홈 폴더의 KIS/config/kis_devlp.yaml (~/KIS/config/kis_devlp.yaml).
      한국투자 공식 예제 저장소(github.com/koreainvestment/open-trading-api)의 kis_auth.py 가 쓰는 위치·파일 이름과 같다.
      환경변수 KIS_CONFIG_DIR 를 주면 그 폴더의 kis_devlp.yaml 을 읽는다.
형식: 이 폴더 맨 위의 config.example.yaml (이 프로그램이 읽는 키만 적어 둠). 공식 예제의 kis_devlp.yaml 을 그대로 써도 된다.
왜 폴더 밖에 두나: 설정·토큰 캐시가 저장소 안에 있으면 실수로 함께 올라가기 쉽다.
비밀값(앱키·시크릿·계좌·토큰)은 화면·로그에 출력하지 않는다. 계좌는 mask_account() 로 끝 2자리만 보여 준다.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# 윈도우 콘솔에서 한글이 깨지지 않게 출력 인코딩을 UTF-8 로 고정
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

CONFIG_DIR = Path(os.environ["KIS_CONFIG_DIR"]) if os.environ.get("KIS_CONFIG_DIR") else Path.home() / "KIS" / "config"
CONFIG_FILE = CONFIG_DIR / "kis_devlp.yaml"

# 모드별로 쓰는 설정 키 (기본값은 모의 "paper"). 키 이름은 공식 예제 kis_devlp.yaml 과 같다.
#   real 은 이 공개판에서 '시세 조회'에만 쓴다(주문은 kis/order.py 가 모의 설정이 아니면 거절한다).
_KEYS = {
    "paper": dict(app="paper_app", sec="paper_sec", acct="my_paper_stock", rest="vps"),
    "real": dict(app="my_app", sec="my_sec", acct="my_acct_stock", rest="prod"),
}


def mask_account(acct: str) -> str:
    """계좌번호를 끝 2자리만 남기고 가린다. 예: ******12"""
    acct = str(acct or "")
    return "*" * max(len(acct) - 2, 0) + acct[-2:]


def _filled(v) -> bool:
    """값이 있고, 공식 예시 문구(한글 안내문)가 아니면 채워진 것으로 본다."""
    return v not in (None, "") and not re.search("[가-힣]", str(v))


@dataclass(frozen=True)
class KisConfig:
    mode: str                      # "paper"(모의) / "real"(실전 키 — 이 공개판에서는 조회만)
    app_key: str = field(repr=False)
    app_secret: str = field(repr=False)
    account: str = field(repr=False)   # 계좌 앞 8자리
    product: str                   # 계좌 뒤 2자리 (01 = 종합)
    rest_url: str
    user_agent: str

    @property
    def is_paper(self) -> bool:
        return self.mode == "paper"

    @property
    def product_name(self) -> str:
        """계좌 뒤 2자리를 숫자 대신 이름으로 (화면 표시용)"""
        return {"01": "종합", "03": "선물옵션", "22": "연금저축", "29": "퇴직연금"}.get(self.product, "기타")

    @property
    def token_file(self) -> Path:
        """토큰 캐시 위치 (저장소 폴더 밖, 설정 파일과 같은 폴더)"""
        return CONFIG_DIR / ("tk_v.json" if self.is_paper else "tk_p.json")

    def summary(self) -> str:
        """비밀값 없이 화면에 보여 줄 요약"""
        return (f"모드={'모의' if self.is_paper else '실전(조회만)'}  계좌={mask_account(self.account)}({self.product_name})  "
                f"토큰캐시={self.token_file.name}")


def load_raw() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"설정 파일이 없습니다: {CONFIG_FILE.name} (위치: ~/KIS/config/ 또는 KIS_CONFIG_DIR) "
                                f"— config.example.yaml 을 복사해 채우세요")
    return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}


def load(mode: str = "paper") -> KisConfig:
    """모드에 맞는 설정을 읽는다. 빠진 값이 있으면 키 이름만 알려 준다(값은 보여 주지 않음)."""
    if mode not in _KEYS:
        raise ValueError("mode 는 'paper'(모의) 또는 'real'(실전 키, 조회만)")
    raw = load_raw()
    k = _KEYS[mode]
    missing = [raw_key for raw_key in (k["app"], k["sec"], k["acct"], k["rest"], "my_prod")
               if not _filled(raw.get(raw_key))]
    if missing:
        raise ValueError(f"[{mode}] 설정이 비어 있습니다: {', '.join(missing)}")
    return KisConfig(
        mode=mode,
        app_key=str(raw[k["app"]]),
        app_secret=str(raw[k["sec"]]),
        account=str(raw[k["acct"]]),
        product=str(raw["my_prod"]),
        rest_url=str(raw[k["rest"]]).rstrip("/"),
        user_agent=str(raw.get("my_agent") or "Mozilla/5.0"),
    )


def status() -> list[tuple[str, bool]]:
    """설정 키별 채워짐 여부 (값은 돌려주지 않는다). 설정 점검용."""
    return [(key, _filled(v)) for key, v in load_raw().items()]
