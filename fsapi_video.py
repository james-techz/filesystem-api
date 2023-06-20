from flask_restful import Resource
from flask import request
from fsapi_utils import os_exception_handle, require_token, DATA_DIR, _split_by_interval, _concat_video_files
import os 
import cv2


def _read_video_metadata(full_path: str):
    # read video file using cv2
    video = cv2.VideoCapture(full_path)
    if not video.isOpened():
        _metadata = {
            'path': full_path,
            'status': 'READ_FAILED',
            'frames': -1,
            'fps': -1,
            'duration_seconds': -1
        }
    else:
        # get video info
        fps = video.get(cv2.CAP_PROP_FPS)
        frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
        duration_seconds = round(frames / fps, 2)
        _metadata = {
            'path': full_path,
            'status': 'READ_SUCCESS',
            'frames': frames,
            'fps': fps,
            'duration_seconds': duration_seconds
        }
    return _metadata


class VideoList(Resource):
    @require_token
    @os_exception_handle
    def get(self):
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
        else:
            return f'Invalid request. Invalid action: {request.json["action"]}', 400