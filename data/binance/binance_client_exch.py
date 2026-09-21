import os
import sys
import time
import pandas as pd

# Add project root to path to resolve 'utils' imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from binance import Client
from cryptosight.utils.logger import get_logger
logger = get_logger("BinanceClient")


class BinanceClient:
    """
    Fetches historical OHLCV candles from Binance.
    No API keys needed for public historical data.
    """

    def __init__(self):
        # Create Binance client — no keys needed for public data
        self.client = Client()

    def fetch_raw_candles(self, symbol: str, timeframe: str, start_time: str,
                          end_time: str, max_retries: int, retry_delay: int) -> list:
        """
        Fetches historical candles from Binance with retry logic.
        Returns list of [timestamp_ms, open, high, low, close, volume]
        """
        # Convert symbol: "BTC" or "BTC/USDT" → "BTCUSDT"
        binance_symbol = symbol.upper().replace("/", "")
        if not binance_symbol.endswith("USDT"):
            binance_symbol = f"{binance_symbol}USDT"

        # Convert "now" to actual UTC datetime string — Binance does not understand "now"
        end_str = (
            pd.Timestamp.now(tz='UTC').strftime("%Y-%m-%d %H:%M:%S")
            if end_time == "now"
            else end_time
        )

        retries = 0
        while retries < max_retries:
            try:
                logger.info(f"Fetching {binance_symbol} | {timeframe} | {start_time} to {end_str}")

                # Binance handles pagination automatically — fetches all candles in batches
                raw_klines = self.client.get_historical_klines(
                    symbol=binance_symbol,
                    interval=timeframe,
                    start_str=start_time,
                    end_str=end_str
                )

                if not raw_klines:
                    return []

                # Keep only 6 values we need from Binance's 12-value response
                processed_candles = []
                for k in raw_klines:
                    processed_candles.append([
                        int(k[0]),      # timestamp in milliseconds
                        float(k[1]),    # open
                        float(k[2]),    # high
                        float(k[3]),    # low
                        float(k[4]),    # close
                        float(k[5])     # volume
                    ])

                logger.info(f"Fetched {len(processed_candles)} candles for {binance_symbol}.")
                return processed_candles

            except Exception as e:
                retries += 1
                logger.warning(f"Attempt {retries}/{max_retries} failed: {e}")
                if retries < max_retries:
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries reached. Binance fetch failed.")
                    raise e


