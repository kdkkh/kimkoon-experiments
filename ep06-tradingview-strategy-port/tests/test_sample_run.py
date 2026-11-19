# 모의투자로만 검증한 것입니다. 실전에 쓰려면 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
"""네트워크 없는 견본 실행 — sample_data/ 의 가짜 일봉 CSV 로 백테스트·검증기가 끝까지 도는지, 스크립트도 도는지.
가짜 일봉은 validate.sample_bars()(고정 시드 합성 랜덤워크)를 그대로 저장한 것이라, 두 값이 같아야 한다."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from strategy import data  # noqa: E402
from strategy.backtest import run_backtest  # noqa: E402
from strategy.ported import load_strategy  # noqa: E402
from strategy.validate import sample_bars, validate  # noqa: E402

BARS = ROOT / "sample_data" / "fake_daily_bars.csv"
TV = ROOT / "sample_data" / "fake_tv_trades.csv"


def test_csv_equals_synthetic_generator():
    a = data.read_bars_csv(BARS)
    b = sample_bars()
    assert len(a) == len(b) == 400
    for c in ("open", "high", "low", "close", "volume"):
        assert (a[c].to_numpy() == b[c].to_numpy()).all(), c
    assert (a["time"].dt.strftime("%Y-%m-%d") == b["time"].dt.strftime("%Y-%m-%d")).all()


def test_backtest_on_csv():
    bars = data.read_bars_csv(BARS)
    strat = load_strategy("supertrend")
    r = run_backtest(bars, strat.run(bars))
    assert r.summary["봉 수"] == 400
    assert len(r.trades) >= 4


def test_validate_on_csv_with_tv_sample():
    rep = validate("supertrend", bars=data.read_bars_csv(BARS), tv_trades=str(TV))
    assert rep.verdict == "통과", rep.lines


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *args],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def test_validate_script_offline():
    p = _run("strategy_validate.py", "supertrend", "--csv", str(BARS), "--tv-trades", str(TV))
    assert p.returncode == 0, p.stdout + p.stderr
    assert "⑤ 판정: 통과" in p.stdout


def test_backtest_script_offline():
    p = _run("strategy_backtest.py", "--csv", str(BARS), "--strategy", "supertrend", "--brief")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "API 호출 0회" in p.stdout and "[요약]" in p.stdout
    # 결과물(data/backtest/)은 저장소에 싣지 않는다(.gitignore 의 data/) — 이 시험이 남긴 파일만 지운다
    out = ROOT / "data" / "backtest"
    for f in out.glob("fake_daily_bars_csv_supertrend_*"):
        f.unlink()
    for d in (out, ROOT / "data"):
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
