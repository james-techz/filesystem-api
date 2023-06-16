# Shamelessly copied from http://flask.pocoo.org/docs/quickstart/
from flask import Flask, request
from flask_restful import Api
import os 
from fsapi_utils import *
from fsapi_dir import Directory
from fsapi_file import File
from fsapi_bgtask import BackgroundTask


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

