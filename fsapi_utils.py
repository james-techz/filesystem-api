import os
from urllib.error import HTTPError
from flask import request
import jwt
from pytube import YouTube, Stream
from celery import shared_task
import json
from pydub import AudioSegment
from moviepy.editor import VideoFileClip, concatenate_videoclips

DATA_DIR = '_files'
PUBLIC_SUBDIR = '_public'
DEBUG = os.environ.get('DEBUG', False)
SECRET = os.environ.get('SECRET', None)
ADMIN_USER = os.environ.get('ADMIN_USER', None)
ADMIN_PASSWD = os.environ.get('ADMIN_PASSWD', None)
JWT_ALGO = 'HS256'
READ_CHUNK_BYTE = 4096

FORBIDDEN_DIR = os.path.sep.join([DATA_DIR, PUBLIC_SUBDIR])

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


@shared_task(bind=True)
def _create_file_by_youtube_download(self, path, request_json):
    full_path = os.path.sep.join([DATA_DIR, path])

    if 'url' not in request_json:
        return 'Invalid request. Request body must contain: url', 400
    
    url = request_json['url']
    min_res = int(request_json['min_res'])

    def on_youtube_download_progress(stream: Stream, chunk: bytes, bytes_remaining: int):
        filesize_bytes = stream.filesize
        self.update_state(state='PROGRESS', meta={
            'total_bytes': filesize_bytes,
            'bytes_remaining': bytes_remaining,
            'progress': round((filesize_bytes - bytes_remaining) / filesize_bytes, 2)
        })
        
    # read available streams  for the video
    streams = YouTube(
            url=url,
            on_progress_callback=on_youtube_download_progress
        ).streams \
        .filter(progressive=True) \
        .order_by('resolution')
    # download the smallest stream which satisfy minimal resolution
    available_res = []
    for _stream in streams:
        _stream_res = int(_stream.resolution[:-1])
        available_res.append(_stream_res)
        if _stream_res >= min_res:
            _stream.download(
                output_path=os.path.dirname(full_path),
                filename=os.path.basename(full_path),
            )
            return {
                'path': path,
                'type': ITEMTYPE.FILE,
            }
    
    # if there's no stream satisfing the filter condition
    return json.dumps({'error_message': f'Resolution resquested not found. Requested >= {min_res}. Available: {available_res}'})




@shared_task(bind=True)
def _create_file_by_mp3_concat(self, path, request_json):
    # fix the problem of grequests patching subprocess module
    # by reloading the original subprocess module
    import subprocess
    import importlib
    importlib.reload(subprocess)

    full_path = os.path.sep.join([DATA_DIR, path])
    if 'files' not in request_json:
        return 'Invalid request. Request body must contain: files', 400
    
    files = request_json['files']
    if not isinstance(files, list) or len(files) == 0:
        return 'Invalid request. "files" must be a non-empty list', 400
    
    files = [os.path.sep.join([DATA_DIR, _file]) for _file in files]
    _result_file = None
    for _file in files:
        if _result_file == None:
            _result_file = AudioSegment.from_mp3(_file)
        else:
            _result_file = _result_file.append(AudioSegment.from_mp3(_file))
    _result_file.export(full_path, format="mp3")
    return {
        'path': path,
        'type': ITEMTYPE.FILE,
    }


@shared_task(bind=True)
def _split_by_interval(self, request_json):
    if request_json['source_file'] == None or request_json['target_directory'] == None or request_json['time_interval'] == None:
        return 'Invalid request. Request body must contain: source_file, target_directory, time_interval', 400
    
    source_file_path = os.path.sep.join([DATA_DIR, request_json['source_file']])
    target_directory = os.path.sep.join([DATA_DIR, request_json['target_directory']])
    os.makedirs(target_directory, exist_ok=True)
    time_interval = float(request_json['time_interval'])

    # extract time_interval, file_path, file_name, file extension
    source_file_name = source_file_path.split(os.path.sep)[-1]
    shortname = source_file_name.split('.')[0]
    ext = '.mp4'

    video = VideoFileClip(source_file_path)
    total_duration = video.duration
    
    iteration = 0
    start_time = iteration * time_interval
    end_time = start_time + time_interval
    clip_names = []
    while start_time <= total_duration:
        if end_time > total_duration:
            end_time = total_duration
        clip = video.subclip(start_time, end_time)
        clip_name = f'{shortname}-{"%04d" % (iteration,)}{ext}'
        clip_names.append(clip_name)
        clip_path = os.path.sep.join([target_directory, clip_name])
        clip.write_videofile(clip_path, audio=True, audio_codec='aac')
        iteration += 1
        start_time = iteration * time_interval
        end_time = start_time + time_interval
        print("-----------------???-----------------")

    return {
        'status': 'SUCCEEDED',
        'info': clip_names
    }, 200


@shared_task(bind=True)
def _concat_video_files(self, request_json):
    if request_json['source_files'] == None or request_json['target_file'] == None:
        return 'Invalid request. Request body must contain: source_files, target_file', 400
    if not isinstance(request_json['source_files'], list) or len(request_json['source_files']) == 0:
        return 'Invalid request. "source_files" must be a non-empty list', 400
    
    source_file_paths = [os.path.sep.join([DATA_DIR, _file]) for _file in request_json['source_files']]
    target_file_path = os.path.sep.join([DATA_DIR, request_json['target_file']])

    video_clips = [VideoFileClip(file_path) for file_path in source_file_paths]
    final_clip = concatenate_videoclips(video_clips)
    final_clip.write_videofile(target_file_path, audio=True, audio_codec='aac')

    return {
        'status': 'SUCCEEDED',
        'info': request_json['target_file']
    }, 200



@shared_task(bind=True)
def _create_wave_from_midi_sf(self, path, midi_file, sf_file):
    # fix the problem of grequests patching subprocess module
    # by reloading the original subprocess module
    import subprocess
    import importlib
    importlib.reload(subprocess)

    full_path = os.path.sep.join([DATA_DIR, path])
    full_midi_path = os.path.sep.join([DATA_DIR, midi_file])
    full_sf_path = os.path.sep.join([DATA_DIR, sf_file])
    completed_process = subprocess.run(["fluidsynth", "-Twav", f"-F{full_path}", full_sf_path, full_midi_path], capture_output=True)

    return {
        'path': path,
        'type': ITEMTYPE.FILE,
        'process_return_code':  completed_process.returncode,
        'process_stdout': completed_process.stdout.decode('utf-8'),
        'process_stderr': completed_process.stderr.decode('utf-8')
    }


@shared_task(bind=True)
@os_exception_handle
def _create_wave_from_cut(self, path, wav_file, from_time, to_time):
    
    full_path = os.path.sep.join([DATA_DIR, path])
    full_wav_file = os.path.sep.join([DATA_DIR, wav_file])
    t1 = from_time * 1000 #Works in milliseconds
    t2 = to_time * 1000
    newAudio = AudioSegment.from_wav(full_wav_file)
    newAudio = newAudio[t1:t2]
    if t1 < 0:
        return {
            'error_message': 'from_time is negative of wav file range'
        }
    else:
        newAudio.export(full_path, format="wav") #Exports to a wav file in the current path.

        return {
            'path': path,
            'type': ITEMTYPE.FILE
        }