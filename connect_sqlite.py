# encoding: utf-8

import sqlite3
import pandas as pd
from logging import info


def save_to_db(db_path, df: pd.DataFrame, table: str, **kwargs):
    info(f"[connect_sqlite save_to_db] Save data to {db_path} table: {table}")
    with sqlite3.connect(db_path) as conn:
        df.to_sql(table, conn, **kwargs)


def get_data(db_path, query):
    info(f"[connect_sqlite get_data] Get data from {db_path} query: {query}")
    with sqlite3.connect(db_path) as conn:
        data = pd.read_sql_query(query, conn)
    return data
