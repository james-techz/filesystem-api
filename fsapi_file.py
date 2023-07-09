from flask_restful import Resource
from fsapi_utils import *
from fsapi_utils import _create_file_by_youtube_download, _create_file_by_mp3_concat
from flask import request, Response
from urllib.request import urlopen
from zipfile import ZipFile
import os 


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

    
    def _create_file_by_upload(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        if request.json['content'] == None:
            return None, 400
        with open(full_path, 'w') as f:
            f.write(request.json['content'])
        return File().get(path)
    
    def _create_file_by_scrape(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        if 'url' not in request.json:
            return None, 400
        url = request.json['url']
        response = urlopen(url)
        if response.status not in [200]:
            return {'error_message': f'{url}: {response.status} - {response.reason}'}
        CHUNK = 16 * 1024
        with open(full_path, 'wb') as f:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
        return File().get(path)

    def _create_file_by_zip(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        if 'files' not in request.json:
            return None, 400
        files = request.json['files']
        if not isinstance(files, list):
            return None, 400
        with ZipFile(full_path, 'x') as zipObj:
            for _file_path in files:
                zipObj.write(os.path.sep.join([DATA_DIR, _file_path]))
        return File().get(path) 
    
    def _create_file_by_text_concat(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        if 'files' not in request.json:
            return None, 400
        files = request.json['files']
        if not isinstance(files, list):
            return None, 400
        with open(full_path, 'w') as target_f:
            for _file_path in files:
                with open(os.path.sep.join([DATA_DIR, _file_path]), 'r') as src_f:
                    target_f.write(src_f.read())
        return File().get(path) 
    
    

    @require_token
    @os_exception_handle
    def post(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        # create intermediate directories if needed
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        # create new file by posting content
        if request.args['action'] == None or request.args['action'] == 'upload':
            return self._create_file_by_upload(path)
        # create new file by scraping from direct URL
        elif request.args['action'] == 'scrape':
            return self._create_file_by_scrape(path)
        # create new file by zip multiple files
        elif request.args['action'] == 'zip':
            return self._create_file_by_zip(path)
        # create new file by concat multiple files
        elif request.args['action'] == 'concat':
            return self._create_file_by_text_concat(path)
        elif request.args['action'] == 'youtube':
            async_result = _create_file_by_youtube_download.delay(path=path, request_json=request.json)
            return {"task_id": async_result.id}
        elif request.args['action'] == 'concat_mp3':
            async_result = _create_file_by_mp3_concat.delay(path=path, request_json=request.json)
            return {"task_id": async_result.id}
        else:
            return None, 400
        

class TextSearchRequest (Resource):
    @require_token
    @os_exception_handle
    def post(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])

        if 'keyword' not in request.json:
            return None, 400
        keyword = request.json['keyword']

        contain_title = True if str.lower(request.json.get('contain_title', '')) == 'true' else False
        case_sensitive = True if str.lower(request.json.get('case_sensitive', '')) == 'true' else False

        lines = []
        with open(full_path, 'r') as f:
            for index, line in enumerate(f):
                # include first line if contain_title == True
                if index == 0:
                    if contain_title:
                        lines.append(line)
                else:
                    if not case_sensitive:
                        line = str.lower(line)
                        keyword = str.lower(keyword)
                    if keyword in line:
                        lines.append(line) 
                    
        response = {
            'result': ''.join(lines)
        }
        return response
