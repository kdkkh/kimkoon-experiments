# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""Pine Script v6 `ta.*` 대응 함수 — 트레이딩뷰 공식 문서의 정의대로.

출처: Pine Script v6 Reference Manual https://www.tradingview.com/pine-script-reference/v6/
  - 2026-11-03 에 문서를 읽고 맞춤. 각 함수 docstring 에 문서 항목 주소(#fun_ta.xxx)를 적어 두었다.
  - 문서의 예시 코드("the same on pine")는 여기 싣지 않았다 — 대조할 때는 위 주소에서 직접 열어 볼 것.
    docstring 에는 그 예시가 하는 계산을 우리말로 풀어 적었다.

공통 규칙
  - 입력은 pandas Series(같은 index), 출력도 같은 index 의 Series.
  - Pine 의 na 는 NaN. 비교에 NaN 이 끼면 False(Pine v6 에서 na 비교 결과를 bool 로 쓰면 false 와 같음).
  - 문서 REMARKS 의 "na values in the source series are ignored" 는 '앞쪽(데이터 시작 전) na 를 건너뛰고
    na 아닌 값 length 개로 계산'으로 구현했다. 중간에 끼는 na(실제 봉 데이터엔 없음)는 직전 값을 잇는다(추정).
  - 외부 지표 라이브러리(pandas-ta, ta-lib)는 쓰지 않는다 — 초기값 처리가 Pine 과 미묘하게 달라
    트레이딩뷰 결과와 대조할 때 어디서 갈라졌는지 흐려진다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

REF = "https://www.tradingview.com/pine-script-reference/v6/"


def _as_series(x, like: pd.Series) -> pd.Series:
    if isinstance(x, pd.Series):
        return x.astype(float)
    return pd.Series(float(x), index=like.index)


def _first_valid(a: np.ndarray) -> int | None:
    ok = np.flatnonzero(~np.isnan(a))
    return int(ok[0]) if len(ok) else None


def sma(src: pd.Series, length: int) -> pd.Series:
    """ta.sma(source, length) — 최근 length 개 값의 산술 평균. 앞 length-1 봉은 na.

    출처: {REF}#fun_ta.sma
    """
    return src.astype(float).rolling(length, min_periods=length).mean()


def _recursive_ma(src: pd.Series, length: int, alpha: float, seed: str) -> pd.Series:
    """앞 값이 na 면 seed 로 시작, 그 뒤는 alpha * src + (1 - alpha) * 앞 값."""
    a = src.to_numpy(dtype=float)
    out = np.full(len(a), np.nan)
    f = _first_valid(a)
    if f is None:
        return pd.Series(out, index=src.index)
    if seed == "sma":
        start = f + length - 1
        if start >= len(a):
            return pd.Series(out, index=src.index)
        out[start] = np.nanmean(a[f:start + 1])     # 첫 값 = 처음 length 개 값의 단순 평균
    elif seed == "first":
        start = f
        out[start] = a[f]                           # 첫 값 = 첫 source 값
    else:
        raise ValueError("seed 는 'sma' 또는 'first'")
    for i in range(start + 1, len(a)):
        out[i] = out[i - 1] if np.isnan(a[i]) else alpha * a[i] + (1 - alpha) * out[i - 1]
    return pd.Series(out, index=src.index)


def rma(src: pd.Series, length: int) -> pd.Series:
    """ta.rma(source, length) — RSI·ATR 에 쓰는 이동평균(Wilder), alpha = 1/length.
    첫 값은 처음 length 개의 단순 평균(ta.sma), 그 뒤는 alpha*src + (1-alpha)*앞 값.

    출처: {REF}#fun_ta.rma (문서 예시: 앞 값이 na 면 ta.sma 로 시작)
    """
    return _recursive_ma(src, length, 1.0 / length, "sma")


def ema(src: pd.Series, length: int, seed: str = "first") -> pd.Series:
    """ta.ema(source, length) — 지수 이동평균, alpha = 2/(length+1).

    출처: {REF}#fun_ta.ema
    주의: v6 문서 예시는 첫 값을 '첫 source 값'으로 시작한다(seed="first", 기본).
      내장 ta.ema 가 실제로 처음 length 개 단순 평균으로 시작하는지는 미확인 → seed="sma" 도 둔다.
      데이터가 길면(수백 봉) 두 방식 차이는 0 에 가까워진다. 앞부분 값이 트레이딩뷰와 다르면 seed 를 바꿔 대조.
    """
    return _recursive_ma(src, length, 2.0 / (length + 1), seed)


def tr(high: pd.Series, low: pd.Series, close: pd.Series, handle_na: bool = True) -> pd.Series:
    """True Range. ta.tr(handle_na) — max(high-low, |high-close[1]|, |low-close[1]|).
    앞 봉 종가가 없으면(첫 봉) handle_na=True 일 때 high-low, False 일 때 na.

    출처: {REF}#fun_ta.tr . 문서의 ta.atr 예시는 첫 봉에 high-low 를 쓴다(= handle_na=True).
    """
    h, l, pc = high.astype(float), low.astype(float), close.astype(float).shift(1)
    rng = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1, skipna=False)
    first = pc.isna()
    rng[first] = (h - l)[first] if handle_na else np.nan
    return rng


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    """ta.atr(length) — True Range(첫 봉은 high-low)의 RMA.

    출처: {REF}#fun_ta.atr
    """
    return rma(tr(high, low, close, handle_na=True), length)


def supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
               factor: float, atr_period: int) -> tuple[pd.Series, pd.Series]:
    """ta.supertrend(factor, atrPeriod) → (supertrend, direction).
    direction: -1 = 상승 추세(선이 가격 아래), 1 = 하락 추세(선이 가격 위). Pine 과 같다.

    출처: {REF}#fun_ta.supertrend — 문서 예시의 계산 순서를 그대로 따랐다:
      1. src = (high+low)/2, atr = ta.atr(atrPeriod)
      2. 위 띠 = src + factor*atr, 아래 띠 = src - factor*atr
      3. 앞 봉 띠가 na 면 0 으로 본다(nz).
         아래 띠: 새 값이 앞 아래 띠보다 크거나, 앞 봉 종가가 앞 아래 띠보다 낮으면 새 값, 아니면 앞 값 유지.
         위 띠:   새 값이 앞 위 띠보다 작거나, 앞 봉 종가가 앞 위 띠보다 높으면 새 값, 아니면 앞 값 유지.
      4. 방향: 앞 봉 atr 이 na 면 1(하락).
         앞 봉 선이 앞 위 띠와 같았으면(하락 추세) 종가 > 위 띠 일 때 -1, 아니면 1.
         그 밖(앞 봉이 상승 추세)이면 종가 < 아래 띠 일 때 1, 아니면 -1.
      5. 선 = 방향이 -1 이면 아래 띠, 아니면 위 띠.
    ATR 이 아직 없는 앞 atrPeriod-1 봉과 그다음 첫 봉은 direction=1(하락)로 시작한다(문서 예시 그대로).
    """
    h, l, c = high.to_numpy(float), low.to_numpy(float), close.to_numpy(float)
    a = atr(high, low, close, atr_period).to_numpy(float)
    src = (h + l) / 2
    upper_raw = src + factor * a
    lower_raw = src - factor * a
    n = len(c)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    st = np.full(n, np.nan)
    d = np.ones(n, dtype=int)

    def nz(v: float) -> float:
        return 0.0 if np.isnan(v) else v

    for i in range(n):
        prev_lower = nz(lower[i - 1]) if i > 0 else 0.0
        prev_upper = nz(upper[i - 1]) if i > 0 else 0.0
        c1 = c[i - 1] if i > 0 else np.nan
        lb, ub = lower_raw[i], upper_raw[i]
        # NaN 이 낀 비교는 False — Pine 과 같다
        lower[i] = lb if (lb > prev_lower or c1 < prev_lower) else prev_lower
        upper[i] = ub if (ub < prev_upper or c1 > prev_upper) else prev_upper
        if i == 0 or np.isnan(a[i - 1]):
            d[i] = 1
        elif st[i - 1] == upper[i - 1]:            # 앞 봉 선이 위쪽 띠였으면(하락 추세)
            d[i] = -1 if c[i] > upper[i] else 1
        else:                                      # 앞 봉 선이 아래쪽 띠였으면(상승 추세)
            d[i] = 1 if c[i] < lower[i] else -1
        st[i] = lower[i] if d[i] == -1 else upper[i]
    return pd.Series(st, index=close.index), pd.Series(d, index=close.index)


def change(src: pd.Series, length: int = 1) -> pd.Series:
    """ta.change(source, length=1) — source - source[length]. 앞 length 봉은 na.

    출처: {REF}#fun_ta.change
    """
    return src.astype(float) - src.astype(float).shift(length)


def crossover(a, b) -> pd.Series:
    """ta.crossover(source1, source2) — 이번 봉 a > b 이고 앞 봉 a <= b 이면 True.

    출처: {REF}#fun_ta.crossover
    b 에 숫자 하나(예: 70)를 줘도 된다.
    """
    like = a if isinstance(a, pd.Series) else b
    s1, s2 = _as_series(a, like), _as_series(b, like)
    return ((s1 > s2) & (s1.shift(1) <= s2.shift(1))).fillna(False).astype(bool)


def crossunder(a, b) -> pd.Series:
    """ta.crossunder(source1, source2) — 이번 봉 a < b 이고 앞 봉 a >= b 이면 True.

    출처: {REF}#fun_ta.crossunder
    """
    like = a if isinstance(a, pd.Series) else b
    s1, s2 = _as_series(a, like), _as_series(b, like)
    return ((s1 < s2) & (s1.shift(1) >= s2.shift(1))).fillna(False).astype(bool)


def highest(src: pd.Series, length: int) -> pd.Series:
    """ta.highest(source, length) — 이번 봉 포함 최근 length 봉 중 최댓값. 앞 length-1 봉은 na.

    출처: {REF}#fun_ta.highest . 인자 하나 판(ta.highest(length))은 source=high → highest(df.high, n).
    """
    return src.astype(float).rolling(length, min_periods=length).max()


def lowest(src: pd.Series, length: int) -> pd.Series:
    """ta.lowest(source, length) — 이번 봉 포함 최근 length 봉 중 최솟값. 앞 length-1 봉은 na.

    출처: {REF}#fun_ta.lowest . 인자 하나 판은 source=low.
    """
    return src.astype(float).rolling(length, min_periods=length).min()


def rsi(src: pd.Series, length: int) -> pd.Series:
    """ta.rsi(source, length) — 오름폭·내림폭의 ta.rma 로 계산한 RSI.

    출처: {REF}#fun_ta.rsi — 문서 예시의 계산:
      오름폭 u = max(x - x[1], 0), 내림폭 d = max(x[1] - x, 0), rs = rma(u)/rma(d), RSI = 100 - 100/(1+rs)
    첫 봉은 x[1] 이 없어 u·d 가 na → rma 는 둘째 봉부터 length 개로 시작(첫 RSI 는 length 번째 index).
    내림폭 rma 가 0 이면 100, 오름폭 rma 가 0 이면 0 으로 둔다(0 나누기 처리 — 내장 함수와 같은지는 미확인).
    """
    x = src.astype(float)
    diff = x - x.shift(1)
    u = diff.clip(lower=0)
    d = (-diff).clip(lower=0)
    up, dn = rma(u, length), rma(d, length)
    out = 100 - 100 / (1 + up / dn)
    out = out.where(dn != 0, 100.0)
    out = out.where(~((up == 0) & (dn != 0)), 0.0)
    return out.where(up.notna() & dn.notna())


# docstring 의 {REF} 를 실제 주소로 바꿔 둔다(help() 로 볼 때 주소가 보이게)
for _f in (sma, rma, ema, tr, atr, supertrend, change, crossover, crossunder, highest, lowest, rsi):
    if _f.__doc__:
        _f.__doc__ = _f.__doc__.replace("{REF}", REF)
del _f
