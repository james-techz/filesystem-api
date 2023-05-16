# Shamelessly copied from http://flask.pocoo.org/docs/quickstart/

from flask import Flask, request
from flask_restful import Resource, Api, fields, marshal_with
import os 
from base64 import b64encode
from zipfile import ZipFile
from urllib.request import urlopen

app = Flask(__name__)
api = Api(app)

DATA_DIR = '_files'
class ITEMTYPE:
    DIRECTORY = "directory"
    FILE = "file"


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

    def get(self, path = ''):
        full_path = os.path.sep.join([DATA_DIR, path])
        response = {
            'path': path,
            'type': ITEMTYPE.DIRECTORY,
            'children': self._scan_dir(full_path)
        }
        return response


class File(Resource):

    # def _read_file(self, path):
    #     with open(path, 'rb') as f:
    #         return b64encode(f.read()).decode('utf-8')

    def get(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        response = {
            'path': path,
            'type': ITEMTYPE.FILE,
        }
        return response
    
    def delete(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        try:
            os.remove(full_path)
            return None, 204
        except Exception as e:
            return e
        
    def patch(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])

        req = request.json
        if req['new_path'] == None:
            return File().get(path)

        new_path = os.path.sep.join([DATA_DIR, req['new_path']])
        try:
            os.rename(full_path, new_path)
            return File().get(req['new_path'])
        except Exception as e:
            return e

    def post(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        req = request.json

        # create new file by posting content
        if request.args['action'] == None or request.args['action'] == 'upload':
            if req['content'] == None:
                return None, 400
            try:
                with open(full_path, 'w') as f:
                    f.write(req['content'])
                return File().get(path)
            except Exception as e:
                return e
            
        # create new file by scraping from direct URL
        elif request.args['action'] == 'scrape':
            if req['url'] == None:
                return None, 400
            try:
                response = urlopen(req['url'])
                CHUNK = 16 * 1024
                with open(full_path, 'wb') as f:
                    while True:
                        chunk = response.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                return File().get(path)
            except Exception as e:
                return e
            
        # create new file by zip multiple files
        elif request.args['action'] == 'zip':
            if req['files'] == None or not isinstance(req['files'], list):
                return None, 400
            try:
                with ZipFile(full_path, 'w') as zipObj:
                    for _file_path in req['files']:
                        zipObj.write(os.path.sep.join([DATA_DIR, _file_path]))
                return File().get(path) 
            except Exception as e:
                return e
            
        # create new file by concat multiple files
        elif request.args['action'] == 'concat':
            if req['files'] == None or not isinstance(req['files'], list):
                return None, 400
            try:
                with open(full_path, 'wb') as target_f:
                    for _file_path in req['files']:
                        with open(os.path.sep.join([DATA_DIR, _file_path]), 'rb') as src_f:
                            target_f.write(src_f.read())
                resp = File().get(path) 
                return resp
            except Exception as e:
                return e
        else:
            return None, 400
        



# add wrapper: check file/dir existence,  check is file, is dir


api.add_resource(Directory, '/dir/', '/dir/<path:path>')
api.add_resource(File, '/file/<path:path>')



if __name__ == '__main__':
    app.run(host='0.0.0.0', threaded=True, port=5000, debug=False)

