
# stdlib imports
import logging
import time
from multiprocessing import Pool

from apt_repoman.connection import Connection

LOG = logging.getLogger(__name__)


def write_path(bucket_name, path, data, profile_name='', role_arn=''):
    now = time.time()
    connection = Connection(
        profile_name=profile_name,
        role_arn=role_arn)
    s3 = connection.session.resource('s3')
    LOG.info('writing s3://%s/%s', bucket_name, path)
    if path.endswith('gz'):
        content_type = 'binary/octet-stream'
    else:
        content_type = 'text/plain'

    k = s3.Object(bucket_name, path)
    elapsed = time.time() - now
    LOG.debug('wrote %s/%s in %f sec', bucket_name, path, elapsed)
    result = k.put(Body=data, ContentType=content_type)
    return path, result


def func_star(args):
    """Convert `f([1,2])` to `f(1,2)`"""
    return write_path(*args)


def write_paths(bucket_name, tups, threads=0):
    if threads == 0:
        threads = len(tups)
    LOG.debug('threads: %s', threads)
    pool = Pool()
    args = [(bucket_name,) + tup for tup in tups]
    now = time.time()
    LOG.debug('dispatching writers')
    results = pool.map(func_star, args)
    LOG.debug('all dispatched in %s seconds', time.time() - now)
    now = time.time()
    LOG.debug('closing writer pool')
    pool.close()
    LOG.debug('closed in %s seconds', time.time() - now)
    now = time.time()
    LOG.debug('joining writer pool')
    pool.join()
    LOG.debug('joined in %s seconds', time.time() - now)
    LOG.info('done writing to s3')
    return results
