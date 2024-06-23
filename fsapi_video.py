from flask_restful import Resource
from flask import request
from fsapi_utils import os_exception_handle, require_token, DATA_DIR, \
    _split_by_interval, _concat_video_files, _extract_mp3_from_video, _read_video_metadata
import os 
import cv2


class VideoListRequest(Resource):
    @require_token
    @os_exception_handle
    def post(self):
        if 'files' not in request.json:
            return 'Missing key in request body: "files"', 400
        files = request.json['files']
        if not isinstance(files, list):
            return '"files" must be a list', 400

        full_paths = [os.path.sep.join([DATA_DIR, _file]) for _file in files]
        results = []
        for full_path in full_paths:
            # read video file using cv2
            _metadata = _read_video_metadata(full_path)
            results.append(_metadata)
    
        return results
    


class VideoOperation(Resource):

    @require_token
    @os_exception_handle
    def post(self):
        if 'action' not in request.json:
            return 'Invalid request. No action defined', 400
        
        if request.json['action'] == 'split_by_interval':
            async_result = _split_by_interval.delay(request.json)
            return {'task_id': async_result.id}
        if request.json['action'] == 'concat':
            async_result = _concat_video_files.delay(request.json)
            return {'task_id': async_result.id}
        if request.json['action'] == 'extract_audio':
            async_result = _extract_mp3_from_video.delay(request.json)
            return {'task_id': async_result.id}
        else:
            return f'Invalid request. Invalid action: {request.json["action"]}', 400