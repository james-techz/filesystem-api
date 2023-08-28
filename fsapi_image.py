from flask_restful import Resource
from flask import request
from fsapi_utils import os_exception_handle, require_token, DATA_DIR, _split_by_interval, _concat_video_files
import os
import errno
import cv2


class ImageOperation(Resource):

    @os_exception_handle
    def _resize_image(self, path, new_path, w, h):
        full_path = os.path.sep.join([DATA_DIR, path])
        full_new_path = os.path.sep.join([DATA_DIR, new_path])
        image = cv2.imread(full_path, cv2.IMREAD_UNCHANGED)

        if image is None:
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT), full_path)
        
        new_image = cv2.resize(image, (w, h), 0, 0, cv2.INTER_CUBIC)
        if cv2.imwrite(full_new_path, new_image):
            return 'Operation succeeded'
        else:
            return 'Operation failed. Please check the server log for more info'
            
    @os_exception_handle
    def _crop_image(self, path, new_path, x1, y1, x2, y2):
        full_path = os.path.sep.join([DATA_DIR, path])
        full_new_path = os.path.sep.join([DATA_DIR, new_path])
        image = cv2.imread(full_path, cv2.IMREAD_UNCHANGED)
        
        if image is None:
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT), full_path)
        
        new_image = image[y1:y2, x1:x2]
        if cv2.imwrite(full_new_path, new_image):
            return 'Operation succeeded'
        else:
            return 'Operation failed. Please check the server log for more info'
        

    @require_token
    @os_exception_handle
    def post(self):
        if 'action' not in request.json:
            return 'Invalid request. No action defined', 400
        
        if request.json['action'] == 'resize':
            path = request.json['path']
            new_path = request.json['new_path']
            width = request.json['width']
            height = request.json['height']

            return self._resize_image(path, new_path, width, height)
        
        if request.json['action'] == 'crop':
            path = request.json['path']
            new_path = request.json['new_path']
            x1, y1, x2, y2 = request.json['x1'], request.json['y1'], request.json['x2'], request.json['y2']

            return self._crop_image(path, new_path, x1, y1, x2, y2)
        else:
            return f'Invalid request. Invalid action: {request.json["action"]}', 400