import datetime
import os
import time

import mysql.connector.errors

from utils import get_tmdb
from utils import logger, connect_mysql, close_mysql, update_many, check_db_myimdb

REVIEW_INTERVAL_REFRESH = int(os.getenv('REVIEW_INTERVAL_REFRESH'))
INSERT_RATE = int(os.getenv('INSERT_RATE'))


def get_tmdb_data(session_not_found=[]):
    """
    populates the database with data from TMDB
    session_not_found are the IDs searched for and not found which can be passed to this function
    in order not to search for them again.
    Extra keys:
    Poze, Country, Lang, Ovrw(short descr), score, trailer_link,
    :return:
    """
    # New titles
    logger.info("Downloading data for new TMDB titles")
    tmdb_inserted = 0
    try:
        conn, new_for_tmdb_cursor = get_new_imdb_titles('tmdb_data')
    except mysql.connector.errors.ProgrammingError:
        conn, new_for_tmdb_cursor = None, None
    if new_for_tmdb_cursor:
        while new_for_tmdb_cursor.with_rows:
            try:
                batch = new_for_tmdb_cursor.fetchmany(INSERT_RATE)
                batch, session_not_found = process_items(batch, session_not_found)
                update_many(batch, 'tmdb_data')
                tmdb_inserted += 1
                logger.info(f"Inserted {tmdb_inserted * INSERT_RATE} into TMDB database")
            except Exception as e:
                logger.error(f"Some other erorr while pulling IMDB data: {e}")
                return
        # Sleep 1hr and repeat
        close_mysql(conn, new_for_tmdb_cursor)
        logger.info('Finishing routine...')
    else:
        logger.info('IMDB refresh going on... Finishing routine...')



def get_new_imdb_titles(target_table):
    conn, cursor = connect_mysql(myimdb=True)
    refresh_interval_date = datetime.datetime.now() - datetime.timedelta(days=REVIEW_INTERVAL_REFRESH)
    q = f"SELECT tconst FROM title_basics WHERE  tconst NOT IN (SELECT imdb_id FROM {target_table} " \
        f"WHERE last_update_tmdb > '{str(refresh_interval_date)}')"
    cursor.execute(q)
    if cursor.with_rows:
        return conn, cursor
    else:
        return None, None


def process_items(items, session_not_found):
    new_items = []
    for item in items:
        item = get_tmdb(item['tconst'])
        if not item['hit_tmdb']:
            session_not_found.append(item['imdb_id'])
    return new_items, session_not_found


if __name__ == '__main__':
    check_db_myimdb()
    get_tmdb_data()
