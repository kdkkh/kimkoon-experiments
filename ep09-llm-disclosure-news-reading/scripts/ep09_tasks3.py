# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 3단계 — 과제 정의 · 정답표 · 표본 (2026-11-17). 파일만 읽는다 — 모델 호출·외부 API 호출 없음.

2단계(ep09_sample.py · ep09_run.py · ep09_grade.py)는 고치지 않고 가져다 쓴다. 3단계 정의 파일은 data/ep09/과제3/ 에,
실행 결과는 data/ep09/run3/, 채점은 data/ep09/채점3/ 에 둔다(2단계 파일은 덮어쓰지 않는다).

과제(전부 2단계 표본 266건 · 같은 정답표에서 기계로 만든 정답):
  A3  쉬운 읽기(2단계 실험 A 와 같음. 대량보유 두 칸의 질문 이름만 원문 표기 '주요계약체결'로 고침)
  H1  말 바꾼 질문 — 서식 칸 이름 대신 일상어 질문(H1_Q, 칸 정의만 보고 씀). 정답 = A3 정답 그대로
  H2  단위 바꿔 답하기 — 총액(원) → 억 원, 주식 수(주) → 만 주, 소수 둘째 자리(셋째 자리에서 반올림). 정답은 코드로 환산
  H3  계산형 — 서식 칸 둘 이상으로 계산(H3_ITEMS). 정답은 코드로 계산, 반올림 규칙은 프롬프트와 같음
  H4  섞인 문서 — 같은 종류 다른 회사 공시 2건과 이어 붙인 세 문서 중 지정한 회사 것만(질문은 A3 와 같음)
  H5  재무제표 — 원문과 재무 구조화 값이 짝으로 있는 정기보고서(원본 실험은 4건, 사례 수준 — H5_DOCS)
  B3  뉴스 제목 방향 — 새 표본 7,000건(2단계 800건과 겹치지 않음) · 그중 2,000건(일반 기사 앞 1,000 · 뒤 1,000) 부분 표본

쓰기(이 폴더에서):
  python -X utf8 scripts/ep09_tasks3.py build      # 과제3/ 의 정의·정답·표본 파일을 만든다(같은 시드 → 같은 결과)
  python -X utf8 scripts/ep09_tasks3.py check      # 정답표 자체 점검(개수·환산·계산 확인)
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
from dart_doc import read_text  # noqa: E402  (zip 읽기만)

EP09 = DATA / "ep09"
T3 = EP09 / "과제3"
SEED3 = 20261117
FNLTT = DATA / "fnltt" / "재무_보고서별.csv"
EVENTS = DATA / "news" / "analysis_year" / "events.csv"
NAMES = DATA / "daily" / "_universe_20261104.csv"

# ================================================================ A3: 대량보유 질문 이름 고침(원문 표기)
A3_RENAME = {("majorstock", "ctr_stkqy"): "주요계약체결 주식등의 수(이번 보고서)",
             ("majorstock", "ctr_stkrt"): "주요계약체결 주식등의 비율(%) (이번 보고서)"}

# 정정 표와 본표 값이 다른 칸 — 사람이(이 작업에서는 Claude 가) 원문을 대조한 칸만 '정정 후 값'을 정답으로 바꾼다.
#   (접수번호, 칸) → (정정 후 정답, 근거)
#   원본 실험에는 실제 공시 1건(전환사채 정정 공시의 cvisstk_cnt)이 적혀 있었다. 공개판은 가짜 견본(scripts/ep09_fake_data.py)의 항목 하나로 바꿨다.
#   자기 자료로 돌릴 때는 원문을 직접 대조한 칸만 여기에 적는다(없으면 빈 dict).
CORRECTION_OVERRIDE = {
    ("20260407990901", "cvisstk_cnt"): ("1234567", "가짜 견본: 정정 표 '정정 후' 1,234,567 · 본표에는 정정 전 2,500,000 이 남아 있음(옆 칸 비율은 정정 후 값)"),
}

# ================================================================ H1: 말 바꾼 질문(칸 정의만 보고 씀 — 정답 값을 보고 쓰지 않음)
H1_Q: dict[str, dict[str, str]] = {
    "tsstkAqDecsn": {
        "aqpln_stk_ostk": "회사가 이번에 사들이려는 자기 회사 보통주는 몇 주인가",
        "aqpln_stk_estk": "회사가 이번에 사들이려는 자기 회사 주식 가운데 보통주가 아닌 주식(우선주 등)은 몇 주인가",
        "aqpln_prc_ostk": "보통주를 사들이는 데 쓰려는 돈은 모두 얼마인가",
        "aqpln_prc_estk": "보통주가 아닌 주식(우선주 등)을 사들이는 데 쓰려는 돈은 모두 얼마인가",
        "aqexpd_bgd": "주식을 사들이기 시작할 것으로 잡은 날은 언제인가",
        "aqexpd_edd": "주식 사들이기를 마칠 것으로 잡은 날은 언제인가",
        "aq_wtn_div_ostk_rt": "이번에 사들이기 전, 배당할 수 있는 이익 한도 안에서 사서 이미 들고 있는 자기 회사 보통주는 전체의 몇 퍼센트인가",
        "aq_dd": "회사가 이번 자기 주식 사들이기를 결정한 날은 언제인가",
        "d1_prodlm_ostk": "하루에 낼 수 있는 보통주 매수 주문은 최대 몇 주인가",
    },
    "tsstkDpDecsn": {
        "dppln_stk_ostk": "회사가 들고 있던 자기 회사 보통주 가운데 이번에 내놓으려는(처분하려는) 것은 몇 주인가",
        "dppln_stk_estk": "회사가 들고 있던 자기 회사 주식 가운데 이번에 내놓으려는 보통주가 아닌 주식(우선주 등)은 몇 주인가",
        "dpstk_prc_ostk": "내놓는 보통주 한 주의 값은 얼마로 잡았나",
        "dppln_prc_ostk": "보통주를 내놓아 받게 될 돈은 모두 얼마로 잡았나",
        "dpprpd_bgd": "주식을 내놓기 시작하려는 날은 언제인가",
        "dpprpd_edd": "주식 내놓기를 마치려는 날은 언제인가",
        "dp_m_mkt": "내놓는 주식 가운데 거래소 시장에서 그냥 파는 것은 몇 주인가",
        "dp_m_ovtm": "내놓는 주식 가운데 정규 거래 시간 밖의 대량 거래로 넘기는 것은 몇 주인가",
        "dp_m_otc": "내놓는 주식 가운데 거래소 밖에서(장외) 넘기는 것은 몇 주인가",
        "dp_dd": "회사가 이번 자기 주식 내놓기를 결정한 날은 언제인가",
    },
    "tsstkAqTrctrCnsDecsn": {
        "ctr_prc": "자기 회사 주식을 대신 사 달라고 금융회사에 맡기는 돈은 얼마인가",
        "ctr_pd_bgd": "그 맡기는 계약이 시작되는 날은 언제인가",
        "ctr_pd_edd": "그 맡기는 계약이 끝나는 날은 언제인가",
        "ctr_cns_prd": "계약을 맺기로 한 날은 언제인가",
        "bddd": "이사회가 이 일을 결의한 날은 언제인가",
        "aq_wtn_div_ostk": "계약을 맺기 전, 배당할 수 있는 이익 한도 안에서 사서 이미 들고 있는 자기 회사 보통주는 몇 주인가",
        "aq_wtn_div_ostk_rt": "계약을 맺기 전, 배당할 수 있는 이익 한도 안에서 사서 이미 들고 있는 자기 회사 보통주는 전체의 몇 퍼센트인가",
        "eaq_ostk": "계약을 맺기 전, 그 밖의 방법으로 얻어 들고 있는 자기 회사 보통주는 몇 주인가",
        "od_a_at_t": "이 결의를 한 이사회에 나온 사외이사는 몇 명인가",
    },
    "tsstkAqTrctrCcDecsn": {
        "ctr_prc_bfcc": "끝내려는(해지하려는) 계약에 끝내기 전까지 맡겨 둔 돈은 얼마인가",
        "ctr_prc_atcc": "계약을 끝낸 뒤에 남는 계약 금액은 얼마인가",
        "ctr_pd_bfcc_bgd": "끝내려는 계약이 원래 시작된 날은 언제인가",
        "ctr_pd_bfcc_edd": "끝내려는 계약이 원래 끝나기로 돼 있던 날은 언제인가",
        "cc_prd": "계약을 끝내기로 한 날은 언제인가",
        "bddd": "이사회가 이 일을 결의한 날은 언제인가",
        "aq_wtn_div_ostk": "계약을 끝내기 전, 배당할 수 있는 이익 한도 안에서 사서 들고 있는 자기 회사 보통주는 몇 주인가",
        "aq_wtn_div_ostk_rt": "계약을 끝내기 전, 배당할 수 있는 이익 한도 안에서 사서 들고 있는 자기 회사 보통주는 전체의 몇 퍼센트인가",
    },
    "piicDecsn": {
        "nstk_ostk_cnt": "이번에 돈을 받고 새로 발행하는 보통주는 몇 주인가",
        "nstk_estk_cnt": "이번에 새로 발행하는 주식 가운데 보통주가 아닌 주식(우선주 등)은 몇 주인가",
        "fv_ps": "주식 한 주의 액면 금액은 얼마인가",
        "bfic_tisstk_ostk": "이번에 주식을 늘리기 전에 이미 발행돼 있는 보통주는 모두 몇 주인가",
        "fdpp_fclt": "모은 돈 가운데 공장·설비 같은 시설에 쓰려는 돈은 얼마인가",
        "fdpp_op": "모은 돈 가운데 회사를 꾸려 가는 데(운영) 쓰려는 돈은 얼마인가",
        "fdpp_dtrp": "모은 돈 가운데 빚을 갚는 데 쓰려는 돈은 얼마인가",
        "fdpp_ocsa": "모은 돈 가운데 다른 회사의 주식 같은 증권을 사는 데 쓰려는 돈은 얼마인가",
        "ic_mthn": "새 주식을 누구에게 어떤 방식으로 나눠 주고 돈을 받는가",
    },
    "fricDecsn": {
        "nstk_ostk_cnt": "이번에 주주에게 돈을 받지 않고 새로 나눠 주는 보통주는 몇 주인가",
        "nstk_estk_cnt": "이번에 돈을 받지 않고 새로 나눠 주는 주식 가운데 보통주가 아닌 주식(우선주 등)은 몇 주인가",
        "fv_ps": "주식 한 주의 액면 금액은 얼마인가",
        "bfic_tisstk_ostk": "이번에 주식을 늘리기 전에 이미 발행돼 있는 보통주는 모두 몇 주인가",
        "nstk_asstd": "어느 날 주주 명부에 올라 있는 사람에게 새 주식을 나눠 주는가",
        "nstk_ascnt_ps_ostk": "지금 가진 보통주 한 주에 새 보통주를 몇 주씩 나눠 주는가",
        "nstk_dividrk": "새 주식은 어느 날부터 배당 계산에 들어가는가",
        "nstk_dlprd": "새 주식의 주권(증서)을 주주에게 내어 줄 예정인 날은 언제인가",
        "nstk_lstprd": "새 주식이 거래소에 올라 거래될 예정인 날은 언제인가",
        "bddd": "이사회가 이 일을 결의한 날은 언제인가",
    },
    "pifricDecsn": {
        "piic_nstk_ostk_cnt": "돈을 받고 새로 발행하는 쪽(유상)의 새 보통주는 몇 주인가",
        "piic_fv_ps": "돈을 받고 발행하는 쪽(유상)에서 주식 한 주의 액면 금액은 얼마인가",
        "piic_bfic_tisstk_ostk": "돈을 받고 주식을 늘리기(유상) 전에 이미 발행돼 있는 보통주는 모두 몇 주인가",
        "piic_fdpp_fclt": "돈을 받고 발행해 모은 돈 가운데 공장·설비 같은 시설에 쓰려는 돈은 얼마인가",
        "piic_fdpp_op": "돈을 받고 발행해 모은 돈 가운데 회사를 꾸려 가는 데(운영) 쓰려는 돈은 얼마인가",
        "piic_fdpp_dtrp": "돈을 받고 발행해 모은 돈 가운데 빚을 갚는 데 쓰려는 돈은 얼마인가",
        "fric_nstk_ostk_cnt": "돈을 받지 않고 나눠 주는 쪽(무상)의 새 보통주는 몇 주인가",
        "fric_nstk_estk_cnt": "돈을 받지 않고 나눠 주는 쪽(무상)의 새 주식 가운데 보통주가 아닌 주식(우선주 등)은 몇 주인가",
        "fric_nstk_asstd": "돈을 받지 않고 나눠 주는 새 주식은 어느 날 주주 명부에 올라 있는 사람에게 주는가",
        "fric_nstk_ascnt_ps_ostk": "돈을 받지 않고 나눠 줄 때, 가진 보통주 한 주에 새 보통주를 몇 주씩 주는가",
    },
    "crDecsn": {
        "fv_ps": "주식 한 주의 액면 금액은 얼마인가",
        "crstk_ostk_cnt": "이번에 줄이는(없애는) 보통주는 몇 주인가",
        "crstk_estk_cnt": "이번에 줄이는 주식 가운데 보통주가 아닌 주식(우선주 등)은 몇 주인가",
        "bfcr_cpt": "주식을 줄이기 전 회사의 자본금은 얼마인가",
        "atcr_cpt": "주식을 줄인 뒤 회사의 자본금은 얼마가 되는가",
        "bfcr_tisstk_ostk": "주식을 줄이기 전에 발행돼 있는 보통주는 모두 몇 주인가",
        "atcr_tisstk_ostk": "주식을 줄인 뒤에 남는 보통주는 모두 몇 주인가",
        "cr_rt_ostk": "보통주를 몇 퍼센트 줄이는가",
        "cr_std": "주식을 줄이는 기준이 되는 날은 언제인가",
        "crsc_gmtsck_prd": "이 안건을 다룰 주주총회가 열릴 예정인 날은 언제인가",
    },
    "cvbdIsDecsn": {
        "bd_tm": "이번 사채는 이 회사의 몇 번째(몇 회차) 사채인가",
        "bd_fta": "이번에 사채를 내어 빌리는 돈은 액면 기준으로 모두 얼마인가",
        "bd_intr_ex": "이 사채에 겉으로 붙는(정기적으로 주는) 연 이자율은 몇 퍼센트인가",
        "bd_intr_sf": "이 사채를 만기까지 들고 있을 때 보장되는 연 수익률은 몇 퍼센트인가",
        "bd_mtd": "이 사채의 원금을 갚기로 한 마지막 날은 언제인가",
        "cv_prc": "이 사채를 주식으로 바꿀 때 주식 한 주를 얼마로 쳐 주는가",
        "cvisstk_cnt": "이 사채를 모두 주식으로 바꾸면 새로 생기는 주식은 몇 주인가",
        "cvisstk_tisstk_vs": "이 사채를 모두 주식으로 바꿔 생기는 주식은 회사 전체 주식 수의 몇 퍼센트인가",
        "act_mktprcfl_cvprc_lwtrsprc": "주가가 떨어져 주식으로 바꾸는 값을 낮추게 될 때, 가장 낮게 내릴 수 있는 한도 가격은 얼마인가",
        "pymd": "사채를 사는 쪽이 돈을 넣는 날은 언제인가",
    },
    "bdwtIsDecsn": {
        "bd_tm": "이번 사채는 이 회사의 몇 번째(몇 회차) 사채인가",
        "bd_fta": "이번에 사채를 내어 빌리는 돈은 액면 기준으로 모두 얼마인가",
        "bd_intr_ex": "이 사채에 겉으로 붙는(정기적으로 주는) 연 이자율은 몇 퍼센트인가",
        "bd_intr_sf": "이 사채를 만기까지 들고 있을 때 보장되는 연 수익률은 몇 퍼센트인가",
        "bd_mtd": "이 사채의 원금을 갚기로 한 마지막 날은 언제인가",
        "ex_prc": "이 사채에 붙은 권리로 새 주식을 살 때 한 주를 얼마에 살 수 있는가",
        "nstk_isstk_cnt": "이 사채에 붙은 새 주식을 살 권리를 모두 쓰면 새로 생기는 주식은 몇 주인가",
        "nstk_isstk_tisstk_vs": "그 권리를 모두 써서 생기는 주식은 회사 전체 주식 수의 몇 퍼센트인가",
        "act_mktprcfl_cvprc_lwtrsprc": "주가가 떨어져 새 주식을 사는 값을 낮추게 될 때, 가장 낮게 내릴 수 있는 한도 가격은 얼마인가",
        "pymd": "사채를 사는 쪽이 돈을 넣는 날은 언제인가",
    },
    "exbdIsDecsn": {
        "bd_tm": "이번 사채는 이 회사의 몇 번째(몇 회차) 사채인가",
        "bd_fta": "이번에 사채를 내어 빌리는 돈은 액면 기준으로 모두 얼마인가",
        "bd_intr_ex": "이 사채에 겉으로 붙는(정기적으로 주는) 연 이자율은 몇 퍼센트인가",
        "bd_intr_sf": "이 사채를 만기까지 들고 있을 때 보장되는 연 수익률은 몇 퍼센트인가",
        "bd_mtd": "이 사채의 원금을 갚기로 한 마지막 날은 언제인가",
        "ex_prc": "이 사채를 회사가 가진 주식과 바꿀 때 주식 한 주를 얼마로 쳐 주는가",
        "extg_stkcnt": "이 사채와 바꿔 줄 수 있는 주식은 모두 몇 주인가",
        "extg_tisstk_vs": "이 사채와 바꿔 줄 수 있는 주식은 전체 발행 주식 수의 몇 퍼센트인가",
        "fdpp_op": "빌린 돈 가운데 회사를 꾸려 가는 데(운영) 쓰려는 돈은 얼마인가",
        "pymd": "사채를 사는 쪽이 돈을 넣는 날은 언제인가",
    },
    "cmpMgDecsn": {
        "bddd": "이사회가 이 일을 결의한 날은 언제인가",
        "mgnstk_ostk_cnt": "회사를 합치면서 새로 발행해 나눠 주는 보통주는 몇 주인가",
        "rbsnfdtl_tast": "합쳐지는 상대 회사가 가장 최근 회계연도에 가진 재산(자산)은 모두 얼마인가",
        "rbsnfdtl_tdbt": "합쳐지는 상대 회사가 가장 최근 회계연도에 진 빚(부채)은 모두 얼마인가",
        "rbsnfdtl_teqt": "합쳐지는 상대 회사의 가장 최근 회계연도 자본(자산에서 부채를 뺀 것)은 모두 얼마인가",
        "rbsnfdtl_cpt": "합쳐지는 상대 회사의 가장 최근 회계연도 자본금(주식 액면 합계)은 얼마인가",
        "rbsnfdtl_sl": "합쳐지는 상대 회사는 가장 최근 회계연도에 얼마어치를 팔았나(매출)",
        "rbsnfdtl_nic": "합쳐지는 상대 회사는 가장 최근 회계연도에 최종적으로 얼마를 벌었나(손실이면 음수)",
        "mgsc_mgctrd": "두 회사가 합치기로 계약을 맺는 날은 언제인가",
        "mgsc_mgdt": "두 회사가 실제로 하나로 합쳐지는 기준 날은 언제인가",
    },
    "otcprStkInvscrInhDecsn": {
        "bddd": "이사회가 이 일을 결의한 날은 언제인가",
        "inhdtl_stkcnt": "이번에 사들이는(넘겨받는) 다른 회사 주식은 몇 주인가",
        "inhdtl_inhprc": "그 주식을 사들이는 데 치르는 돈은 모두 얼마인가",
        "inhdtl_tast": "비교 기준으로 적은, 공시를 낸 회사의 총자산은 얼마인가",
        "inhdtl_tast_vs": "사들이는 값은 공시를 낸 회사 총자산의 몇 퍼센트인가",
        "inhdtl_ecpt": "비교 기준으로 적은, 공시를 낸 회사의 자기자본은 얼마인가",
        "inhdtl_ecpt_vs": "사들이는 값은 공시를 낸 회사 자기자본의 몇 퍼센트인가",
        "atinh_owstkcnt": "사들인 뒤에는 그 회사 주식을 모두 몇 주 갖게 되는가",
        "atinh_eqrt": "사들인 뒤에는 그 회사 지분을 몇 퍼센트 갖게 되는가",
        "inh_prd": "주식을 넘겨받기로 한 날은 언제인가",
    },
    "otcprStkInvscrTrfDecsn": {
        "bddd": "이사회가 이 일을 결의한 날은 언제인가",
        "trfdtl_stkcnt": "이번에 넘겨주는(파는) 다른 회사 주식은 몇 주인가",
        "trfdtl_trfprc": "그 주식을 넘겨주고 받는 돈은 모두 얼마인가",
        "trfdtl_tast": "비교 기준으로 적은, 공시를 낸 회사의 총자산은 얼마인가",
        "trfdtl_tast_vs": "넘겨주는 값은 공시를 낸 회사 총자산의 몇 퍼센트인가",
        "trfdtl_ecpt": "비교 기준으로 적은, 공시를 낸 회사의 자기자본은 얼마인가",
        "trfdtl_ecpt_vs": "넘겨주는 값은 공시를 낸 회사 자기자본의 몇 퍼센트인가",
        "attrf_owstkcnt": "넘겨준 뒤에는 그 회사 주식을 몇 주 갖고 있게 되는가",
        "attrf_eqrt": "넘겨준 뒤에는 그 회사 지분을 몇 퍼센트 갖고 있게 되는가",
        "trf_prd": "주식을 넘겨주기로 한 날은 언제인가",
    },
    "majorstock": {
        "report_tp": "이 보고서는 일반 보고인가 약식 보고인가",
        "stkqy": "이번 보고 시점에 보고자 쪽이 들고 있는 주식 등은 모두 몇 주인가",
        "stkqy_irds": "들고 있는 주식 등은 직전 보고 때보다 몇 주 늘거나 줄었나(줄었으면 음수)",
        "stkrt": "이번 보고 시점에 보고자 쪽이 들고 있는 비율은 몇 퍼센트인가",
        "stkrt_irds": "들고 있는 비율은 직전 보고 때보다 몇 퍼센트포인트 달라졌나(줄었으면 음수)",
        "ctr_stkqy": "이번 보고 시점에, 들고 있는 주식 등 가운데 담보·대여 같은 주요 계약이 맺어져 있는 것은 몇 주인가",
        "ctr_stkrt": "이번 보고 시점에, 담보·대여 같은 주요 계약이 맺어져 있는 주식 등의 비율은 몇 퍼센트인가",
    },
    "elestock": {
        "isu_exctv_rgist_at": "보고한 사람이 이 회사 임원이라면 등기된 임원인가 등기되지 않은 임원인가",
        "isu_main_shrholdr": "보고한 사람이 이 회사의 주요 주주라면 어떤 주요 주주에 해당하는가",
        "sp_stock_lmp_cnt": "이번 보고 시점에 보고한 사람이 들고 있는 이 회사 주식 등은 모두 몇 주인가",
        "sp_stock_lmp_irds_cnt": "들고 있는 주식 등은 직전 보고 때보다 몇 주 늘거나 줄었나(줄었으면 음수)",
        "sp_stock_lmp_rate": "이번 보고 시점에 보고한 사람이 들고 있는 비율은 몇 퍼센트인가",
        "sp_stock_lmp_irds_rate": "들고 있는 비율은 직전 보고 때보다 몇 퍼센트포인트 달라졌나(줄었으면 음수)",
    },
}

# ================================================================ H2: 단위 바꿔 답하기
# 대상: 형 num 이고 단위가 '원'(총액) 또는 '주'(주식 수)인 칸. 아래는 뺀다(칸 정의만 보고 정함 — 내가 정함):
#   주당 가격·액면가(억 원으로 바꾸면 0.00 이 됨) · 1주당 배정 주식수(비율 성격) · %·%p·날짜·분류·회차·명
H2_EXCLUDE = {"fv_ps", "piic_fv_ps", "dpstk_prc_ostk", "cv_prc", "ex_prc", "act_mktprcfl_cvprc_lwtrsprc",
              "nstk_ascnt_ps_ostk", "fric_nstk_ascnt_ps_ostk"}
H2_UNIT = {"원": ("억 원", Decimal(10) ** 8), "주": ("만 주", Decimal(10) ** 4)}
H2_DEC = 2

# ================================================================ H3: 계산형(칸 정의만 보고 정함)
# (id, 질문 문장, 식, 답 단위, 소수 자리)   식: 칸 이름으로 쓴 파이썬 식. days(a, b) = b − a 의 달력 날수.
H3_ITEMS: dict[str, list[tuple[str, str, str, str, int]]] = {
    "tsstkAqDecsn": [
        ("c1", "「취득예정금액(원) 보통주식」 ÷ 「취득예정주식(주) 보통주식」 = 보통주 1주당 취득 예정 금액", "aqpln_prc_ostk / aqpln_stk_ostk", "원", 0),
        ("c2", "「취득예상기간 시작일」부터 「취득예상기간 종료일」까지의 날수(종료일 − 시작일)", "days(aqexpd_bgd, aqexpd_edd)", "일", 0),
    ],
    "tsstkDpDecsn": [
        ("c1", "「처분예정주식(주) 보통주식」 × 「처분 대상 주식가격(원) 보통주식」", "dppln_stk_ostk * dpstk_prc_ostk", "원", 0),
        ("c2", "「처분예정기간 시작일」부터 「처분예정기간 종료일」까지의 날수(종료일 − 시작일)", "days(dpprpd_bgd, dpprpd_edd)", "일", 0),
    ],
    "tsstkAqTrctrCnsDecsn": [
        ("c1", "「계약기간 시작일」부터 「계약기간 종료일」까지의 날수(종료일 − 시작일)", "days(ctr_pd_bgd, ctr_pd_edd)", "일", 0),
        ("c2", "「이사회결의일(결정일)」부터 「계약기간 종료일」까지의 날수(종료일 − 이사회결의일)", "days(bddd, ctr_pd_edd)", "일", 0),
    ],
    "tsstkAqTrctrCcDecsn": [
        ("c1", "「해지 전 계약기간 시작일」부터 「해지 전 계약기간 종료일」까지의 날수(종료일 − 시작일)", "days(ctr_pd_bfcc_bgd, ctr_pd_bfcc_edd)", "일", 0),
        ("c2", "「해지예정일자」부터 「해지 전 계약기간 종료일」까지 남은 날수(종료일 − 해지예정일자, 해지예정일자가 더 뒤면 음수)", "days(cc_prd, ctr_pd_bfcc_edd)", "일", 0),
    ],
    "piicDecsn": [
        ("c1", "「증자전 발행주식총수(주) 보통주식」 + 「신주의 종류와 수 보통주식(주)」 = 증자 후 보통주 발행주식총수", "bfic_tisstk_ostk + nstk_ostk_cnt", "주", 0),
        ("c2", "「신주의 종류와 수 보통주식(주)」 ÷ 「증자전 발행주식총수(주) 보통주식」 × 100", "nstk_ostk_cnt / bfic_tisstk_ostk * 100", "%", 2),
        ("c3", "「신주의 종류와 수 보통주식(주)」 × 「1주당 액면가액(원)」", "nstk_ostk_cnt * fv_ps", "원", 0),
    ],
    "fricDecsn": [
        ("c1", "「증자전 발행주식총수 보통주식(주)」 + 「신주의 종류와 수 보통주식(주)」 = 증자 후 보통주 발행주식총수", "bfic_tisstk_ostk + nstk_ostk_cnt", "주", 0),
        ("c2", "「신주의 종류와 수 보통주식(주)」 ÷ 「증자전 발행주식총수 보통주식(주)」 × 100", "nstk_ostk_cnt / bfic_tisstk_ostk * 100", "%", 2),
        ("c3", "「신주배정기준일」부터 「신주의 상장 예정일」까지의 날수(상장 예정일 − 신주배정기준일)", "days(nstk_asstd, nstk_lstprd)", "일", 0),
    ],
    "pifricDecsn": [
        ("c1", "「유상증자 신주의 종류와 수 보통주식(주)」 + 「무상증자 신주의 종류와 수 보통주식(주)」", "piic_nstk_ostk_cnt + fric_nstk_ostk_cnt", "주", 0),
        ("c2", "「유상증자 증자전 발행주식총수 보통주식(주)」 + 「유상증자 신주의 종류와 수 보통주식(주)」 + 「무상증자 신주의 종류와 수 보통주식(주)」", "piic_bfic_tisstk_ostk + piic_nstk_ostk_cnt + fric_nstk_ostk_cnt", "주", 0),
        ("c3", "「유상증자 신주의 종류와 수 보통주식(주)」 ÷ 「유상증자 증자전 발행주식총수 보통주식(주)」 × 100", "piic_nstk_ostk_cnt / piic_bfic_tisstk_ostk * 100", "%", 2),
    ],
    "crDecsn": [
        ("c1", "「감자전 자본금(원)」 − 「감자후 자본금(원)」 = 줄어드는 자본금", "bfcr_cpt - atcr_cpt", "원", 0),
        ("c2", "「감자전 발행주식수 보통주식(주)」 − 「감자후 발행주식수 보통주식(주)」", "bfcr_tisstk_ostk - atcr_tisstk_ostk", "주", 0),
        ("c3", "(「감자전 자본금(원)」 − 「감자후 자본금(원)」) ÷ 「감자전 자본금(원)」 × 100", "(bfcr_cpt - atcr_cpt) / bfcr_cpt * 100", "%", 2),
    ],
    "cvbdIsDecsn": [
        ("c1", "「사채의 권면(전자등록)총액(원)」 ÷ 「전환가액(원/주)」", "bd_fta / cv_prc", "주", 0),
        ("c2", "「사채의 이율 만기이자율(%)」 − 「사채의 이율 표면이자율(%)」", "bd_intr_sf - bd_intr_ex", "%p", 2),
        ("c3", "「납입일」부터 「사채만기일」까지의 날수(사채만기일 − 납입일)", "days(pymd, bd_mtd)", "일", 0),
    ],
    "bdwtIsDecsn": [
        ("c1", "「사채의 권면(전자등록)총액(원)」 ÷ 「신주인수권 행사가액(원/주)」", "bd_fta / ex_prc", "주", 0),
        ("c2", "「사채의 이율 만기이자율(%)」 − 「사채의 이율 표면이자율(%)」", "bd_intr_sf - bd_intr_ex", "%p", 2),
        ("c3", "「납입일」부터 「사채만기일」까지의 날수(사채만기일 − 납입일)", "days(pymd, bd_mtd)", "일", 0),
    ],
    "exbdIsDecsn": [
        ("c1", "「사채의 권면(전자등록)총액(원)」 ÷ 「교환가액(원/주)」", "bd_fta / ex_prc", "주", 0),
        ("c2", "「사채의 이율 만기이자율(%)」 − 「사채의 이율 표면이자율(%)」", "bd_intr_sf - bd_intr_ex", "%p", 2),
        ("c3", "「납입일」부터 「사채만기일」까지의 날수(사채만기일 − 납입일)", "days(pymd, bd_mtd)", "일", 0),
    ],
    "cmpMgDecsn": [
        ("c1", "합병상대회사 최근 사업연도 재무내용의 「부채총계(원)」 ÷ 「자본총계(원)」 × 100", "rbsnfdtl_tdbt / rbsnfdtl_teqt * 100", "%", 2),
        ("c2", "합병상대회사 최근 사업연도 재무내용의 「당기순이익(원)」 ÷ 「매출액(원)」 × 100", "rbsnfdtl_nic / rbsnfdtl_sl * 100", "%", 2),
        ("c3", "「합병일정 합병계약일」부터 「합병일정 합병기일」까지의 날수(합병기일 − 합병계약일)", "days(mgsc_mgctrd, mgsc_mgdt)", "일", 0),
    ],
    "otcprStkInvscrInhDecsn": [
        ("c1", "「양수내역 양수금액(원)」 ÷ 「양수내역 양수주식수(주)」 = 1주당 양수금액", "inhdtl_inhprc / inhdtl_stkcnt", "원", 0),
        ("c2", "「양수내역 총자산(원)」 − 「양수내역 자기자본(원)」", "inhdtl_tast - inhdtl_ecpt", "원", 0),
        ("c3", "「이사회결의일(결정일)」부터 「양수예정일자」까지의 날수(양수예정일자 − 이사회결의일)", "days(bddd, inh_prd)", "일", 0),
    ],
    "otcprStkInvscrTrfDecsn": [
        ("c1", "「양도내역 양도금액(원)」 ÷ 「양도내역 양도주식수(주)」 = 1주당 양도금액", "trfdtl_trfprc / trfdtl_stkcnt", "원", 0),
        ("c2", "「양도내역 총자산(원)」 − 「양도내역 자기자본(원)」", "trfdtl_tast - trfdtl_ecpt", "원", 0),
        ("c3", "「이사회결의일(결정일)」부터 「양도예정일자」까지의 날수(양도예정일자 − 이사회결의일)", "days(bddd, trf_prd)", "일", 0),
    ],
    "majorstock": [
        ("c1", "「보유주식등의 수(이번 보고서)」 − 「보유주식등의 증감」 = 직전 보고서 기준 보유주식등의 수", "stkqy - stkqy_irds", "주", 0),
        ("c2", "「보유비율(%) (이번 보고서)」 − 「보유비율 증감(%p)」 = 직전 보고서 기준 보유비율", "stkrt - stkrt_irds", "%", 2),
    ],
    "elestock": [
        ("c1", "「특정 증권 등 소유 수(이번 보고서)」 − 「특정 증권 등 소유 증감 수」 = 직전 보고서 기준 소유 수", "sp_stock_lmp_cnt - sp_stock_lmp_irds_cnt", "주", 0),
        ("c2", "「특정 증권 등 소유 비율(%)」 − 「특정 증권 등 소유 증감 비율(%p)」 = 직전 보고서 기준 소유 비율", "sp_stock_lmp_rate - sp_stock_lmp_irds_rate", "%", 2),
    ],
}

# ================================================================ H4 · H5 · B3 설정
H4_MAX_CHARS = 150_000            # 세 문서를 합친 글자 수가 이보다 크면 그 건은 뺀다(문맥 한도 보호 — 내가 정함)
H5_DOCS = [                       # (접수번호, 종목코드, 연도, 보고서) — 원문 zip 과 재무 구조화 값이 함께 있는 정기보고서
    # 원본 실험: 받아 둔 정기보고서 4건(실제 접수번호·종목코드). 공개판은 가짜 견본 4건 — 자기 자료로 돌릴 때 바꿔 적는다.
    ("20251114990801", "FK9001", "2025", "TQ"),
    ("20260316990802", "FK9002", "2025", "FY"),
    ("20260515990803", "FK9003", "2026", "FQ"),
    ("20260814990804", "FK9004", "2026", "HY"),
]
H5_MEASURES = [("매출액_누적", "매출액(영업수익)"), ("영업이익_누적", "영업이익(손실이면 음수)"), ("순이익_누적", "당기순이익(분기·반기순이익, 손실이면 음수)")]
B3_PLAN = [("일반 기사", "앞", 3000), ("일반 기사", "뒤", 3000), ("시세 중계", "뒤", 1000)]
B3_SUB = 1000                     # 부분 표본: 일반 기사 앞·뒤에서 각 1,000건
B_BATCH = 20
FRONT_END, BACK_BGN = "20260531", "20260701"


def q2(x: Decimal, dec: int) -> Decimal:
    """사사오입(0.5 는 0 에서 먼 쪽으로)."""
    return x.quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)


def fmt(x: Decimal) -> str:
    s = format(x, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def load_defs() -> pd.DataFrame:
    return pd.read_csv(EP09 / "sample_A_칸정의.csv", dtype=str, encoding="utf-8-sig").fillna("")


def load_docs() -> pd.DataFrame:
    return pd.read_csv(EP09 / "sample_A.csv", dtype=str, encoding="utf-8-sig").fillna("")


def key_a3() -> pd.DataFrame:
    """A3 정답 = 2단계 정답표 + 대량보유 질문 이름 고침 + 대조한 정정 칸만 '정정 후 값'."""
    k = pd.read_csv(EP09 / "sample_A_정답.csv", dtype=str, encoding="utf-8-sig").fillna("")
    k["질문이름"] = [A3_RENAME.get((a, b), q) for a, b, q in zip(k["kind"], k["칸"], k["질문이름"])]
    k["정답_2단계"] = k["정답"]
    k["정정대조"] = ""
    for (rcp, col), (val, why) in CORRECTION_OVERRIDE.items():
        m = (k["rcept_no"] == rcp) & (k["칸"] == col)
        if m.sum() == 0:      # 공개판에서 더함: 이 상수는 가짜 견본의 접수번호다 — 자기 자료에는 없으니 건너뛴다(상수는 지우지 말 것, 가짜 생성기가 읽는다)
            print(f"  (건너뜀) CORRECTION_OVERRIDE {rcp} · {col} — 표본에 없음")
            continue
        assert m.sum() == 1, (rcp, col)
        k.loc[m, "정답"] = val
        k.loc[m, "상태"] = "값"
        k.loc[m, "정정대조"] = why
    return k


def fields_for(task: str) -> dict[str, list[dict]]:
    """종류 → 질문 목록(순서 고정). 각 항목: id(칸 또는 c1…)·질문·형·단위 글·선택지."""
    d = load_defs()
    out = defaultdict(list)
    if task == "H3":
        for kind, items in H3_ITEMS.items():
            for cid, q, _, unit, dec in items:
                tail = "정수로(소수 첫째 자리에서 반올림)" if dec == 0 else f"소수 {dec}째 자리까지(그다음 자리에서 반올림)".replace("2째", "둘째")
                out[kind].append({"칸": cid, "질문": q, "형": "num", "단위글": f"숫자, 단위 {unit}, {tail}", "선택지": ""})
        return out
    for r in d.itertuples(index=False):
        q = A3_RENAME.get((r.kind, r.칸), r.질문이름)
        if task == "H1":
            if r.kind not in H1_Q:
                continue
            q = H1_Q[r.kind][r.칸]
        if task == "H2":
            if r.형 != "num" or r.단위 not in H2_UNIT or r.칸 in H2_EXCLUDE:
                continue
            unit = f"숫자, 단위 {H2_UNIT[r.단위][0]} — 소수 둘째 자리까지(셋째 자리에서 반올림)"
        elif r.형 == "enum":
            unit = "분류 — 다음 중 하나: " + ", ".join(o.strip() for o in r.선택지.split("|"))
        elif r.형 == "date":
            unit = "날짜"
        else:
            unit = f"숫자, 단위 {r.단위}"
        out[r.kind].append({"칸": r.칸, "질문": q, "형": r.형, "단위글": unit, "선택지": r.선택지})
    return out


# ================================================================ 정답표
def key_h2(k: pd.DataFrame) -> pd.DataFrame:
    f = fields_for("H2")
    rows = []
    for r in k.itertuples(index=False):
        if not any(x["칸"] == r.칸 for x in f.get(r.kind, [])):
            continue
        name, div = H2_UNIT[r.단위]
        if r.상태 == "값":
            raw = Decimal(r.정답) / div
            rows.append({"kind": r.kind, "rcept_no": r.rcept_no, "칸": r.칸, "형": "num", "단위": name, "소수": H2_DEC, "정답": fmt(q2(raw, H2_DEC)),
                         "정답_반올림전": fmt(raw), "원단위_정답": r.정답, "상태": "값"})
        else:
            rows.append({"kind": r.kind, "rcept_no": r.rcept_no, "칸": r.칸, "형": "num", "단위": name, "소수": H2_DEC, "정답": "", "정답_반올림전": "", "원단위_정답": "", "상태": r.상태})
    return pd.DataFrame(rows)


def _days(a: str, b: str) -> Decimal:
    return Decimal((date(int(b[:4]), int(b[4:6]), int(b[6:])) - date(int(a[:4]), int(a[4:6]), int(a[6:]))).days)


def key_h3(k: pd.DataFrame) -> pd.DataFrame:
    tp = {(r.kind, r.칸): r.형 for r in load_defs().itertuples(index=False)}
    rows = []
    for (kind, rcp), g in k.groupby(["kind", "rcept_no"], sort=False):
        val = {r.칸: (r.정답, r.상태) for r in g.itertuples(index=False)}
        for cid, q, expr, unit, dec in H3_ITEMS.get(kind, []):
            names = sorted(set(re.findall(r"[a-z][a-z0-9_]+", expr)) - {"days"})
            st = [val[n][1] for n in names]
            row = {"kind": kind, "rcept_no": rcp, "칸": cid, "형": "num", "단위": unit, "소수": dec, "식": expr, "입력": " · ".join(f"{n}={val[n][0] or '∅'}" for n in names)}
            if any(s == "해석불가" for s in st):
                row.update(정답="", 정답_반올림전="", 상태="해석불가")
            elif any(s != "값" for s in st):
                row.update(정답="", 정답_반올림전="", 상태="빈칸")              # 입력 칸이 하나라도 비면 답도 null 이어야 한다
            else:
                env = {n: (val[n][0] if tp[(kind, n)] == "date" else Decimal(val[n][0])) for n in names}
                try:
                    raw = eval(expr, {"__builtins__": {}, "days": _days}, env)  # 식은 이 파일에 적힌 것뿐
                    row.update(정답=fmt(q2(Decimal(raw), dec)), 정답_반올림전=fmt(Decimal(raw).quantize(Decimal("0.000001"))), 상태="값")
                except Exception:                                               # 0 으로 나누기 등
                    row.update(정답="", 정답_반올림전="", 상태="해석불가")
            rows.append(row)
    return pd.DataFrame(rows)


def h4_groups() -> pd.DataFrame:
    """대상 문서마다 같은 종류·다른 회사 문서 2건을 고정 시드로 골라 세 문서의 순서를 섞는다."""
    docs = load_docs().sort_values(["kind", "rcept_no"])
    rng = random.Random(SEED3 + 4)
    txt = {}

    def text_of(r):
        if r not in txt:
            txt[r] = re.sub(r"\s+", "", read_text(r))
        return txt[r]
    rows = []
    for kind, g in docs.groupby("kind", sort=False):
        recs = g.to_dict("records")
        for t in recs:
            name = t["corp_name"]
            core = re.sub(r"\s+", "", name)
            row = {"kind": kind, "rcept_no": t["rcept_no"], "회사명": name, "문서1": "", "문서2": "", "문서3": "", "대상_위치": "", "합친_글자수": "", "뺀_이유": ""}
            if core not in text_of(t["rcept_no"]):
                row["뺀_이유"] = "대상 문서 글에 회사명이 글자 그대로 없음"
                rows.append(row)
                continue
            cand = [o for o in recs if o["corp_name"] != name and core not in text_of(o["rcept_no"])
                    and re.sub(r"\s+", "", o["corp_name"]) not in text_of(t["rcept_no"])]
            cand.sort(key=lambda o: o["rcept_no"])
            if len(cand) < 2:
                row["뺀_이유"] = f"같은 종류의 다른 회사 문서가 2건 미만({len(cand)}건)"
                rows.append(row)
                continue
            pick = rng.sample(cand, 2)
            order = [t["rcept_no"]] + [p["rcept_no"] for p in pick]
            rng.shuffle(order)
            total = int(t["원문_글자수"]) + sum(int(p["원문_글자수"]) for p in pick)
            row.update(문서1=order[0], 문서2=order[1], 문서3=order[2], 대상_위치=order.index(t["rcept_no"]) + 1, 합친_글자수=total)
            if total > H4_MAX_CHARS:
                row["뺀_이유"] = f"세 문서 합친 글자 수 {total:,} > {H4_MAX_CHARS:,}"
            rows.append(row)
    return pd.DataFrame(rows)


def key_h5() -> tuple[pd.DataFrame, pd.DataFrame]:
    f = pd.read_csv(FNLTT, dtype=str, encoding="utf-8-sig").fillna("")
    prev = {"FY": "FY", "HY": "HY", "TQ": "TQ", "FQ": "FQ"}
    docs, rows = [], []
    for rcp, code, year, rep in H5_DOCS:
        g = f[(f["종목코드"] == code)]
        cur = g[(g["연도"] == year) & (g["보고서"] == rep)]
        old = g[(g["연도"] == str(int(year) - 1)) & (g["보고서"] == prev[rep])]
        name = g["회사명"].iloc[0] if len(g) else ""
        docs.append({"rcept_no": rcp, "종목코드": code, "회사명": name, "연도": year, "보고서": rep, "통화": ",".join(sorted(set(cur["통화"]))),
                     "결산기준일": ",".join(sorted(set(cur["결산기준일"]))), "글자수": len(read_text(rcp)), "재무_당기줄": len(cur), "재무_전기줄": len(old)})
        n = 0
        for scope in ("연결", "별도"):
            for period, src in (("당기", cur), ("전기", old)):
                s = src[src["연결"] == scope]
                if len(s) != 1:
                    continue
                for col, label in H5_MEASURES:
                    if period == "전기" and col != "매출액_누적":
                        continue                                               # 전기는 매출액만 묻는다(문항 수를 줄임 — 내가 정함)
                    v = s[col].iloc[0]
                    if v == "":
                        continue
                    n += 1
                    raw = Decimal(v) / Decimal(10) ** 6
                    rows.append({"kind": "H5", "rcept_no": rcp, "칸": f"f{n:02d}", "형": "num", "단위": "백만", "소수": 0, "범위": scope, "기간": period, "항목": label,
                                 "정답": fmt(q2(raw, 0)), "정답_반올림전": fmt(raw), "원단위_정답": v, "상태": "값", "재무_열": col, "재무_코드": s[col.split("_")[0] + "_코드"].iloc[0]})
    return pd.DataFrame(docs), pd.DataFrame(rows)


# ================================================================ B3 표본
def build_b3() -> tuple[pd.DataFrame, list[str]]:
    e = pd.read_csv(EVENTS, dtype=str, encoding="utf-8-sig").fillna("")
    nm = dict(pd.read_csv(NAMES, dtype=str, encoding="utf-8-sig").fillna("")[["code", "name"]].values)
    old = set(pd.read_csv(EP09 / "sample_B.csv", dtype=str, encoding="utf-8-sig")["id"])
    u = e[e["use"] == "1"].copy()
    u["구간"] = u["day"].map(lambda d: "앞" if d <= FRONT_END else ("뒤" if d >= BACK_BGN else "회색"))
    u["종목명"] = u["code"].map(nm).fillna("")
    u["제목_반복수"] = u.groupby("title")["title"].transform("size")
    u["id"] = u["srno"] + "_" + u["code"]
    L = ["## 실험 B 3단계 표본(B3) — 2단계 800건과 겹치지 않게", "",
         f"- events.csv {len(e):,}줄 → use==1 {len(u):,}줄. 정리 규칙은 2단계와 같다(종목명 있음 · 같은 날·종목·제목 되풀이는 첫 건만).", "",
         "| 갈래 | 구간 | use==1 | 종목명 없음 뺌 | 되풀이 뺌 | 2단계 표본 뺌 | 뽑을 수 있는 건 | 표본 | 표본 post5 오름/0/내림 | 표본 post30 오름/0/내림 | 표본 중 목록형 제목(반복 ≥ 10) |",
         "|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|"]
    out = []
    for i, (kind, seg, n) in enumerate(B3_PLAN):
        g = u[(u["kind"] == kind) & (u["구간"] == seg)]
        g1 = g[g["종목명"] != ""]
        g2 = g1.sort_values(["day", "tm", "srno", "code"]).drop_duplicates(["day", "code", "title"], keep="first")
        g3 = g2[~g2["id"].isin(old)]
        s = g3.sample(n, random_state=SEED3 + i).sort_values(["day", "tm", "srno", "code"])
        p5, p30 = pd.to_numeric(s["post5"]), pd.to_numeric(s["post30"])
        L.append(f"| {kind} | {seg} | {len(g):,} | {len(g) - len(g1):,} | {len(g1) - len(g2):,} | {len(g2) - len(g3):,} | {len(g3):,} | {len(s):,} | "
                 f"{(p5 > 0).sum()}/{(p5 == 0).sum()}/{(p5 < 0).sum()} | {(p30 > 0).sum()}/{(p30 == 0).sum()}/{(p30 < 0).sum()} | {int((s['제목_반복수'] >= 10).sum())} |")
        out.append(s)
    b = pd.concat(out)
    assert b["id"].is_unique and not (set(b["id"]) & old)
    # 부분 표본(강제 · 세 급): 일반 기사 앞·뒤에서 각 1,000건
    b["부분"] = 0
    for j, seg in enumerate(("앞", "뒤")):
        idx = b[(b["kind"] == "일반 기사") & (b["구간"] == seg)].sort_values("id").sample(B3_SUB, random_state=SEED3 + 10 + j).index
        b.loc[idx, "부분"] = 1
    L += ["", f"- 부분 표본(B-강제 · B-세 급) = 일반 기사 앞 {B3_SUB:,} · 뒤 {B3_SUB:,}건(시드 {SEED3}+10·+11). 시드 {SEED3}(갈래마다 +0·+1·+2).", ""]
    cols = ["id", "구간", "kind", "day", "tm", "srno", "code", "종목명", "mk", "dorg", "title", "제목_반복수", "pre5", "bar0", "post5", "post30", "부분"]
    return b[cols].rename(columns={"kind": "갈래"}), L


def b3_batches() -> dict[str, list[str]]:
    """부분 표본 2,000건은 저희끼리 100묶음(S001~S100), 나머지 5,000건은 250묶음(R001~R250). 묶음 안 순서까지 고정."""
    b = pd.read_csv(EP09 / "sample_B3.csv", dtype=str, encoding="utf-8-sig").fillna("")
    out = {}
    for tag, flag, seed in (("S", "1", SEED3 + 20), ("R", "0", SEED3 + 21)):
        ids = sorted(b[b["부분"] == flag]["id"])
        random.Random(seed).shuffle(ids)
        for i in range(0, len(ids), B_BATCH):
            out[f"{tag}{i // B_BATCH + 1:03d}"] = ids[i:i + B_BATCH]
    return out


def build():
    T3.mkdir(parents=True, exist_ok=True)
    k = key_a3()
    k.to_csv(T3 / "정답_A3.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"rcept_no": a, "칸": b, "정정후_정답": v, "근거": w} for (a, b), (v, w) in CORRECTION_OVERRIDE.items()]).to_csv(T3 / "정답_정정대조.csv", index=False, encoding="utf-8-sig")
    for task in ("A3", "H1", "H2", "H3"):
        rows = [{"kind": kind, "번호": f"q{i:02d}", **f} for kind, fs in fields_for(task).items() for i, f in enumerate(fs, 1)]
        pd.DataFrame(rows).to_csv(T3 / f"{task}_질문.csv", index=False, encoding="utf-8-sig")
    h2, h3 = key_h2(k), key_h3(k)
    h2.to_csv(T3 / "정답_H2.csv", index=False, encoding="utf-8-sig")
    h3.to_csv(T3 / "정답_H3.csv", index=False, encoding="utf-8-sig")
    h4 = h4_groups()
    h4.to_csv(T3 / "H4_묶음.csv", index=False, encoding="utf-8-sig")
    d5, k5 = key_h5()
    d5.to_csv(T3 / "H5_문서.csv", index=False, encoding="utf-8-sig")
    k5.to_csv(T3 / "정답_H5.csv", index=False, encoding="utf-8-sig")
    b, L = build_b3()
    b.to_csv(EP09 / "sample_B3.csv", index=False, encoding="utf-8-sig")
    bb = b3_batches()
    (T3 / "B3_묶음.json").write_text(json.dumps(bb, ensure_ascii=False, indent=0), encoding="utf-8")
    (T3 / "표본_깔때기_3단계.md").write_text("\n".join(
        ["# 9편 실험 3단계 표본 — 깔때기", "", "`scripts/ep09_tasks3.py build` 가 센 값만 적는다.", ""] + L +
        ["## 어려운 읽기(H1~H5) 문항 수", "",
         f"- A3·H1: 문서 266건 · 값 칸 {int((k['상태'] == '값').sum())} · 빈 칸 {int((k['상태'] == '빈칸').sum())}(정정 대조로 바꾼 칸 {len(CORRECTION_OVERRIDE)})",
         f"- H2: 문서 {h2['rcept_no'].nunique()}건 · 값 칸 {int((h2['상태'] == '값').sum())} · 빈 칸 {int((h2['상태'] == '빈칸').sum())}",
         f"- H3: 문서 {h3['rcept_no'].nunique()}건 · 값 문항 {int((h3['상태'] == '값').sum())} · 빈(입력 칸이 빔) 문항 {int((h3['상태'] == '빈칸').sum())} · 계산 불가로 뺀 문항 {int((h3['상태'] == '해석불가').sum())}",
         f"- H4: 대상 {len(h4)}건 중 쓰는 건 {int((h4['뺀_이유'] == '').sum())}건 · 뺀 이유: {dict(Counter(x.split('(')[0].split(' 1')[0] for x in h4['뺀_이유'] if x))}",
         f"- H5: 문서 {len(d5)}건 · 문항 {len(k5)}", ""]) + "\n", encoding="utf-8")
    print(f"A3 값 {int((k['상태'] == '값').sum())} 빈 {int((k['상태'] == '빈칸').sum())} | H2 값 {int((h2['상태'] == '값').sum())} 빈 {int((h2['상태'] == '빈칸').sum())} | "
          f"H3 {h3['상태'].value_counts().to_dict()} | H4 쓰는 건 {int((h4['뺀_이유'] == '').sum())}/{len(h4)} | H5 문서 {len(d5)} 문항 {len(k5)} | B3 {len(b)} 묶음 {len(bb)}")
    print(h4[h4["뺀_이유"] != ""][["kind", "rcept_no", "뺀_이유"]].to_string())
    print(d5.to_string())


def check():
    k = key_a3()
    assert set(H1_Q) >= set(load_docs()["kind"]), "H1 질문이 없는 종류"
    for kind, fs in fields_for("A3").items():
        if kind in H1_Q:
            assert [f["칸"] for f in fs] == list(H1_Q[kind]), f"H1 칸 순서·이름 불일치: {kind}"
    h2 = pd.read_csv(T3 / "정답_H2.csv", dtype=str, encoding="utf-8-sig").fillna("")
    for r in h2[h2["상태"] == "값"].itertuples(index=False):
        assert abs(Decimal(r.정답) - Decimal(r.정답_반올림전)) <= Decimal("0.005"), r
    print("점검 통과: H1 질문", sum(len(v) for v in H1_Q.values()), "개 · H2 값", int((h2["상태"] == "값").sum()))


if __name__ == "__main__":
    {"build": build, "check": check}[sys.argv[1] if len(sys.argv) > 1 else "build"]()
