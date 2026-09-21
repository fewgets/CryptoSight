import pandas as pd
from cryptosight.utils.logger import get_logger
from cryptosight.utils.db import get_connection, create_schema_and_table, insert_ohlcv, get_latest_timestamp

# Import exchange clients directly
from cryptosight.data.binance.binance_client_exch import BinanceClient
from cryptosight.data.bybit.bybit_client_exch import BybitClient

logger = get_logger("Downloader")

def download_exchange_data(exchange: str, symbol: str, timeframe: str, start_time: str, end_time: str, max_retries: int, retry_delay: int, fill_method: str):
    """
    Downloads historical data from the exchange, processes gaps and calculates
    volume percentage using pandas, and saves it directly to the database.
    """
    # Supported fill methods
    valid_methods = ["ffill", "interpolate_linear", "interpolate_time"]
    if fill_method not in valid_methods:
        raise ValueError(f"Invalid fill_method '{fill_method}'. Must be one of {valid_methods}")

    exchange_name = exchange.lower().strip()
    
    # 1. Select exchange client
    if exchange_name == "binance":
        client = BinanceClient()
    elif exchange_name == "bybit":
        client = BybitClient()
    else:
        raise ValueError(f"Unsupported exchange: {exchange_name}")

    # Standardize symbol format (e.g. BTC to BTC/USDT)
    pair_name = symbol.upper()
    if "/" not in pair_name:
        pair_name = f"{pair_name}/USDT"

    # 2. Connect to PostgreSQL
    conn = get_connection()

    try:
        # Create table if missing
        create_schema_and_table(conn, exchange_name, pair_name, timeframe)

        # Check latest timestamp in DB to resume fetching
        latest_time = get_latest_timestamp(conn, exchange_name, pair_name, timeframe)
        latest_time_pd = pd.to_datetime(latest_time, utc=True) if latest_time else None
        
        if latest_time_pd:
            start_query_time = latest_time_pd.strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"Resuming {pair_name} on {exchange_name.upper()} from: {start_query_time}")
        else:
            start_query_time = start_time
            logger.info(f"Starting {pair_name} fresh on {exchange_name.upper()} from: {start_query_time}")

        # 3. Fetch raw candles from the client
        raw_candles = client.fetch_raw_candles(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_query_time,
            end_time=end_time,
            max_retries=max_retries,
            retry_delay=retry_delay
        )

        if not raw_candles:
            logger.info(f"No new data returned from exchange for {pair_name}.")
            return

        # --- PANDAS PROCESSING ---

        # 1. Convert raw candles list to a pandas DataFrame
        # Each raw candle: [timestamp_ms, open, high, low, close, volume]
        timestamps = [pd.to_datetime(candle[0], unit='ms', utc=True) for candle in raw_candles]
        ohlcv_values = [candle[1:6] for candle in raw_candles]

        df = pd.DataFrame(
            ohlcv_values,
            index=timestamps,
            columns=['open', 'high', 'low', 'close', 'volume']
        ).copy()

        # Drop the last row (incomplete candle) since it is not complete
        if not df.empty:
            df = df.iloc[:-1]

        # Log how many missing (NaN) values exist in each column
        missing_counts = df.isnull().sum()
        logger.info(f"Missing (NaN) value counts per column before filling:\n{missing_counts}")

        # 4. Set all NaN volume values to 0.0 first
        df['volume'] = df['volume'].fillna(0.0)

        # 5. Fill missing OHLC values based on fill_method parameter
        ohlc_cols = ['open', 'high', 'low', 'close']
        if fill_method == "ffill":
            df[ohlc_cols] = df[ohlc_cols].ffill()
        elif fill_method == "interpolate_linear":
            df[ohlc_cols] = df[ohlc_cols].interpolate(method='linear')
        elif fill_method == "interpolate_time":
            df[ohlc_cols] = df[ohlc_cols].interpolate(method='time')

        # 6. Calculate volume_pct column (Temporarily removed/disabled)
        df['volume_pct'] = None

        # 7. Convert final DataFrame back to list of tuples for database insert
        final_data = []
        for ts, row in df.iterrows():
            # Skip duplicate timestamps that exist in the DB
            if latest_time_pd and ts <= latest_time_pd:
                continue
            
            # Append tuple of (timestamp_utc, open, high, low, close, volume, volume_pct)
            final_data.append((
                ts,
                float(row['open']),
                float(row['high']),
                float(row['low']),
                float(row['close']),
                float(row['volume']),
                None  # volume_pct is disabled/None for now
            ))

        if not final_data:
            logger.info(f"No newer data to save for {pair_name}.")
            return

        # 5. Insert data directly to PostgreSQL
        insert_ohlcv(conn, exchange_name, pair_name, timeframe, final_data)

    except Exception as e:
        logger.error(f"Failed to download data for {pair_name} on {exchange_name.upper()}: {e}")
        raise e
    finally:
        conn.close()
def fetch_and_merge_missing_data(exchange: str, symbol: str, timeframe: str, output_path: str):
    """
    Queries database for stored candles, gets missing candles up to now from exchange,
    merges both datasets, and saves the output to a CSV file. Does NOT save to database.
    """
    import os
    import pandas as pd
    from cryptosight.utils.db import get_connection
    from cryptosight.data.binance.binance_client_exch import BinanceClient
    from cryptosight.data.bybit.bybit_client_exch import BybitClient

    print(f"\nStarting merge process for {exchange.upper()} {symbol} {timeframe}...")

    # 1. Standardize table name and query database into a DataFrame
    schema_name = f"{exchange.lower()}_data"
    pair_name = symbol.upper()
    if "/" not in pair_name:
        pair_name = f"{pair_name}/USDT"
    clean_symbol = pair_name.lower().replace("/", "_")
    table_name = f"{exchange.lower()}_{clean_symbol}_{timeframe.lower()}"
    
    query = f"SELECT timestamp, open, high, low, close, volume FROM {schema_name}.{table_name} ORDER BY timestamp ASC;"
    
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            colnames = [desc[0] for desc in cursor.description]
        db_df = pd.DataFrame(rows, columns=colnames)
    finally:
        conn.close()

    if db_df.empty:
        print("Database table is empty. No data to merge.")
        return None

    db_df['timestamp'] = pd.to_datetime(db_df['timestamp'], utc=True)
    db_df.set_index('timestamp', inplace=True)

    db_min = db_df.index.min()
    db_max = db_df.index.max()
    print(f"Database data range: {db_min} to {db_max} (Total: {len(db_df)} records)")

    # 2. Get current time in UTC
    now_utc = pd.Timestamp.now(tz='UTC')
    print(f"Current UTC Time: {now_utc}")

    # 3. Define missing time window range
    start_fetch = db_max.strftime("%Y-%m-%d %H:%M:%S")
    end_fetch = "now"

    # 4. Fetch missing data from Exchange Client
    exchange_name = exchange.lower().strip()
    if exchange_name == "binance":
        client = BinanceClient()
    elif exchange_name == "bybit":
        client = BybitClient()
    else:
        raise ValueError(f"Unsupported exchange: {exchange_name}")

    print(f"Fetching missing data from exchange starting from: {start_fetch}")
    raw_candles = client.fetch_raw_candles(
        symbol=symbol,
        timeframe=timeframe,
        start_time=start_fetch,
        end_time=end_fetch,
        max_retries=3,
        retry_delay=2
    )

    if not raw_candles:
        print("No missing data returned from the exchange.")
        merged_df = db_df
    else:
        # Convert raw candles to DataFrame
        timestamps = [pd.to_datetime(candle[0], unit='ms', utc=True) for candle in raw_candles]
        ohlcv_values = [candle[1:6] for candle in raw_candles]

        ex_df = pd.DataFrame(
            ohlcv_values,
            index=timestamps,
            columns=['open', 'high', 'low', 'close', 'volume']
        )

        # Drop the last row (incomplete candle)
        if not ex_df.empty:
            ex_df = ex_df.iloc[:-1]

        print(f"Fetched {len(ex_df)} new candles from Exchange.")

        # Concat both and remove duplicate indexes (keeping newest from exchange)
        # merged_df = pd.concat([db_df, ex_df])
        # merged_df = merged_df[~merged_df.index.duplicated(keep='first')].sort_index()
        merged_df = db_df

    print(f"Merged DataFrame range: {merged_df.index.min()} to {merged_df.index.max()} (Total: {len(merged_df)} records)")

    # 5. Save the merged output to the specified file path
    # if output_path:
    #     os.makedirs(os.path.dirname(output_path), exist_ok=True)
    #     merged_df.to_csv(output_path)
    #     print(f"SUCCESS: Merged data saved to file: {output_path}")

    return merged_df


if __name__ == "__main__":
    # Test the function directly when running: python data/downloader.py
    from pathlib import Path
    import sys

    # Add project's parent directory to sys.path to enable 'cryptosight' imports
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root.parent) not in sys.path:
        sys.path.insert(0, str(project_root.parent))

    test_out = str(project_root / "logs" / "merged_test_output.csv")
    print("Running ad-hoc test for fetch_and_merge_missing_data...")
    try:
        # Check Binance BTC 1m data merge
        df = fetch_and_merge_missing_data(
            exchange="binance",
            symbol="BTC",
            timeframe="1m",
            output_path=test_out
        )
        if df is not None:
            print(f"Test Succeeded! Merged rows count: {len(df)}")
    except Exception as e:
        print(f"Test Failed: {e}")

def resample_ohlcv(exchange: str, symbol: str, timeframe: str, target_timeframe: str = "4h", output_path: str = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    1. Calls fetch_and_merge_missing_data to fetch, merge, and clean database and exchange data.
    2. Resamples the resulting merged data to the target higher timeframe.
    3. Returns both: (merged_lower_tf_df, resampled_df)
    """
    import pandas as pd

    # 1. Fetch, merge, and clean the data from DB and Exchange
    merged_df = fetch_and_merge_missing_data(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        output_path=output_path
    )

    if merged_df is None or merged_df.empty:
        print("No data available to resample.")
        return pd.DataFrame(), pd.DataFrame()

    # 2. Define aggregation rules for each column
    agg_rules = {
        'open': 'first',   # Open price of the first candle in the window
        'high': 'max',     # Highest price reached during the period
        'low': 'min',      # Lowest price reached during the period
        'close': 'last',   # Close price of the last candle in the window
        'volume': 'sum'    # Sum of all volumes during the period
    }

    # 3. Resample the merged DataFrame to the target timeframe (e.g., "4h")
    resampled_df = merged_df.resample(target_timeframe).agg(agg_rules)

    # 4. Drop empty intervals (gaps) from the resampled data
    resampled_df.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)

    # Return both original merged DataFrame and the resampled DataFrame
    return merged_df, resampled_df
