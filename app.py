# Shamelessly copied from http://flask.pocoo.org/docs/quickstart/

from flask import Flask, request, Response
from flask_restful import Resource, Api
import os 
from zipfile import ZipFile
from urllib.request import urlopen
from urllib.error import HTTPError
import jwt
from pathlib import Path

app = Flask(__name__)
api = Api(app)

DATA_DIR = '_files'
DEBUG = os.environ.get('DEBUG', False)
READ_CHUNK_BYTE = 4096
SECRET = os.environ.get('SECRET', None)
ADMIN_USER = os.environ.get('ADMIN_USER', None)
ADMIN_PASSWD = os.environ.get('ADMIN_PASSWD', None)
JWT_ALGO = 'HS256'
FORBIDDEN_DIR = os.path.sep.join(['_files', '_public'])

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

class Directory(Resource):
    def _scan_dir(self, path):
        files = []
        dirs = []
        with os.scandir(path) as items:
            for item in items:
                if item.is_file(): 
                    files.append(item.name)
                elif item.is_dir():
                    dirs.append(item.name)
        return {'dirs': dirs, 'files': files}

    @require_token
    @os_exception_handle
    def get(self, path = ''):
        full_path = os.path.sep.join([DATA_DIR, path])
        response = {
            'path': path,
            'type': ITEMTYPE.DIRECTORY,
            'children': self._scan_dir(full_path)
        }
        return response

    @require_token
    @os_exception_handle
    def post(self, path = ''):
        full_path = os.path.sep.join([DATA_DIR, path])
        os.makedirs(full_path, exist_ok=True)
        req = request.json

        if req['url'] == None:
            return None, 400

        # send GET to the target URL
        response = urlopen(req['url'])
        if response.status not in [200]:
            return {'error_message': f'{req["url"]}: {response.status} - {response.reason}'}

        # read / parse the target website to get links
        html = response.read()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.find_all('a')
        SKIP_LINKS = ['/', '../', './', '..', '.', '?C=N;O=D', '']
        ONLY_SUFFIX = '.html'

        # construct link lists
        if ONLY_SUFFIX != '':
            filtered_links = [link['href'] for link in links if str(link['href']).endswith(ONLY_SUFFIX) ]
        else:
            filtered_links = [link['href'] for link in links if link['href'] not in SKIP_LINKS ]

        filtered_full_links = [f"{req['url']}/{link}" for link in filtered_links]

        def exception_request(request, exception):
            print(f"{request.url}: {exception}")

        # smultaneously get the links to speed up
        import grequests
        import requests_cache
        session = requests_cache.CachedSession(cache_name='my_cache')
        results = grequests.map(
            (grequests.get(u, session=session, timeout=10) for u in filtered_full_links),
            exception_handler=exception_request,
            size=10,
        )

        # construct file content lists
        file_contents = [r.text if r is not None else '' for r in results]
        
        # write the file content to the directory
        for (name, content) in zip(filtered_links, file_contents):
            full_name = os.path.sep.join([full_path, name])
            with open(full_name, 'w') as f:
                f.write(content)
                
        return {
            'path': path,
            'type': ITEMTYPE.DIRECTORY,
            'children': self._scan_dir(full_path)
        }

    @require_token
    @os_exception_handle
    def delete(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        if full_path.replace(os.path.sep, '') == FORBIDDEN_DIR.replace(os.path.sep, ''):
            return None, 403
        
        def rmdir(directory):
            directory = Path(directory)
            for item in directory.iterdir():
                if item.is_dir():
                    rmdir(item)
                else:
                    item.unlink()
            directory.rmdir()
        
        rmdir(full_path)

        return None, 204

class File(Resource):

    def stream_file_content(self, file_path):
        with open(file_path, 'rb') as f:
            while True:
                buffer = f.read(READ_CHUNK_BYTE)
                yield buffer
                if len(buffer) < READ_CHUNK_BYTE:
                    break

    @require_token
    @os_exception_handle
    def get(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        req_type = request.args['type'] if 'type' in request.args else None
        if req_type == 'content':
            return Response(self.stream_file_content(full_path), mimetype='application/octet-stream')
        else:
            response = {
                'path': path,
                'type': ITEMTYPE.FILE,
            }
            return response
    
    @require_token
    @os_exception_handle
    def delete(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        if full_path.replace(os.path.sep, '') == FORBIDDEN_DIR.replace(os.path.sep, ''):
            return None, 403
        os.remove(full_path)
        return None, 204
        
    @require_token
    @os_exception_handle
    def patch(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        if full_path == FORBIDDEN_DIR:
            return None, 403
        
        req = request.json
        if req['new_path'] == None:
            return File().get(path)

        new_path = os.path.sep.join([DATA_DIR, req['new_path']])
        os.rename(full_path, new_path)
        return File().get(req['new_path'])

    @require_token
    @os_exception_handle
    def post(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        # create intermediate directories if needed
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        req = request.json

        # create new file by posting content
        if request.args['action'] == None or request.args['action'] == 'upload':
            if req['content'] == None:
                return None, 400

            with open(full_path, 'w') as f:
                f.write(req['content'])
            return File().get(path)
            
        # create new file by scraping from direct URL
        elif request.args['action'] == 'scrape':
            if req['url'] == None:
                return None, 400

            response = urlopen(req['url'])
            if response.status not in [200]:
                return {'error_message': f'{req["url"]}: {response.status} - {response.reason}'}

            CHUNK = 16 * 1024
            with open(full_path, 'wb') as f:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
            return File().get(path)
            
        # create new file by zip multiple files
        elif request.args['action'] == 'zip':
            if req['files'] == None or not isinstance(req['files'], list):
                return None, 400
            
            with ZipFile(full_path, 'x') as zipObj:
                for _file_path in req['files']:
                    zipObj.write(os.path.sep.join([DATA_DIR, _file_path]))
            return File().get(path) 

        # create new file by concat multiple files
        elif request.args['action'] == 'concat':
            if req['files'] == None or not isinstance(req['files'], list):
                return None, 400
            
            with open(full_path, 'wb') as target_f:
                for _file_path in req['files']:
                    with open(os.path.sep.join([DATA_DIR, _file_path]), 'rb') as src_f:
                        target_f.write(src_f.read())
            resp = File().get(path) 
            return resp
            
        else:
            return None, 400
        
def initialize():
    # Generate token
    if ADMIN_USER is None or ADMIN_PASSWD is None or SECRET is None:
        print('[ERROR]: Information to generate token is missing')
        os.abort()
    else:
        token = jwt.encode({'ADMIN_USER': ADMIN_USER, 'ADMIN_PASSWD': ADMIN_PASSWD}, SECRET, algorithm=JWT_ALGO)
        print(f'[IMPORTANT]: Token: {token}')

initialize()


api.add_resource(Directory, '/dir/', '/dir/<path:path>')
api.add_resource(File, '/file/<path:path>')



if __name__ == '__main__':
    app.run(host='0.0.0.0', threaded=True, port=5000, debug=DEBUG)

