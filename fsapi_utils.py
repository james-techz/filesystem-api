import os
from urllib.error import HTTPError
from flask import request
import jwt
from pytube import YouTube

DATA_DIR = '_files'
PUBLIC_SUBDIR = '_public'
DEBUG = os.environ.get('DEBUG', False)
SECRET = os.environ.get('SECRET', None)
ADMIN_USER = os.environ.get('ADMIN_USER', None)
ADMIN_PASSWD = os.environ.get('ADMIN_PASSWD', None)
JWT_ALGO = 'HS256'
READ_CHUNK_BYTE = 4096

FORBIDDEN_DIR = os.path.sep.join([DATA_DIR, PUBLIC_SUBDIR])

class ITEMTYPE:
    DIRECTORY = 'directory'
    FILE = 'file'

def os_exception_handle(f):
    def _inner_func(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except HTTPError as e:
            return {'error_message': f'{e.filename}: {e.code}: {e.msg}', }, 400
        except OSError as e:
            trimmed_filename = os.path.sep.join(e.filename.split(os.path.sep)[1:])
            return {'error_message': f'{trimmed_filename}: {e.strerror}', }, 400
    return _inner_func

def require_token(f):
    def _inner_func(*args, **kwargs):
        token = request.headers.get('token', None)
        if token is None:
            return 'Header token missing', 401
        else:
            options = {
                'require': ['ADMIN_USER', 'ADMIN_PASSWD']
            }
            try:
                entity = jwt.decode(token, SECRET, algorithms=JWT_ALGO, options=options)
                if entity['ADMIN_USER'] == ADMIN_USER and entity['ADMIN_PASSWD'] == ADMIN_PASSWD:
                    return f(*args, **kwargs)
                else:
                    return 'Invalid token', 401
            except jwt.exceptions.InvalidTokenError:
                return 'Invalid token', 401
    return _inner_func


from celery import shared_task
import json

@shared_task
def _create_file_by_youtube_download(path, request_json):
    full_path = os.path.sep.join([DATA_DIR, path])

    if 'url' not in request_json:
        return None, 400
    url = request_json['url']
    min_res = int(request_json['min_res'])
    # read available streams  for the video
    streams = YouTube(url).streams \
        .filter(progressive=True) \
        .order_by('resolution')
    # download the smallest stream which satisfy minimal resolution
    available_res = []
    for _stream in streams:
        _stream_res = int(_stream.resolution[:-1])
        available_res.append(_stream_res)
        if _stream_res >= min_res:
            _stream.download(
                output_path=os.path.dirname(full_path),
                filename=os.path.basename(full_path),
            )
            # import time
            # time.sleep(30)
            return {
                'path': path,
                'type': ITEMTYPE.FILE,
            }
    
    # if there's no stream satisfing the filter condition
    return json.dumps({'error_message': f'Resolution resquested not found. Requested >= {min_res}. Available: {available_res}'})