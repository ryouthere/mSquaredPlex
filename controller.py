from utils import logger
import requests
from settings import API_URL, USER, PASSKEY, MOVIE_HDRO, MOVIE_4K, SOAP_HD, SOAP_4K
from db_tools import check_in_my_movies, check_in_my_torrents, retrieve_bulk_from_dbs, update_my_torrents_db
from pprint import pprint
from utils import connect_mysql

# https://filelist.io/forums.php?action=viewtopic&topicid=120435


def get_latest_torrents(n=100, category=MOVIE_HDRO):
    '''
    returns last n movies from filelist API.
    n default 100
    movie category default HD RO
    '''
    logger.info('Getting RSS feeds')
    r = requests.get(
        url=API_URL,
        params={
            'username': USER,
            'passkey': PASSKEY,
            'action': 'latest-torrents',
            'category': category,
            'limit': n,
        },
    )
    if category == MOVIE_4K:
        return [x for x in r.json() if 'Remux' in x['name']]
    return r.json()


def filter_results(new_movies):
    # Check against my_movies database
    filtered = check_in_my_movies(new_movies)
    # Check against my_torrents_database
    filtered = check_in_my_torrents(filtered)

    return filtered


def run():
    # fetch latest movies
    new_movies = get_latest_torrents(n=5)
    # filter out those already in database with same or better quality and mark
    # the rest if they are already in db
    new_movies = filter_results(new_movies)
    # get if these torrents have been seen before


    # get IMDB, TMDB and OMDB data for these new movies.
    new_movies = retrieve_bulk_from_dbs(new_movies)
    pprint(new_movies)
    # send to user to choose


    # update torrents in my_torrents db
    update_my_torrents_db(new_movies)

    # download and update my_movies db.


















if __name__ == '__main__':
    run()