"""차트 이미지 생성 서비스.

매매일지에 첨부할 차트 이미지를 생성한다.
matplotlib + mplfinance를 사용하여 캔들스틱 차트를 그린다.
"""

import logging
from pathlib import Path

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
            data: OHLCV 데이터 리스트
            markers: 매수/매도 포인트 표시

        Returns:
            생성된 차트 이미지 파일 경로
        """
        # TODO: mplfinance 기반 구현
        filepath = self.output_dir / f"{ticker}_chart.png"
        logger.info("차트 생성: %s -> %s", ticker, filepath)
        return str(filepath)
