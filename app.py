# Shamelessly copied from http://flask.pocoo.org/docs/quickstart/
from fsapi_dir import Directory
from flask import Flask
from flask_restful import Api
import os 
from fsapi_utils import *
from fsapi_file import File, \
    TextSearchRequest, TextReplaceRequest, \
    BatchFileCopyRequest, MIDIRequest, WAVRequest, \
    BatchThumbnailRequest, AHKScript, BatchWAVRequest, \
    WaveForm
from fsapi_video import VideoListRequest, VideoOperation
from fsapi_image import ImageOperation
from fsapi_bgtask import BackgroundTask
from fsapi_html import SVGRequest
from fsapi_srt import SRTRequest
from fsapi_musicgen import MusicGen, AudioGen, MusicGenMelody

app = Flask(__name__)
app.config['CELERY'] = {
    'broker_url': 'amqp://notAnUser:andNotAGoodPass@rabbit-mq:5672/flaskvhost',
    'result_backend': 'redis://redis:',
    'task_ignore_result': False,
    'task_track_started': True,
}
api = Api(app)

        
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
api.add_resource(BackgroundTask, '/bgtask/<string:id>')
api.add_resource(VideoListRequest, '/videolist', '/videolist/')
api.add_resource(VideoOperation, '/videooperation', '/videooperation/')
api.add_resource(TextSearchRequest, '/textsearch/<path:path>')
api.add_resource(TextReplaceRequest, '/textreplace', '/textreplace/')
api.add_resource(BatchFileCopyRequest, '/batchcopy', '/batchcopy/')
api.add_resource(MIDIRequest, '/midi/<path:path>')
api.add_resource(WAVRequest, '/wav/<path:path>')
api.add_resource(BatchWAVRequest, '/batchwav', '/batchwav/')
api.add_resource(WaveForm, '/waveform', '/waveform/')
api.add_resource(ImageOperation, '/image', '/image/')
api.add_resource(BatchThumbnailRequest, '/batchthumbnail', '/batchthumbnail/')
api.add_resource(SVGRequest, '/svgrequest', '/svgrequest/')
api.add_resource(SRTRequest, '/srtrequest', '/srtrequest/')
api.add_resource(MusicGen, '/musicgen', '/musicgen/')
api.add_resource(AudioGen, '/audiogen', '/audiogen/')
api.add_resource(MusicGenMelody, '/musicgenmelody', '/musicgenmelody/')
api.add_resource(AHKScript, '/ahkscript', '/ahkscript/')

from celery import Celery, Task

def celery_init_app(app: Flask):
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config['CELERY'])
    celery_app.set_default()
    app.extensions['celery'] = celery_app
    return celery_app

celery_app = celery_init_app(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=DEBUG)

