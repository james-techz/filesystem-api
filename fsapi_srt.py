import grequests
from flask_restful import Resource, request
from flask import request
from bs4 import BeautifulSoup
import os
from fsapi_utils import require_token, os_exception_handle, DATA_DIR
import pathlib
import hashlib
import json

class SRTRequest(Resource):

    def _simplify_srt(self, srt_dir = ''):
        full_path = os.path.sep.join([DATA_DIR, srt_dir])
        if not os.path.exists(full_path) or not os.path.isdir(full_path):
            return {f'error_message': f'srt_dir does not exist or not a directory: {srt_dir}'}, 400
        
        simplified_files = []
        for srt_file in pathlib.Path(full_path).rglob('*.srt'):

            try:
                with open(srt_file, 'r') as f:
                    j = json.loads(f.read())

                for index, s in enumerate(j["segments"]):
                    s.pop('whole_word_timestamps', None)
                    j["segments"][index] = s

                with open(srt_file, 'w') as out_srt:
                    out_srt.write(json.dumps(j, indent=4))
                    simplified_files.append(str(srt_file))
            except Exception as e:
                pass

        return {
            'action': 'simplify',
            'srt_dir': srt_dir,
            'saved_svg_files': list(simplified_files)
        }
    

    @require_token
    @os_exception_handle
    def post(self):
        action = request.json.get( 'action', None)
        srt_dir = request.json.get( 'srt_dir', None)
        if action is None:
            return {f'error_message': 'action must be specified'}, 400
        if srt_dir is None:
            return {f'error_message': 'srt_dir must be specified'}, 400
        
        if action == 'simplify':
            return self._simplify_srt(srt_dir)
        else:
            return {f'error_message': 'action not supported: {action}'}, 400

        