import datetime
import os
import time

import mysql.connector.errors

from utils import setup_logger, connect_mysql, close_mysql, update_many, check_db_myimdb
from utils import get_omdb

logger = setup_logger('OMDB_refresher')

REVIEW_INTERVAL_REFRESH = int(os.getenv('REVIEW_INTERVAL_REFRESH'))
OMDB_API_LIMIT = int(os.getenv('OMDB_API_LIMIT'))
INSERT_RATE = int(os.getenv('INSERT_RATE'))


def get_omdb_data(session_not_found=[]):
    """
    populates the database with data from TMDB
    session_not_found are the IDs searched for and not found which can be passed to this function
    in order not to search for them again.
    Extra keys:
    Poze, Country, Lang, Ovrw(short descr), score, trailer_link,
    :return:
    """
    # New titles
    logger.info("Downloading data for new OMDB titles")
    # Get how many API calls we have left
    api_calls = get_omdb_api_limit()
    try:
        conn, new_for_omdb_cursor = get_new_imdb_titles('omdb_data', session_not_found)
    except mysql.connector.errors.ProgrammingError:
        conn, new_for_omdb_cursor = None, None
    if new_for_omdb_cursor:
        while new_for_omdb_cursor.with_rows:
            if api_calls > INSERT_RATE:
                calls_to_make = INSERT_RATE
                stop = False
            else:
                calls_to_make = api_calls
                stop = True
            if calls_to_make < 0:
                calls_to_make = 0
            try:
                batch = new_for_omdb_cursor.fetchmany(calls_to_make)
                batch, session_not_found = process_items(batch, session_not_found)
                update_many(batch, 'omdb_data')
                logger.info(f"Inserted {calls_to_make} into OMDB database")
                api_calls -= calls_to_make
                if stop:
                    # Sleep 1hr and repeat
                    close_mysql(conn, new_for_omdb_cursor)
                    logger.info('Hit OMDB API limit. Finishing up.')
                    return
            except Exception as e:
                logger.error(f"Some other erorr while pulling IMDB data: {e}")
                return
    else:
        logger.info('IMDB refresh going on... Finishing up.')


def get_new_imdb_titles(target_table, session_not_found):
    values = ', '.join([str(x) for x in session_not_found])
    conn, cursor = connect_mysql(myimdb=True)
    refresh_interval_date = datetime.datetime.now() - datetime.timedelta(days=REVIEW_INTERVAL_REFRESH)
    q = f"SELECT tconst FROM title_basics WHERE  tconst NOT IN (SELECT imdb_id FROM {target_table} " \
        f"WHERE last_update_omdb > '{str(refresh_interval_date)}')"
    if session_not_found:
        q = q + f" AND tconst NOT IN ({values})"
    cursor.execute(q)
    if cursor.with_rows:
        return conn, cursor
    else:
        return None, None


def get_omdb_api_limit():
    refresh_interval_date = datetime.datetime.now() - datetime.timedelta(days=1)
    conn, cursor = connect_mysql(myimdb=True)
    q = f"SELECT imdb_id FROM  `omdb_data`" \
        f"WHERE last_update_omdb > '{str(refresh_interval_date)}'"
    cursor.execute(q)
    results = cursor.fetchall()
    return OMDB_API_LIMIT - len(results)


def process_items(items, session_not_found):
    new_items = []
    for item in items:
        item = get_omdb(item['tconst'])
        if not item['hit_omdb']:
            session_not_found.append(item['tconst'])
    return new_items, session_not_found


if __name__ == '__main__':
    check_db_myimdb()
    get_omdb_data()
