# sample_data/ — 네트워크 없이 돌려 보는 가짜 견본

**여기 있는 값은 모두 가짜다.** 실제 종목·실제 시세·실제 트레이딩뷰 결과가 아니다.

| 파일 | 무엇 | 만든 법 |
|---|---|---|
| `fake_daily_bars.csv` | 가짜 일봉 400개(열 `time, open, high, low, close, volume`, 2024-01-02 부터 평일) | `strategy/validate.py` 의 `sample_bars()`(고정 시드 7 랜덤워크 + 40봉마다 추세 바뀜, 시작가 50,000)를 그대로 저장. `tests/test_sample_run.py` 가 두 값이 같은지 확인한다 |
| `fake_tv_trades.csv` | 트레이딩뷰 거래 목록(List of trades) **형식** 견본 4거래 | 위 가짜 일봉에 기본 파라미터 Supertrend 를 돌린 결과를 트레이딩뷰 내보내기 열 이름·순서(최근 거래가 위, 거래 안에서 청산 줄이 위)로 적은 것. `Signal` 칸의 `Long`·`Short` 는 자리표시 이름 |

돌려 보기(이 실험 폴더 맨 위에서):
```
python -X utf8 scripts/strategy_backtest.py --csv sample_data/fake_daily_bars.csv --strategy supertrend
python -X utf8 scripts/strategy_validate.py supertrend --csv sample_data/fake_daily_bars.csv --tv-trades sample_data/fake_tv_trades.csv
```

## 진짜 데이터는 어디서
- **한투 일봉·분봉**: 설정 파일(`config.example.yaml` 참고)을 채운 뒤 `--code <종목코드>` 로 실행하면 `data/bars/` 에 받아 둔다(캐시, 저장소에 싣지 않음).
- **다른 곳에서 받은 일봉**: 위와 같은 열(`time, open, high, low, close, volume`)의 CSV 로 만들면 `--csv` 로 그대로 읽힌다. `time` 에 시간대가 없으면 한국 시간으로 본다.
- **트레이딩뷰 거래 목록**: 트레이딩뷰 Strategy Tester → 거래 목록(List of trades) → 내보내기(CSV). 차트 시간대를 Asia/Seoul 로 두고 내보낸다.
