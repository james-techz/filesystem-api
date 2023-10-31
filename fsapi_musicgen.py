from flask_restful import Resource
from flask import request
from fsapi_utils import os_exception_handle, require_token, DATA_DIR, \
    _musicgen, _audiogen, _musicgen_melody
import os 
import pathlib

class MusicGen(Resource):

    @require_token
    @os_exception_handle
    def post(self):
        if ('file_path' not in request.json) or ('input_text' not in request.json):
            return 'Invalid request. file_path and input_text must be defined', 400
        
        output_file = os.path.sep.join([DATA_DIR, request.json['file_path']])
        pathlib.Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        input_text = request.json['input_text']
        duration = request.json.get('duration', 30)
        # model_id = request.json.get('model_id', "facebook/musicgen-small")
        
        async_result = _musicgen.delay(output_file, input_text, duration)
        return {'task_id': async_result.id}
    
class MusicGenMelody(Resource):

    @require_token
    @os_exception_handle
    def post(self):
        if ('file_path' not in request.json) or ('input_text' not in request.json):
            return 'Invalid request. file_path and input_text must be defined', 400
        
        output_file = os.path.sep.join([DATA_DIR, request.json['file_path']])
        pathlib.Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        input_text = request.json['input_text']
        duration = request.json.get('duration', 30)
        MAX_DURATION = 30
        duration = int(MAX_DURATION if duration >= MAX_DURATION else duration)
        
        payload = {
            "inputs": {
                "text": input_text,
            },
            "parameters": {
                'duration': duration,
            }
        }

        if 'input_audio_file' in request.json:
            payload["inputs"]["input_audio_file"] = request.json['input_audio_file']
        
        async_result = _musicgen_melody.delay(output_file, payload)
        return {'task_id': async_result.id}
    
class AudioGen(Resource):

    @require_token
    @os_exception_handle
    def post(self):
        if ('file_path' not in request.json) or ('input_text' not in request.json):
            return 'Invalid request. file_path and input_text must be defined', 400
        
        output_file = os.path.sep.join([DATA_DIR, request.json['file_path']])
        pathlib.Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        input_text = request.json['input_text']
        duration = request.json.get('duration', 5)
        
        async_result = _audiogen.delay(output_file, input_text, duration)
        return {'task_id': async_result.id}

        