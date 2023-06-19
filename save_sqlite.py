# encoding: utf-8

import sqlite3
import pandas as pd


def save_to_db(db_path, df: pd.DataFrame, table: str, **kwargs):
    with sqlite3.connect(db_path) as conn:
        df.to_sql(table, conn, **kwargs)
