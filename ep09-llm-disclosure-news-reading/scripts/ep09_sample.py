# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""9편 실험 1단계 — 시험 표본 추출 + 정답표 (2026-11-16). 파일만 읽는다 — 모델 호출·외부 API 호출 없음.

1·2단계는 시험(파일럿)이다 — 프롬프트와 채점기를 굳히려고 작게 돌렸다. 3단계는 여기서 만든 A 표본(sample_A)을 그대로 쓰고,
Sonnet 의 쉬운 읽기(A3) 답은 2단계 답을 다시 쓴다(ep09_grade3.load_ans). 실험 A(읽기) · 실험 B(맞히기).

실험 A (공시 원문에서 정해진 값 뽑기)
  정답 = data/disclosure/구조화/<엔드포인트>.csv (OpenDART 구조화 서식 19종, 값은 글자 그대로 "1,234,567"·"2025년 01월 02일"·"-")
  입력 = 같은 접수번호의 원문 zip(data/disclosure/원문/<날짜>/<접수번호>.zip, scripts/dart_doc.py read_text)
  표본 = 종류마다 "원문 zip 을 받아 둔 접수번호"에서 20건(모자라면 있는 만큼) — 고정 시드.
  채점 칸 = 종류마다 숫자·날짜·분류 위주 6~10개(FIELDS). 대체로 비는 칸(기타주식 등)을 일부러 넣어
            '정답이 빈 칸에 모델이 값을 채우는 비율(지어내기)'을 잴 수 있게 했다.
  뺀 것  = 접수번호가 겹치는 줄 · 원문 zip 없는 줄 · 고른 칸이 통째로 빈 줄(정답지가 비어 채점할 것이 없음).
실험 B (뉴스 제목으로 방향 판단)
  data/news/analysis_year/events.csv 의 use==1 에서 일반 기사 앞(day ≤ 20260531) 300 · 뒤(day ≥ 20260701) 300,
  시세 중계 뒤 200 — 고정 시드. 종목명은 data/daily/_universe_20261104.csv(code,name) 로 붙인다(새로 받지 않음).
  뺀 것 = 종목명이 표에 없는 줄 · 같은 날 같은 종목 같은 제목이 되풀이된 줄(첫 건만 남김).

출력(data/ep09/):
  sample_A.csv         표본 문서 한 줄씩(종류·접수번호·회사·정정 여부·글자 수·칸 수·빈 칸 수)
  sample_A_정답.csv     (접수번호, 칸) 한 줄씩 — 원값·정규값·상태(값/빈칸/해석불가)·원문확인(찾음/못찾음/…)
  sample_A_칸정의.csv   종류별 채점 칸 — 질문 이름·형·단위·고른 이유·채움 수·원문 일치 수·원문 앞줄 예시
  sample_B.csv         id(srno_code)·구간·갈래·날짜·시각·종목·종목명·제목·제목_반복수·post5·post30
  표본_깔때기.md        모수 → 뺀 수와 이유 → 남은 수 (전부 이 실행에서 센 값)

쓰기(이 폴더에서):
  python -X utf8 scripts/ep09_sample.py            # 전부 다시 만들기(같은 시드 → 같은 표본)
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

from ep09_paths import DATA  # 자료 뿌리(기본 = 이 폴더의 data/ · --data <폴더> 또는 환경 변수 EP09_DATA)
from dart_doc import path_of, read_text  # noqa: E402  (원문 zip → 글, 원본 disclosure/document.py 에서 옮김)

API = DATA / "disclosure" / "구조화"
EVENTS = DATA / "news" / "analysis_year" / "events.csv"
NAMES = DATA / "daily" / "_universe_20261104.csv"
EP09 = DATA / "ep09"
SEED = 20261116
N_A = 20                                  # 종류별 시험 표본
B_PLAN = [("일반 기사", "앞", 300), ("일반 기사", "뒤", 300), ("시세 중계", "뒤", 200)]
FRONT_END, BACK_BGN = "20260531", "20260701"
EMPTY = {"", "-", "－", "−", "–", "해당사항없음", "해당사항 없음", "해당없음", "nan"}

KIND_NAME = {
    "tsstkAqDecsn": "자기주식취득결정", "tsstkDpDecsn": "자기주식처분결정",
    "tsstkAqTrctrCnsDecsn": "자기주식취득신탁계약체결결정", "tsstkAqTrctrCcDecsn": "자기주식취득신탁계약해지결정",
    "piicDecsn": "유상증자결정", "fricDecsn": "무상증자결정", "pifricDecsn": "유무상증자결정", "crDecsn": "감자결정",
    "cvbdIsDecsn": "전환사채권발행결정", "bdwtIsDecsn": "신주인수권부사채권발행결정", "exbdIsDecsn": "교환사채권발행결정",
    "cmpMgDecsn": "회사합병결정", "cmpDvDecsn": "회사분할결정", "bsnInhDecsn": "영업양수결정", "bsnTrfDecsn": "영업양도결정",
    "otcprStkInvscrInhDecsn": "타법인주식및출자증권양수결정", "otcprStkInvscrTrfDecsn": "타법인주식및출자증권양도결정",
    "majorstock": "주식등의대량보유상황보고서", "elestock": "임원ㆍ주요주주특정증권등소유상황보고서",
}

# 고른 이유(짧은 말)
R_AMT, R_QTY, R_DATE, R_RATE = "핵심 금액(큰 수 — 자릿수·단위 환산 오류를 봄)", "핵심 수량", "일정(날짜 형식 정규화)", "비율(소수 — 반올림·자릿수)"
R_EMPTY = "대체로 빈 칸(지어내기 측정)"
R_SIGN = "부호가 있는 값(부호 오류를 봄)"
R_ENUM = "분류(선택지)"
R_CNT = "작은 정수"

# 종류 → [(구조화 열, 질문 이름(서식 표기에 맞춘 것 — 일부는 확인 필요, 보고서 참고), 형, 단위, 고른 이유)]
#   형: num 숫자 · date 날짜 · enum 분류.  단위는 구조화 값의 단위(원문 서식 표기 기준).
FIELDS: dict[str, list[tuple[str, str, str, str, str]]] = {
    "tsstkAqDecsn": [
        ("aqpln_stk_ostk", "취득예정주식(주) 보통주식", "num", "주", R_QTY),
        ("aqpln_stk_estk", "취득예정주식(주) 기타주식", "num", "주", R_EMPTY),
        ("aqpln_prc_ostk", "취득예정금액(원) 보통주식", "num", "원", R_AMT),
        ("aqpln_prc_estk", "취득예정금액(원) 기타주식", "num", "원", R_EMPTY),
        ("aqexpd_bgd", "취득예상기간 시작일", "date", "날짜", R_DATE),
        ("aqexpd_edd", "취득예상기간 종료일", "date", "날짜", R_DATE),
        ("aq_wtn_div_ostk_rt", "취득 전 자기주식 보유현황 배당가능이익범위 내 취득 보통주식 비율(%)", "num", "%", R_RATE),
        ("aq_dd", "취득결정일", "date", "날짜", R_DATE),
        ("d1_prodlm_ostk", "1일 매수 주문수량 한도 보통주식", "num", "주", R_QTY),
    ],
    "tsstkDpDecsn": [
        ("dppln_stk_ostk", "처분예정주식(주) 보통주식", "num", "주", R_QTY),
        ("dppln_stk_estk", "처분예정주식(주) 기타주식", "num", "주", R_EMPTY),
        ("dpstk_prc_ostk", "처분 대상 주식가격(원) 보통주식", "num", "원", "주당 가격(총액과 헷갈리는지 봄)"),
        ("dppln_prc_ostk", "처분예정금액(원) 보통주식", "num", "원", R_AMT),
        ("dpprpd_bgd", "처분예정기간 시작일", "date", "날짜", R_DATE),
        ("dpprpd_edd", "처분예정기간 종료일", "date", "날짜", R_DATE),
        ("dp_m_mkt", "처분방법 시장을 통한 매도(주)", "num", "주", R_EMPTY),
        ("dp_m_ovtm", "처분방법 시간외대량매매(주)", "num", "주", R_EMPTY),
        ("dp_m_otc", "처분방법 장외처분(주)", "num", "주", R_EMPTY),
        ("dp_dd", "처분결정일", "date", "날짜", R_DATE),
    ],
    "tsstkAqTrctrCnsDecsn": [
        ("ctr_prc", "계약금액(원)", "num", "원", R_AMT),
        ("ctr_pd_bgd", "계약기간 시작일", "date", "날짜", R_DATE),
        ("ctr_pd_edd", "계약기간 종료일", "date", "날짜", R_DATE),
        ("ctr_cns_prd", "계약체결 예정일자", "date", "날짜", R_DATE),
        ("bddd", "이사회결의일(결정일)", "date", "날짜", R_DATE),
        ("aq_wtn_div_ostk", "계약 전 자기주식 보유현황 배당가능이익범위 내 취득(주) 보통주식", "num", "주", R_QTY),
        ("aq_wtn_div_ostk_rt", "계약 전 자기주식 보유현황 배당가능이익범위 내 취득 보통주식 비율(%)", "num", "%", R_RATE),
        ("eaq_ostk", "계약 전 자기주식 보유현황 기타취득(주) 보통주식", "num", "주", R_EMPTY),
        ("od_a_at_t", "사외이사 참석(명)", "num", "명", R_CNT),
    ],
    "tsstkAqTrctrCcDecsn": [
        ("ctr_prc_bfcc", "계약금액(원) 해지 전", "num", "원", R_AMT),
        ("ctr_prc_atcc", "계약금액(원) 해지 후", "num", "원", R_EMPTY),
        ("ctr_pd_bfcc_bgd", "해지 전 계약기간 시작일", "date", "날짜", R_DATE),
        ("ctr_pd_bfcc_edd", "해지 전 계약기간 종료일", "date", "날짜", R_DATE),
        ("cc_prd", "해지예정일자", "date", "날짜", R_DATE),
        ("bddd", "이사회결의일(결정일)", "date", "날짜", R_DATE + " · 빈 칸 섞임"),
        ("aq_wtn_div_ostk", "해지 전 자기주식 보유현황 배당가능이익범위 내 취득(주) 보통주식", "num", "주", R_QTY),
        ("aq_wtn_div_ostk_rt", "해지 전 자기주식 보유현황 배당가능이익범위 내 취득 보통주식 비율(%)", "num", "%", R_RATE),
    ],
    "piicDecsn": [
        ("nstk_ostk_cnt", "신주의 종류와 수 보통주식(주)", "num", "주", R_QTY),
        ("nstk_estk_cnt", "신주의 종류와 수 기타주식(주)", "num", "주", R_EMPTY),
        ("fv_ps", "1주당 액면가액(원)", "num", "원", "작은 금액(발행가와 헷갈리는지 봄)"),
        ("bfic_tisstk_ostk", "증자전 발행주식총수(주) 보통주식", "num", "주", R_QTY),
        ("fdpp_fclt", "자금조달의 목적 시설자금(원)", "num", "원", R_EMPTY),
        ("fdpp_op", "자금조달의 목적 운영자금(원)", "num", "원", R_AMT),
        ("fdpp_dtrp", "자금조달의 목적 채무상환자금(원)", "num", "원", R_EMPTY),
        ("fdpp_ocsa", "자금조달의 목적 타법인 증권 취득자금(원)", "num", "원", R_EMPTY),
        ("ic_mthn", "증자방식", "enum", "분류", R_ENUM),
    ],
    "fricDecsn": [
        ("nstk_ostk_cnt", "신주의 종류와 수 보통주식(주)", "num", "주", R_QTY),
        ("nstk_estk_cnt", "신주의 종류와 수 기타주식(주)", "num", "주", R_EMPTY),
        ("fv_ps", "1주당 액면가액(원)", "num", "원", "작은 금액"),
        ("bfic_tisstk_ostk", "증자전 발행주식총수 보통주식(주)", "num", "주", R_QTY),
        ("nstk_asstd", "신주배정기준일", "date", "날짜", R_DATE),
        ("nstk_ascnt_ps_ostk", "1주당 신주배정 주식수 보통주식(주)", "num", "주", R_RATE),
        ("nstk_dividrk", "신주의 배당기산일", "date", "날짜", R_DATE),
        ("nstk_dlprd", "신주권교부예정일", "date", "날짜", R_EMPTY + " — 원문 있는 49건 모두 빈 칸"),
        ("nstk_lstprd", "신주의 상장 예정일", "date", "날짜", R_DATE),
        ("bddd", "이사회결의일(결정일)", "date", "날짜", R_DATE),
    ],
    "pifricDecsn": [
        ("piic_nstk_ostk_cnt", "유상증자 신주의 종류와 수 보통주식(주)", "num", "주", R_QTY),
        ("piic_fv_ps", "유상증자 1주당 액면가액(원)", "num", "원", "작은 금액"),
        ("piic_bfic_tisstk_ostk", "유상증자 증자전 발행주식총수 보통주식(주)", "num", "주", R_QTY),
        ("piic_fdpp_fclt", "유상증자 자금조달의 목적 시설자금(원)", "num", "원", R_AMT + " · 빈 칸 섞임"),
        ("piic_fdpp_op", "유상증자 자금조달의 목적 운영자금(원)", "num", "원", R_AMT),
        ("piic_fdpp_dtrp", "유상증자 자금조달의 목적 채무상환자금(원)", "num", "원", R_AMT + " · 빈 칸 섞임"),
        ("fric_nstk_ostk_cnt", "무상증자 신주의 종류와 수 보통주식(주)", "num", "주", R_QTY + "(유상 쪽 수와 헷갈리는지 봄)"),
        ("fric_nstk_estk_cnt", "무상증자 신주의 종류와 수 기타주식(주)", "num", "주", R_EMPTY),
        ("fric_nstk_asstd", "무상증자 신주배정기준일", "date", "날짜", R_DATE),
        ("fric_nstk_ascnt_ps_ostk", "무상증자 1주당 신주배정 주식수 보통주식(주)", "num", "주", R_RATE),
    ],
    "crDecsn": [
        ("fv_ps", "1주당 액면가액(원)", "num", "원", "작은 금액"),
        ("crstk_ostk_cnt", "감자주식의 종류와 수 보통주식(주)", "num", "주", R_QTY),
        ("crstk_estk_cnt", "감자주식의 종류와 수 기타주식(주)", "num", "주", R_EMPTY),
        ("bfcr_cpt", "감자전 자본금(원)", "num", "원", R_AMT),
        ("atcr_cpt", "감자후 자본금(원)", "num", "원", R_AMT + "(전·후 헷갈리는지 봄)"),
        ("bfcr_tisstk_ostk", "감자전 발행주식수 보통주식(주)", "num", "주", R_QTY),
        ("atcr_tisstk_ostk", "감자후 발행주식수 보통주식(주)", "num", "주", R_QTY),
        ("cr_rt_ostk", "감자비율 보통주식(%)", "num", "%", R_RATE),
        ("cr_std", "감자기준일", "date", "날짜", R_DATE),
        ("crsc_gmtsck_prd", "주주총회 예정일", "date", "날짜", R_DATE),
    ],
    "cvbdIsDecsn": [
        ("bd_tm", "사채의 종류 회차", "num", "회차", R_CNT),
        ("bd_fta", "사채의 권면(전자등록)총액(원)", "num", "원", R_AMT),
        ("bd_intr_ex", "사채의 이율 표면이자율(%)", "num", "%", R_RATE),
        ("bd_intr_sf", "사채의 이율 만기이자율(%)", "num", "%", R_RATE + "(표면·만기 헷갈리는지 봄)"),
        ("bd_mtd", "사채만기일", "date", "날짜", R_DATE),
        ("cv_prc", "전환가액(원/주)", "num", "원", "주당 가격"),
        ("cvisstk_cnt", "전환에 따라 발행할 주식 주식수", "num", "주", R_QTY),
        ("cvisstk_tisstk_vs", "전환에 따라 발행할 주식 주식총수 대비 비율(%)", "num", "%", R_RATE),
        ("act_mktprcfl_cvprc_lwtrsprc", "시가하락에 따른 전환가액 조정 최저 조정가액(원)", "num", "원", R_EMPTY + " — 3할쯤 빈 칸"),
        ("pymd", "납입일", "date", "날짜", R_DATE),
    ],
    "bdwtIsDecsn": [
        ("bd_tm", "사채의 종류 회차", "num", "회차", R_CNT),
        ("bd_fta", "사채의 권면(전자등록)총액(원)", "num", "원", R_AMT),
        ("bd_intr_ex", "사채의 이율 표면이자율(%)", "num", "%", R_RATE),
        ("bd_intr_sf", "사채의 이율 만기이자율(%)", "num", "%", R_RATE),
        ("bd_mtd", "사채만기일", "date", "날짜", R_DATE),
        ("ex_prc", "신주인수권 행사가액(원/주)", "num", "원", "주당 가격"),
        ("nstk_isstk_cnt", "신주인수권 행사에 따라 발행할 주식 주식수", "num", "주", R_QTY),
        ("nstk_isstk_tisstk_vs", "신주인수권 행사에 따라 발행할 주식 주식총수 대비 비율(%)", "num", "%", R_RATE),
        ("act_mktprcfl_cvprc_lwtrsprc", "시가하락에 따른 행사가액 조정 최저 조정가액(원)", "num", "원", R_EMPTY),
        ("pymd", "납입일", "date", "날짜", R_DATE),
    ],
    "exbdIsDecsn": [
        ("bd_tm", "사채의 종류 회차", "num", "회차", R_CNT),
        ("bd_fta", "사채의 권면(전자등록)총액(원)", "num", "원", R_AMT),
        ("bd_intr_ex", "사채의 이율 표면이자율(%)", "num", "%", R_RATE),
        ("bd_intr_sf", "사채의 이율 만기이자율(%)", "num", "%", R_RATE),
        ("bd_mtd", "사채만기일", "date", "날짜", R_DATE),
        ("ex_prc", "교환가액(원/주)", "num", "원", "주당 가격"),
        ("extg_stkcnt", "교환대상 주식수", "num", "주", R_QTY),
        ("extg_tisstk_vs", "교환대상 주식총수 대비 비율(%)", "num", "%", R_RATE),
        ("fdpp_op", "자금조달의 목적 운영자금(원)", "num", "원", R_EMPTY + " — 절반쯤 빈 칸"),
        ("pymd", "납입일", "date", "날짜", R_DATE),
    ],
    "cmpMgDecsn": [
        ("bddd", "이사회결의일(결정일)", "date", "날짜", R_DATE),
        ("mgnstk_ostk_cnt", "합병신주의 종류와 수 보통주식(주)", "num", "주", R_EMPTY + " — 무증자합병이면 빈 칸"),
        ("rbsnfdtl_tast", "합병상대회사 최근 사업연도 재무내용 자산총계(원)", "num", "원", R_AMT),
        ("rbsnfdtl_tdbt", "합병상대회사 최근 사업연도 재무내용 부채총계(원)", "num", "원", R_AMT),
        ("rbsnfdtl_teqt", "합병상대회사 최근 사업연도 재무내용 자본총계(원)", "num", "원", R_AMT),
        ("rbsnfdtl_cpt", "합병상대회사 최근 사업연도 재무내용 자본금(원)", "num", "원", R_AMT + "(자본총계와 헷갈리는지 봄)"),
        ("rbsnfdtl_sl", "합병상대회사 최근 사업연도 재무내용 매출액(원)", "num", "원", R_AMT),
        ("rbsnfdtl_nic", "합병상대회사 최근 사업연도 재무내용 당기순이익(원)", "num", "원", R_SIGN),
        ("mgsc_mgctrd", "합병일정 합병계약일", "date", "날짜", R_DATE),
        ("mgsc_mgdt", "합병일정 합병기일", "date", "날짜", R_DATE),
    ],
    "cmpDvDecsn": [
        ("bddd", "이사회결의일(결정일)", "date", "날짜", R_DATE),
        ("atdvfdtl_tast", "분할 후 존속회사 분할후 재무내용 자산총계(원)", "num", "원", R_AMT),
        ("atdvfdtl_teqt", "분할 후 존속회사 분할후 재무내용 자본총계(원)", "num", "원", R_AMT),
        ("atdvfdtl_cpt", "분할 후 존속회사 분할후 재무내용 자본금(원)", "num", "원", R_AMT),
        ("ffdtl_tast", "분할설립회사 설립시 재무내용 자산총계(원)", "num", "원", R_AMT + "(존속·설립 헷갈리는지 봄)"),
        ("ffdtl_tdbt", "분할설립회사 설립시 재무내용 부채총계(원)", "num", "원", R_AMT),
        ("ffdtl_teqt", "분할설립회사 설립시 재무내용 자본총계(원)", "num", "원", R_AMT),
        ("ffdtl_cpt", "분할설립회사 설립시 재무내용 자본금(원)", "num", "원", R_AMT),
        ("gmtsck_prd", "주주총회 예정일", "date", "날짜", R_DATE),
        ("dvdt", "분할기일", "date", "날짜", R_DATE),
    ],
    "bsnInhDecsn": [
        ("bddd", "이사회결의일(결정일)", "date", "날짜", R_DATE),
        ("inh_prc", "양수가액(원)", "num", "원", R_AMT),
        ("ast_inh_bsn", "재무내용 자산액 양수대상 영업부문(원)", "num", "원", R_AMT),
        ("ast_cmp_all", "재무내용 자산액 당사전체(원)", "num", "원", R_AMT),
        ("ast_rt", "재무내용 자산액 비중(%)", "num", "%", R_RATE),
        ("sl_inh_bsn", "재무내용 매출액 양수대상 영업부문(원)", "num", "원", R_AMT),
        ("sl_cmp_all", "재무내용 매출액 당사전체(원)", "num", "원", R_AMT),
        ("sl_rt", "재무내용 매출액 비중(%)", "num", "%", R_RATE),
        ("inh_prd_ctr_cnsd", "양수예정일자 계약체결일", "date", "날짜", R_DATE),
        ("inh_prd_inh_std", "양수예정일자 양수기준일", "date", "날짜", R_DATE),
    ],
    "bsnTrfDecsn": [
        ("bddd", "이사회결의일(결정일)", "date", "날짜", R_DATE),
        ("trf_prc", "양도가액(원)", "num", "원", R_AMT),
        ("ast_trf_bsn", "재무내용 자산액 양도대상 영업부문(원)", "num", "원", R_AMT),
        ("ast_cmp_all", "재무내용 자산액 당사전체(원)", "num", "원", R_AMT),
        ("ast_rt", "재무내용 자산액 비중(%)", "num", "%", R_RATE),
        ("sl_trf_bsn", "재무내용 매출액 양도대상 영업부문(원)", "num", "원", R_AMT),
        ("sl_cmp_all", "재무내용 매출액 당사전체(원)", "num", "원", R_AMT),
        ("sl_rt", "재무내용 매출액 비중(%)", "num", "%", R_RATE),
        ("trf_prd_ctr_cnsd", "양도예정일자 계약체결일", "date", "날짜", R_DATE),
        ("trf_prd_trf_std", "양도예정일자 양도기준일", "date", "날짜", R_DATE),
    ],
    "otcprStkInvscrInhDecsn": [
        ("bddd", "이사회결의일(결정일)", "date", "날짜", R_DATE),
        ("inhdtl_stkcnt", "양수내역 양수주식수(주)", "num", "주", R_QTY),
        ("inhdtl_inhprc", "양수내역 양수금액(원)", "num", "원", R_AMT),
        ("inhdtl_tast", "양수내역 총자산(원)", "num", "원", R_AMT),
        ("inhdtl_tast_vs", "양수내역 총자산대비(%)", "num", "%", R_RATE),
        ("inhdtl_ecpt", "양수내역 자기자본(원)", "num", "원", R_AMT),
        ("inhdtl_ecpt_vs", "양수내역 자기자본대비(%)", "num", "%", R_RATE),
        ("atinh_owstkcnt", "양수후 소유주식수 및 지분비율 소유주식수(주)", "num", "주", R_QTY),
        ("atinh_eqrt", "양수후 소유주식수 및 지분비율 지분비율(%)", "num", "%", R_RATE),
        ("inh_prd", "양수예정일자", "date", "날짜", R_DATE),
    ],
    "otcprStkInvscrTrfDecsn": [
        ("bddd", "이사회결의일(결정일)", "date", "날짜", R_DATE),
        ("trfdtl_stkcnt", "양도내역 양도주식수(주)", "num", "주", R_QTY),
        ("trfdtl_trfprc", "양도내역 양도금액(원)", "num", "원", R_AMT),
        ("trfdtl_tast", "양도내역 총자산(원)", "num", "원", R_AMT),
        ("trfdtl_tast_vs", "양도내역 총자산대비(%)", "num", "%", R_RATE),
        ("trfdtl_ecpt", "양도내역 자기자본(원)", "num", "원", R_AMT),
        ("trfdtl_ecpt_vs", "양도내역 자기자본대비(%)", "num", "%", R_RATE),
        ("attrf_owstkcnt", "양도후 소유주식수 및 지분비율 소유주식수(주)", "num", "주", R_QTY + " · 빈 칸 섞임"),
        ("attrf_eqrt", "양도후 소유주식수 및 지분비율 지분비율(%)", "num", "%", R_RATE + " · 빈 칸 섞임"),
        ("trf_prd", "양도예정일자", "date", "날짜", R_DATE),
    ],
    "majorstock": [
        ("report_tp", "보고구분(일반/약식)", "enum", "분류", R_ENUM),
        ("stkqy", "보유주식등의 수(이번 보고서)", "num", "주", R_QTY),
        ("stkqy_irds", "보유주식등의 증감", "num", "주", R_SIGN),
        ("stkrt", "보유비율(%) (이번 보고서)", "num", "%", R_RATE),
        ("stkrt_irds", "보유비율 증감(%p)", "num", "%p", R_SIGN),
        ("ctr_stkqy", "주요체결 주식등의 수", "num", "주", R_EMPTY),
        ("ctr_stkrt", "주요체결 보유비율(%)", "num", "%", R_EMPTY),
    ],
    "elestock": [
        ("isu_exctv_rgist_at", "발행 회사 관계 임원(등기여부)", "enum", "분류", R_ENUM + " · 빈 칸 섞임"),
        ("isu_main_shrholdr", "발행 회사 관계 주요 주주", "enum", "분류", R_EMPTY),
        ("sp_stock_lmp_cnt", "특정 증권 등 소유 수(이번 보고서)", "num", "주", R_QTY),
        ("sp_stock_lmp_irds_cnt", "특정 증권 등 소유 증감 수", "num", "주", R_SIGN),
        ("sp_stock_lmp_rate", "특정 증권 등 소유 비율(%)", "num", "%", R_RATE),
        ("sp_stock_lmp_irds_rate", "특정 증권 등 소유 증감 비율(%p)", "num", "%p", R_SIGN),
    ],
}
ENUM_OPTS = {
    ("piicDecsn", "ic_mthn"): ["제3자배정증자", "주주배정증자", "주주배정후 실권주 일반공모", "일반공모증자", "주주우선공모증자"],
    ("majorstock", "report_tp"): ["일반", "약식"],
    ("elestock", "isu_exctv_rgist_at"): ["등기임원", "비등기임원"],
    ("elestock", "isu_main_shrholdr"): ["10%이상주주", "사실상지배주주"],
}

NUM_RE = re.compile(r"^[-+△▲]?\(?[\d,]+(\.\d+)?\)?%?$")
DATE_RE = re.compile(r"^(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일$|^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$|^(\d{4})(\d{2})(\d{2})$")


def norm_truth(raw: str, tp: str) -> tuple[str, str]:
    """구조화 원값 → (정규값, 상태). 상태: 값 · 빈칸 · 해석불가(여러 값·범위·글 — 채점에서 뺀다)."""
    s = (raw or "").strip()
    if s in EMPTY:
        return "", "빈칸"
    if tp == "num":
        t = s.replace(" ", "")
        if not NUM_RE.match(t):
            return "", "해석불가"
        neg = t[0] in "-△▲" or (t.startswith("(") and t.endswith(")"))
        t = t.strip("-+△▲()%").replace(",", "")
        if not t or t == ".":
            return "", "해석불가"
        if "." in t:
            t = t.rstrip("0").rstrip(".") or "0"
        t = t.lstrip("0") or "0"
        if t.startswith("."):
            t = "0" + t
        return ("-" + t if neg and t != "0" else t), "값"
    if tp == "date":
        m = DATE_RE.match(s)
        if not m:
            return "", "해석불가"
        g = [x for x in m.groups() if x]
        y, mo, d = int(g[0]), int(g[1]), int(g[2])
        if not (1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
            return "", "해석불가"
        return f"{y:04d}{mo:02d}{d:02d}", "값"
    return re.sub(r"\s+", " ", s), "값"                      # enum: 글자 그대로(공백만 정리)


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def in_text(raw: str, tp: str, text_sq: str) -> str:
    """정답 원값이 원문 글에 글자 그대로 있는지(공백 무시). 짧은 값(3자 이하)은 우연 일치라 판단하지 않는다."""
    r = squash(raw)
    if len(r) <= 3:
        return "짧아서 판단 안 함"
    if r in text_sq:
        return "찾음"
    if tp == "num" and r.replace(",", "") in text_sq.replace(",", ""):
        return "찾음"
    if tp == "date":                                          # 원문은 2026.05.19 처럼 다른 표기일 수 있다
        v, st = norm_truth(raw, "date")
        if st == "값":
            y, m, d = v[:4], int(v[4:6]), int(v[6:])
            for sep in (".", "-", "/"):
                if f"{y}{sep}{m:02d}{sep}{d:02d}" in text_sq or f"{y}{sep}{m}{sep}{d}" in text_sq:
                    return "찾음(표기 다름)"
            if f"{y}년{m}월{d}일" in text_sq:
                return "찾음(표기 다름)"
    return "못찾음"


def label_before(raw: str, lines: list[str]) -> str:
    """원문에서 그 값이 한 줄로 나오는 첫 자리의 바로 앞 두 줄(서식 칸 이름 확인용)."""
    r = squash(raw)
    for i, ln in enumerate(lines):
        if squash(ln) == r and i >= 1:
            return " / ".join(x[:30] for x in lines[max(0, i - 2):i])
    return ""


# ================================================================ 실험 A
def build_a(funnel: list[str]):
    doc_rows, ans_rows, def_rows = [], [], []
    funnel += ["## 실험 A — 공시 원문에서 값 뽑기 (종류별 20건 목표)", "",
               "| 종류 | 구조화 줄 | 접수번호 겹침 뺌 | 원문 zip 없음 뺌 | 고른 칸 통째로 빈 줄 뺌 | 뽑을 수 있는 건 | 표본 | 표본 중 정정 공시 | 채점 칸(값) | 빈 칸 | 빈 칸 있는 문서 | 해석불가 칸 |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    tot = Counter()
    for ep, fields in FIELDS.items():
        d = pd.read_csv(API / f"{ep}.csv", dtype=str, encoding="utf-8-sig").fillna("")
        n0 = len(d)
        d1 = d.drop_duplicates("rcept_no", keep=False)
        have = d1[d1["rcept_no"].map(lambda r: path_of(r).exists())]
        cols = [c for c, *_ in fields]
        tps = {c: tp for c, _, tp, _, _ in fields}
        allempty = have[cols].apply(lambda r: all(norm_truth(r[c], tps[c])[1] != "값" for c in cols), axis=1) if len(have) else pd.Series([], dtype=bool)
        pool = have[~allempty].sort_values("rcept_no")
        smp = pool.sample(min(N_A, len(pool)), random_state=SEED).sort_values("rcept_no") if len(pool) else pool
        cnt = Counter()
        found = Counter()
        ex_label: dict[str, str] = {}
        for r in smp.itertuples(index=False):
            row = r._asdict()
            text = read_text(row["rcept_no"])
            lines = text.splitlines()
            sq = squash(text)
            is_corr = "정정신고" in squash("".join(lines[:12]))
            st = Counter()
            for c, label, tp, unit, _ in fields:
                val, status = norm_truth(row[c], tp)
                chk = in_text(row[c], tp, sq) if status == "값" else "-"
                st[status] += 1
                cnt[(c, status)] += 1
                found[(c, chk)] += 1
                if status == "값" and c not in ex_label:
                    lb = label_before(row[c], lines)
                    if lb:
                        ex_label[c] = lb
                ans_rows.append({"kind": ep, "rcept_no": row["rcept_no"], "칸": c, "질문이름": label, "형": tp, "단위": unit,
                                 "원값": row[c].strip(), "정답": val, "상태": status, "원문확인": chk})
            doc_rows.append({"kind": ep, "종류": KIND_NAME[ep], "rcept_no": row["rcept_no"], "corp_name": row.get("corp_name", ""),
                             "접수일": row["rcept_no"][:8], "정정": int(is_corr), "원문_글자수": len(text),
                             "칸_값": st["값"], "칸_빈칸": st["빈칸"], "칸_해석불가": st["해석불가"]})
        mine = [x for x in doc_rows if x["kind"] == ep]
        for c, label, tp, unit, why in fields:
            fill_pop = int((have[c].map(lambda v: norm_truth(v, tp)[1]) == "값").sum()) if len(have) else 0
            def_rows.append({"kind": ep, "종류": KIND_NAME[ep], "칸": c, "질문이름": label, "형": tp, "단위": unit,
                             "선택지": " | ".join(ENUM_OPTS.get((ep, c), [])), "고른_이유": why,
                             "원문있는줄": len(have), "원문있는줄_채움": fill_pop,
                             "표본_값": cnt[(c, "값")], "표본_빈칸": cnt[(c, "빈칸")], "표본_해석불가": cnt[(c, "해석불가")],
                             "표본_원문에서_찾음": found[(c, "찾음")], "표본_원문에서_찾음_표기다름": found[(c, "찾음(표기 다름)")],
                             "표본_원문에서_못찾음": found[(c, "못찾음")],
                             "표본_짧아서_판단안함": found[(c, "짧아서 판단 안 함")], "원문_앞줄_예시": ex_label.get(c, "")})
        row = [KIND_NAME[ep], n0, n0 - len(d1), len(d1) - len(have), int(allempty.sum()) if len(have) else 0, len(pool), len(smp),
               sum(x["정정"] for x in mine), sum(x["칸_값"] for x in mine), sum(x["칸_빈칸"] for x in mine),
               sum(1 for x in mine if x["칸_빈칸"] > 0), sum(x["칸_해석불가"] for x in mine)]
        for k, v in zip(["줄", "겹침", "원문없음", "통째빈", "풀", "표본", "정정", "값", "빈칸", "빈칸문서", "해석불가"], row[1:]):
            tot[k] += v
        funnel.append("| " + " | ".join(f"{x:,}" if isinstance(x, int) else str(x) for x in row) + " |")
    funnel.append("| **합계** | " + " | ".join(f"{tot[k]:,}" for k in ["줄", "겹침", "원문없음", "통째빈", "풀", "표본", "정정", "값", "빈칸", "빈칸문서", "해석불가"]) + " |")
    funnel += ["",
               "- 구조화 줄 = `data/disclosure/구조화/<엔드포인트>.csv` 의 줄 수(2022-10-20~ 4년치, 회사별 최신본 한 줄).",
               "- 원문 zip 없음 = `data/disclosure/원문/<날짜>/<접수번호>.zip` 이 없는 줄(받아 두지 않은 공시). 새로 받지 않는다.",
               "- 고른 칸 통째로 빈 줄 = 채점 칸이 모두 빈칸·해석불가인 줄(정답지가 비어 채점할 값이 없음).",
               "- 빈 칸 = 구조화 값이 '-'·빈 글자·'해당사항없음' 인 칸. 지어내기 측정의 분모.",
               "- 해석불가 칸 = 값이 여러 개·범위·글이라 숫자/날짜 하나로 못 바꾼 칸 — 채점에서 뺀다.",
               f"- 표본 수 20 에 못 미친 종류 = 원문이 모자란 종류. 시드 {SEED}.", ""]
    return pd.DataFrame(doc_rows), pd.DataFrame(ans_rows), pd.DataFrame(def_rows)


# ================================================================ 실험 B
def build_b(funnel: list[str]) -> pd.DataFrame:
    e = pd.read_csv(EVENTS, dtype=str, encoding="utf-8-sig").fillna("")
    names = pd.read_csv(NAMES, dtype=str, encoding="utf-8-sig").fillna("")
    nm = dict(zip(names["code"], names["name"]))
    u = e[e["use"] == "1"].copy()
    u["구간"] = u["day"].map(lambda d: "앞" if d <= FRONT_END else ("뒤" if d >= BACK_BGN else "회색"))
    u["종목명"] = u["code"].map(nm).fillna("")
    u["제목_반복수"] = u.groupby("title")["title"].transform("size")       # use==1 전체에서 같은 제목 줄 수(틀 제목 가려내기용)
    funnel += ["## 실험 B — 뉴스 제목으로 방향 판단", "",
               f"- events.csv 전체 {len(e):,}줄 → use==1(주 표본) {len(u):,}줄 (use==0 {len(e) - len(u):,}줄은 창 밖·봉 없음 등으로 이미 빠져 있음).",
               f"- 종목 이름표 `data/daily/_universe_20261104.csv` {len(names):,}종목(2026-11-04 기준 상장 종목). "
               f"use==1 의 종목 {u['code'].nunique():,}개 가운데 이름 없음 {(~u['code'].drop_duplicates().isin(nm)).sum():,}개.",
               f"- 구간: 앞 = day ≤ {FRONT_END} · 회색 = 2026-06(뺌) · 뒤 = day ≥ {BACK_BGN}.", "",
               "| 갈래 | 구간 | use==1 | 종목명 없음 뺌 | 같은 날·종목·제목 되풀이 뺌 | 뽑을 수 있는 건 | 표본 | 표본 post5 오름/0/내림 | 표본 post30 오름/0/내림 | 표본 중 틀 제목(반복 ≥ 10) |",
               "|---|---|---:|---:|---:|---:|---:|---|---|---:|"]
    out = []
    for i, (kind, seg, n) in enumerate(B_PLAN):
        g = u[(u["kind"] == kind) & (u["구간"] == seg)]
        g1 = g[g["종목명"] != ""]
        g2 = g1.sort_values(["day", "tm", "srno", "code"]).drop_duplicates(["day", "code", "title"], keep="first")
        s = g2.sample(min(n, len(g2)), random_state=SEED + i).sort_values(["day", "tm", "srno", "code"])
        p5, p30 = pd.to_numeric(s["post5"]), pd.to_numeric(s["post30"])
        funnel.append(f"| {kind} | {seg} | {len(g):,} | {len(g) - len(g1):,} | {len(g1) - len(g2):,} | {len(g2):,} | {len(s):,} | "
                      f"{(p5 > 0).sum()}/{(p5 == 0).sum()}/{(p5 < 0).sum()} | {(p30 > 0).sum()}/{(p30 == 0).sum()}/{(p30 < 0).sum()} | {int((s['제목_반복수'] >= 10).sum())} |")
        out.append(s)
    b = pd.concat(out)
    b.insert(0, "id", b["srno"] + "_" + b["code"])
    assert b["id"].is_unique, "id(srno_code) 가 겹침"
    gray = u[u["구간"] == "회색"]
    funnel += ["",
               f"- 쓰지 않은 것: 회색 구간 {len(gray):,}줄 · 공시 피드 {int((u['kind'] == '공시 피드').sum()):,}줄 · 일반 기사·시세 중계의 나머지 구간(시세 중계 앞 {int(((u['kind'] == '시세 중계') & (u['구간'] == '앞')).sum()):,}줄).",
               "- 같은 날·종목·제목 되풀이 = 같은 기사가 다시 전송된 줄. 시각이 가장 이른 첫 건만 남겼다(뒤 건은 이미 나온 소식).",
               "- post5·post30 = 기사 분 봉을 뺀 뒤 5분·30분 수익률(events.csv 에 계산돼 있던 값 그대로). 0 = 변화 없음(채점기에서 따로 셈).",
               "- 틀 제목 = use==1 전체에서 글자가 똑같은 제목이 10줄 이상인 것(예: 시장별 상승률 상위 종목을 늘어놓는 목록 기사). events.csv 의 갈래는 고치지 않았고, "
               "sample_B.csv 의 `제목_반복수` 열로 표시만 했다 — 채점기가 '틀 제목 뺌' 줄을 따로 낸다.",
               f"- 시드 {SEED}(갈래마다 +0·+1·+2).", ""]
    cols = ["id", "구간", "kind", "day", "tm", "srno", "code", "종목명", "mk", "dorg", "title", "제목_반복수", "pre5", "bar0", "post5", "post30"]
    return b[cols].rename(columns={"kind": "갈래"})


def main():
    EP09.mkdir(parents=True, exist_ok=True)
    funnel = [f"# 9편 실험 시험 표본 — 깔때기 ({datetime.now():%Y-%m-%d %H:%M} 생성)", "",
              "`scripts/ep09_sample.py` 가 이 실행에서 센 값만 적는다(추정 없음). 다시 돌리면 같은 시드로 같은 표본이 나온다.", ""]
    docs, ans, defs = build_a(funnel)
    b = build_b(funnel)
    docs.to_csv(EP09 / "sample_A.csv", index=False, encoding="utf-8-sig")
    ans.to_csv(EP09 / "sample_A_정답.csv", index=False, encoding="utf-8-sig")
    defs.to_csv(EP09 / "sample_A_칸정의.csv", index=False, encoding="utf-8-sig")
    b.to_csv(EP09 / "sample_B.csv", index=False, encoding="utf-8-sig")
    (EP09 / "표본_깔때기.md").write_text("\n".join(funnel) + "\n", encoding="utf-8")
    print(f"A: 문서 {len(docs)}건 · 칸 {len(ans)}개(값 {int((ans['상태'] == '값').sum())} · 빈칸 {int((ans['상태'] == '빈칸').sum())} · 해석불가 {int((ans['상태'] == '해석불가').sum())})")
    print(docs.groupby("kind").size().to_string())
    print(f"B: {len(b)}건", b.groupby(["갈래", "구간"]).size().to_dict())
    print("저장:", EP09)


if __name__ == "__main__":
    main()
