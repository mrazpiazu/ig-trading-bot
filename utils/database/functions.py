import logging
from sqlalchemy import text, insert, select, distinct, func
from sqlalchemy.sql import exists
import os
from datetime import datetime as dt

from utils.database.db import SessionLocal
from utils.database.models import StockBar, Stock, StockBarAggregate
from utils.logger.logger import get_logger_config
from utils.brokers.alpaca_market.alpaca_rest_api import get_stock_data

logger = logging.getLogger("db_functions")
get_logger_config(logging)

session = SessionLocal()

def get_active_symbols():
    """
    Load active symbols from the database.
    """
    try:
        query = session.query(StockBar)
        active_symbols = query.distinct(StockBar.symbol).all()
        symbols = [symbol.symbol for symbol in active_symbols]

        return symbols
    except Exception as e:
        logger.error(f"Error loading active symbols: {e}")
        return []
    finally:
        session.close()


def load_stock_table_list(group_by=None):
    """
    Load the Stock table from the database.
    Returns:
        list: List of Stock objects.
    """
    try:
        query = session.query(Stock)
        stock_table = query.all()

        stock_table_list = [symbol.symbol for symbol in stock_table]

        if group_by == 'alphabetical':
            # Group list by starting letter
            stock_table_list.sort()
            grouped_stock_table = []
            for symbol in stock_table_list:
                starting_letter = symbol[0].upper()
                if starting_letter not in grouped_stock_table:
                    grouped_stock_table.append(starting_letter)

            stock_table_list = grouped_stock_table

        return stock_table_list
    except Exception as e:
        logger.error(f"Error loading Stock table: {e}")
        return []
    finally:
        session.close()


def load_stock_starting_by(starting_letter):

    """
    Load the Stock table from the database.
    Args:
        starting_letter (str): Starting letter to filter symbols.
    Returns:
        list: List of Stock objects starting with the specified letter.
    """
    try:
        query = session.query(Stock).filter(Stock.symbol.like(f"{starting_letter}%"))
        stock_table = query.all()

        stock_table_list = [symbol.symbol for symbol in stock_table]

        return stock_table_list
    except Exception as e:
        logger.error(f"Error loading Stock table: {e}")
        return []
    finally:
        session.close()


def insert_new_stocks():
    """
    Inserts distinct symbols from StockBar into Stock table
    Returns:
    """

    stmt = insert(Stock).from_select(
        ['symbol'],
        select(distinct(StockBar.symbol)).where(
            ~StockBar.symbol.in_(select(Stock.symbol).scalar_subquery())
        )
    )

    session.execute(stmt)
    session.commit()


def run_backfill_fact_stock_bars(start_time, end_time):
    """
    Backfill data for a specific symbol.
    """

    logger.info(f"Backfilling data for symbols from {start_time} to {end_time}")

    current_dir = os.path.dirname(os.path.abspath(__file__))

    with open(f"{current_dir}/backfill_fact_stock_bars.sql", "r") as file:
        sql_query = text(file.read())

    try:

        logger.info("Deleting existing backfilled data in StockBar table...")
        delete_stmt = StockBar.__table__.delete().where(
            StockBar.created_at >= start_time,
            StockBar.created_at < end_time,
            StockBar.is_imputed == True
        )
        session.execute(delete_stmt)
        session.commit()
        logger.info("Deleted existing data in StockBar table")

        logger.info("Backfilling data in StockBar table...")
        session.execute(sql_query, {
            "start_time": start_time,
            "end_time": end_time
        })
        session.commit()
        logger.info(f"Backfilled data for symbols from {start_time} to {end_time}")
    except Exception as e:
        logger.error(f"Error backfilling symbol data: {e}")
        session.rollback()
        raise


def run_backfill_fact_stock_bars_api(start_time, end_time):

    logger.info(f"Backfilling data for symbols from {start_time} to {end_time}")

    expected_minutes = int((end_time - start_time).total_seconds() // 60)

    symbols_query = text(f"""
        WITH counted_bars AS (
            SELECT
                symbol,
                COUNT(*) AS actual_count
            FROM fact_stock_bars
            WHERE created_at >= :start_time
              AND created_at < :end_time AND
              is_imputed = False
            GROUP BY symbol
        )
        SELECT ds.symbol
        FROM dim_stocks ds
        LEFT JOIN counted_bars cb ON ds.symbol = cb.symbol
        WHERE COALESCE(cb.actual_count, 0) < :expected_minutes;
    """)

    result = session.execute(symbols_query,
                             {
                                "start_time": start_time,
                                "end_time": end_time,
                                "expected_minutes": expected_minutes
                             }).all()
    symbols_list = [row.symbol for row in result]

    logger.info(f"Reloading {len(symbols_list)} symbols from Alpaca API")

    get_stock_data(start_time, end_time, symbols_list)
    logger.info(f"Reloaded {len(symbols_list)} symbols from Alpaca API")


def run_agg_stock_bars_candles(start_time, end_time, aggregation):

    """
    Aggregate stock data.
    """

    logger.info("Aggregating stock data...")

    current_dir = os.path.dirname(os.path.abspath(__file__))

    with open(f"{current_dir}/agg_stock_bars_candles.sql", "r") as file:
        sql_query = text(file.read())

    try:

        logger.info("Deleting existing aggregated data in StockBarAggregate table...")
        delete_stmt = StockBarAggregate.__table__.delete().where(
            StockBarAggregate.created_at >= start_time,
            StockBarAggregate.created_at < end_time,
            StockBarAggregate.aggregation == aggregation
        )
        session.execute(delete_stmt)
        session.commit()
        logger.info("Deleted existing data in StockBarAggregate table")

        logger.info("Aggregating data in StockBarAggregate table...")
        session.execute(sql_query,
                        {
                            "start_time": start_time,
                            "end_time": end_time,
                            "aggregation": aggregation
                        })
        session.commit()
        logger.info("Aggregated stock data")
    except Exception as e:
        logger.error(f"Error aggregating stock data: {e}")
        session.rollback()
        raise


def run_agg_backfill_stock_bars(start_time, end_time, aggregation):

    """
    Backfill data for a specific symbol.
    """

    logger.info(f"Backfilling data for symbols from {start_time} to {end_time}")

    current_dir = os.path.dirname(os.path.abspath(__file__))

    with open(f"{current_dir}/agg_backfill_stock_bars.sql", "r") as file:
        sql_query = text(file.read())

    try:

        logger.info("Deleting existing backfilled data in StockBarAggregate table...")
        delete_stmt = StockBarAggregate.__table__.delete().where(
            StockBarAggregate.created_at >= start_time,
            StockBarAggregate.created_at < end_time,
            StockBarAggregate.aggregation == aggregation
        )
        session.execute(delete_stmt)
        session.commit()
        logger.info("Deleted existing data in StockBarAggregate table")

        logger.info("Aggregating backfilled data in StockBarAggregate table...")
        session.execute(sql_query, {
            "start_time": start_time,
            "end_time": end_time,
            "aggregation": aggregation
        })
        session.commit()
        logger.info(f"Aggregated backfilled data for symbols from {start_time} to {end_time}")
    except Exception as e:
        logger.error(f"Error backfilling symbol data: {e}")
        session.rollback()
        raise


def run_agg_stock_bars(start_time, end_time, aggregation):
    """
    Aggregate stock data.
    """

    logger.info("Aggregating stock data...")

    current_dir = os.path.dirname(os.path.abspath(__file__))

    with open(f"{current_dir}/agg_stock_bars.sql", "r") as file:
        sql_query = text(file.read())

    try:

        logger.info("Deleting existing aggregated data in StockBarAggregate table...")
        delete_stmt = StockBarAggregate.__table__.delete().where(
            StockBarAggregate.created_at >= start_time,
            StockBarAggregate.created_at < end_time,
            StockBarAggregate.aggregation == aggregation
        )
        session.execute(delete_stmt)
        session.commit()
        logger.info("Deleted existing data in StockBarAggregate table")

        logger.info("Aggregating data in StockBarAggregate table...")
        session.execute(sql_query,
                        {
                            "start_time": start_time,
                            "end_time": end_time,
                            "aggregation": aggregation
                        })
        session.commit()
        logger.info("Aggregated stock data")
    except Exception as e:
        logger.error(f"Error aggregating stock data: {e}")
        session.rollback()
        raise


if __name__ == "__main__":

    start_time = dt(2025, 4, 1, 0, 0)
    end_time = dt(2025, 5, 5, 23, 59)

    run_backfill_fact_stock_bars_api(start_time, end_time)