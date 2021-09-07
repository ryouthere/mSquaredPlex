#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s32imdbpy.py script.

This script imports the s3 dataset distributed by IMDb into a SQL database.

Copyright 2017-2018 Davide Alberani <da@erlug.linux.it>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
"""

import glob
import gzip
import logging
import os

import sqlalchemy

from utils import setup_logger

from imdb.parser.s3.utils import DB_TRANSFORM, title_soundex, name_soundexes

TSV_EXT = '.tsv.gz'
# how many entries to write to the database at a time.
BLOCK_SIZE = 200000

metadata = sqlalchemy.MetaData()

logger = setup_logger("IMDBdump")


def generate_content(fd, headers, table):
    """Generate blocks of rows to be written to the database.

    :param fd: a file descriptor for the .tsv.gz file
    :type fd: :class:`_io.TextIOWrapper`
    :param headers: headers in the file
    :type headers: list
    :param table: the table that will populated
    :type table: :class:`sqlalchemy.Table`
    :returns: block of data to insert
    :rtype: list
    """
    data = []
    headers_len = len(headers)
    data_transf = {}
    table_name = table.name
    for column, conf in DB_TRANSFORM.get(table_name, {}).items():
        if 'transform' in conf:
            data_transf[column] = conf['transform']
    for line in fd:
        s_line = line.decode('utf-8').strip().split('\t')
        if len(s_line) != headers_len:
            continue
        info = dict(zip(headers, [x if x != r'\N' else None for x in s_line]))
        for key, tranf in data_transf.items():
            if key not in info:
                continue
            info[key] = tranf(info[key])
        if table_name == 'title_basics':
            info['t_soundex'] = title_soundex(info['primaryTitle'])
        elif table_name == 'title_akas':
            info['t_soundex'] = title_soundex(info['title'])
        elif table_name == 'name_basics':
            info['ns_soundex'], info['sn_soundex'], info['s_soundex'] = name_soundexes(info['primaryName'])
        data.append(info)
        if len(data) >= BLOCK_SIZE:
            yield data
            data = []
    if data:
        yield data
        data = []


def build_table(fn, headers):
    """Build a Table object from a .tsv.gz file.

    :param fn: the .tsv.gz file
    :type fn: str
    :param headers: headers in the file
    :type headers: list
    """
    logger.info('Building table for file %s' % fn)
    table_name = fn.replace(TSV_EXT, '').replace('.', '_')
    table_map = DB_TRANSFORM.get(table_name) or {}
    columns = []
    all_headers = set(headers)
    all_headers.update(table_map.keys())
    for header in all_headers:
        col_info = table_map.get(header) or {}
        col_type = col_info.get('type') or sqlalchemy.UnicodeText
        if 'length' in col_info and col_type is sqlalchemy.String:
            col_type = sqlalchemy.String(length=col_info['length'])
        col_args = {
            'name': header,
            'type_': col_type,
            'index': col_info.get('index', False)
        }
        col_obj = sqlalchemy.Column(**col_args)
        columns.append(col_obj)
    return sqlalchemy.Table(table_name, metadata, *columns)


def import_file(fn, engine):
    """Import data from a .tsv.gz file.

    :param fn: the .tsv.gz file
    :type fn: str
    :param engine: SQLAlchemy engine
    :type engine: :class:`sqlalchemy.engine.base.Engine`
    """
    logger.info('Beginning to process file %s' % fn)
    connection = engine.connect()
    count = 0
    nr_of_lines = 0
    fn_basename = os.path.basename(fn)
    with gzip.GzipFile(fn, 'rb') as gz_file:
        gz_file.readline()
        for line in gz_file:
            nr_of_lines += 1
    with gzip.GzipFile(fn, 'rb') as gz_file:
        headers = gz_file.readline().decode('utf-8').strip().split('\t')
        table = build_table(fn_basename, headers)
        try:
            table.drop()
            logger.info('Table %s dropped' % table.name)
        except:
            pass
        insert = table.insert()
        metadata.create_all(tables=[table])
        try:
            for block in generate_content(gz_file, headers, table):
                try:
                    connection.execute(insert, block)
                except Exception as e:
                    logger.error('error processing data: %d entries lost: %s' % (len(block), e))
                    continue
                count += len(block)
                percent = count * 100 / nr_of_lines
        except Exception as e:
            logger.error('error processing data on table %s: %s' % (table.name, e))
        logger.info('Processed file %s: %d entries' % (fn, count))


def import_dir(dir_name, engine):
    """Import data from a series of .tsv.gz files.

    :param dir_name: directory containing the .tsv.gz files
    :type dir_name: str
    :param engine: SQLAlchemy engine
    :type engine: :class:`sqlalchemy.engine.base.Engine`
    """
    for fn in glob.glob(os.path.join(dir_name, '*%s' % TSV_EXT)):
        if not os.path.isfile(fn):
            logger.info('Skipping file %s' % fn)
            continue
        import_file(fn, engine)


def run_import(db_uri, dir_name):
    logger.info('Starting imports')
    print(db_uri)
    engine = sqlalchemy.create_engine(db_uri, encoding='utf-8', echo=False)
    metadata.bind = engine
    import_dir(dir_name, engine)
    logger.info('DB imports finished.')


if __name__ == '__main__':
    from dotenv import load_dotenv

    load_dotenv()

    DB_URI = "postgresql://{u}:{p}@{hp}/{dbname}?charset=utf8".format(
        u='mike',
        p='pass',
        hp=':'.join(['192.168.1.99', '5432']),
        dbname='movielib',
    )

    run_import(DB_URI, r"C:\Users\mihai\Downloads\movielib")
