# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""strategy/ — 트레이딩뷰 Pine 전략을 파이썬으로 옮겨 꽂는 틀 (김쿤 | AI 자동매매 6편).

- base.py        전략 공통 형식(Strategy 클래스·입력 봉 검사·신호 열)
- indicators.py  Pine ta.* 대응 함수(공식 문서 정의대로)
- ported/        AI(또는 사람)가 전략마다 한 번 옮긴 결과
- data.py        봉 로더(한투 일봉·당일 분봉·과거 분봉, data/bars/ 캐시, CSV 파일 읽기)
- backtest.py    트레이딩뷰 Strategy Tester 기본 규칙에 맞춘 단순 백테스트
- validate.py    옮긴 전략 검증기(규격·금지·견본 실행·트레이딩뷰 거래 목록 대조)
- live.py        실시간 실행기(기본 dry-run, 모의 주문은 --paper-order 일 때만)
자세한 설명은 strategy/README.md.
"""
