import yaml
from pathlib import Path
from cryptosight.data.downloader import download_exchange_data
from cryptosight.utils.logger import get_logger

logger = get_logger("BinanceMain")


def main(exchange: str, symbols: list, timeframe: str, start_time: str,
         end_time: str, fill_method: str, max_retries: int, retry_delay: int):
    """
    Main runner for Binance ingestion.
    Reads all parameters from config and passes them to the downloader.
    """
    logger.info("--- Starting Binance Ingestion Pipeline ---")

    # Loop through each symbol and download its data
    for symbol in symbols:
        try:
            # Pass ALL config parameters to downloader
            download_exchange_data(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                fill_method=fill_method,
                max_retries=max_retries,
                retry_delay=retry_delay
            )
        except Exception as e:
            logger.error(f"Failed to process symbol {symbol}: {e}")

    logger.info("--- Binance Ingestion Pipeline Finished ---")

import yaml
from pathlib import Path
from cryptosight.data.downloader import download_exchange_data
from cryptosight.utils.logger import get_logger

logger = get_logger("BinanceMain")


def main(exchange: str, symbols: list, timeframe: str, start_time: str,
         end_time: str, fill_method: str, max_retries: int, retry_delay: int):
    """
    Main runner for Binance ingestion.
    Reads all parameters from config and passes them to the downloader.
    """
    logger.info("--- Starting Binance Ingestion Pipeline ---")

    for symbol in symbols:
        try:
            download_exchange_data(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                fill_method=fill_method,
                max_retries=max_retries,
                retry_delay=retry_delay
            )
        except Exception as e:
            logger.error(f"Failed to process symbol {symbol}: {e}")

    logger.info("--- Binance Ingestion Pipeline Finished ---")


if __name__ == "__main__":
    # Path(__file__) = this file
    # .parent = folder containing this file (binance/)
    # / "config.yaml" = joins path to config file
    config_path = Path(__file__).parent / "config.yaml"
    
    # Path.read_text() reads file content — no need for open/close
    config = yaml.safe_load(config_path.read_text())

    # Safety check — wrap single string symbol in list
    symbols = config.get("symbols", [])
    if isinstance(symbols, str):
        symbols = [symbols]

    logger.info("=== Config Loaded ===")
    logger.info(f"Exchange   : {config.get('exchange')}")
    logger.info(f"Symbols    : {symbols}")
    logger.info(f"Timeframe  : {config.get('timeframe')}")
    logger.info(f"Start Time : {config.get('start_time')}")
    logger.info(f"End Time   : {config.get('end_time')}")
    logger.info(f"Fill Method: {config.get('fill_method')}")
    logger.info(f"Max Retries: {config.get('max_retries')}")
    logger.info(f"Retry Delay: {config.get('retry_delay')}")

    main(
        exchange=config.get("exchange"),
        symbols=symbols,
        timeframe=config.get("timeframe"),
        start_time=config.get("start_time"),
        end_time=config.get("end_time"),
        fill_method=config.get("fill_method", "ffill"),
        max_retries=config.get("max_retries", 5),
        retry_delay=config.get("retry_delay", 3)
    )