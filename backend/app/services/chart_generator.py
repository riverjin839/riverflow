"""차트 이미지 생성 서비스.

매매일지에 첨부할 차트 이미지를 생성한다.
matplotlib + mplfinance를 사용하여 캔들스틱 차트를 그린다.
"""

import logging
from pathlib import Path

import matplotlib
import mplfinance as mpf
import pandas as pd

matplotlib.use("Agg")

logger = logging.getLogger(__name__)

CHART_DIR = Path("/tmp/charts")


class ChartGenerator:
    """주식 차트 이미지 생성"""

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or CHART_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_candlestick(
        self,
        ticker: str,
        data: list[dict],
        markers: list[dict] | None = None,
    ) -> str:
        """캔들스틱 차트 생성.

        Args:
            ticker: 종목 코드
            data: OHLCV 데이터 리스트.
                  각 dict에 date, open, high, low, close, volume 포함.
            markers: 매수/매도 포인트 표시.
                  각 dict에 date, type('buy'|'sell'), price 포함.

        Returns:
            생성된 차트 이미지 파일 경로
        """
        filepath = self.output_dir / f"{ticker}_chart.png"

        if not data:
            logger.warning("차트 생성 실패: %s 데이터 없음", ticker)
            return str(filepath)

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df = df.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })

        add_plots = []
        if markers:
            buy_dates = []
            sell_dates = []
            for m in markers:
                mdate = pd.Timestamp(m["date"])
                if m["type"] == "buy":
                    buy_dates.append(mdate)
                elif m["type"] == "sell":
                    sell_dates.append(mdate)

            if buy_dates:
                buy_signals = df["Low"].copy() * float("nan")
                for d in buy_dates:
                    if d in buy_signals.index:
                        buy_signals[d] = df.loc[d, "Low"] * 0.98
                add_plots.append(
                    mpf.make_addplot(buy_signals, type="scatter", marker="^", markersize=100, color="red")
                )

            if sell_dates:
                sell_signals = df["High"].copy() * float("nan")
                for d in sell_dates:
                    if d in sell_signals.index:
                        sell_signals[d] = df.loc[d, "High"] * 1.02
                add_plots.append(
                    mpf.make_addplot(sell_signals, type="scatter", marker="v", markersize=100, color="blue")
                )

        style = mpf.make_mpf_style(
            base_mpf_style="charles",
            rc={"font.size": 8},
        )

        kwargs: dict = {
            "type": "candle",
            "volume": "Volume" in df.columns and df["Volume"].notna().any(),
            "style": style,
            "title": ticker,
            "savefig": str(filepath),
            "figscale": 1.2,
        }
        if add_plots:
            kwargs["addplot"] = add_plots

        mpf.plot(df, **kwargs)

        logger.info("차트 생성: %s -> %s", ticker, filepath)
        return str(filepath)
