# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""자료 뿌리(DATA) 한 곳을 정한다. 모든 스크립트가 이 파일을 불러 같은 자리를 쓴다.

정하는 순서: 명령줄 `--data <폴더>`(또는 `--data=<폴더>`) → 환경 변수 `EP09_DATA` → 기본값 = 이 폴더의 `data/`.
`--data` 는 여기서 sys.argv 에서 떼어 내므로 각 스크립트의 인자 해석과 부딪히지 않는다(어느 자리에 써도 된다).

자료 뿌리 아래 구조(원본 실험 폴더의 data/ 와 같은 상대 위치):
  disclosure/구조화/<엔드포인트>.csv      OpenDART 주요사항보고서·지분공시 구조화 API 결과(정답지)
  disclosure/원문/<YYYYMMDD>/<접수번호>.zip OpenDART 공시서류원본파일
  fnltt/재무_보고서별.csv                   재무 구조화 값(H5 정답)
  news/analysis_year/events.csv              뉴스 제목 + 기사 뒤 5·30분 수익률
  news/analysis_year/prepost/ 아래 prepost_events.csv  기사 앞뒤 30분 가격 갈래(4단계 정답)
  news/lines/<YYYYMMDD>.csv                  기사 줄별 종목 코드 목록(4단계 기준선 특징)
  daily/_universe_20261104.csv               종목 코드 → 이름(code,name)
  dart/corpCode.zip · dart/listed_corps.json 선택(종목 이름 가리기 보강)
  ep09/                                      이 실험이 만드는 것(표본·정답·실행 기록·채점) 전부
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _pick() -> Path:
    for i, a in enumerate(list(sys.argv)):
        if a == "--data":
            if i + 1 >= len(sys.argv):
                sys.exit("--data 뒤에 폴더를 적어야 한다")
            v = sys.argv[i + 1]
            del sys.argv[i:i + 2]
            return Path(v)
        if a.startswith("--data="):
            del sys.argv[i]
            return Path(a.split("=", 1)[1])
    if os.environ.get("EP09_DATA"):
        return Path(os.environ["EP09_DATA"])
    return HERE.parent / "data"


DATA = _pick().resolve()
