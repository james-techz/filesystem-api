import grequests
import os
from urllib.error import HTTPError
from flask import request
import jwt
from pytube import YouTube, Stream
from celery import shared_task
import json
from pydub import AudioSegment
from moviepy.editor import VideoFileClip, concatenate_videoclips
from urllib.request import urlopen
import cv2
import pathlib
import shutil
import requests
import numpy as np
import scipy
from scipy.io import wavfile
from scipy import interpolate

DATA_DIR = '_files'
PUBLIC_SUBDIR = '_public'
DEBUG = os.environ.get('DEBUG', False)
SECRET = os.environ.get('SECRET', None)
ADMIN_USER = os.environ.get('ADMIN_USER', None)
ADMIN_PASSWD = os.environ.get('ADMIN_PASSWD', None)
JWT_ALGO = 'HS256'
READ_CHUNK_BYTE = 4096

AHK_SERVER = os.environ.get('AHK_SERVER', None)
AHK_SERVER_PORT = os.environ.get('AHK_SERVER_PORT', None)
AHK_SERVER_USER = os.environ.get('AHK_SERVER_USER', None)

# https://u2i0qhej2tuzfzbq.eu-west-1.aws.endpoints.huggingface.cloud
HF_MUSIC_API_URL = os.environ.get('HF_MUSIC_API_URL', None)
HF_MUSIC_API_TOKEN = os.environ.get('HF_MUSIC_API_TOKEN', None)
# https://y7gd5iij1ni4qbj0.eu-west-1.aws.endpoints.huggingface.cloud
HF_AUDIO_API_URL = os.environ.get('HF_AUDIO_API_URL', None)
HF_AUDIO_API_TOKEN = os.environ.get('HF_AUDIO_API_TOKEN', None)

HF_MUSIC_MELODY_API_URL = os.environ.get('HF_MUSIC_MELODY_API_URL', None)
HF_MUSIC_MELODY_API_TOKEN = os.environ.get('HF_MUSIC_MELODY_API_TOKEN', None)


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

    clip_names = []
    with VideoFileClip(source_file_path) as video:
        total_duration = video.duration
        iteration = 0
        start_time = iteration * time_interval
        end_time = start_time + time_interval
        
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

    # multiple request
    if 'items' in request_json:

        items = request_json['items']
        if not isinstance(items, list):
            return 'Invalid request. "items" must be a list', 400

        # validate the items format
        for item in items:
            if item['source_files'] == None or item['target_file'] == None:
                return 'Invalid request. Each item must contain: source_files, target_file', 400
            if not isinstance(item['source_files'], list) or len(item['source_files']) == 0:
                return 'Invalid request. "source_files" must be a non-empty list', 400
        
        self.update_state(state='INPROGRESS', meta={
                'items': items
            })

        for item in items:
            source_file_paths = [os.path.sep.join([DATA_DIR, _file]) for _file in item['source_files']]
            target_file_path = os.path.sep.join([DATA_DIR, item['target_file']])
            pathlib.Path(target_file_path).parent.mkdir(parents=True, exist_ok=True)

            try:
                with [VideoFileClip(file_path) for file_path in source_file_paths] as video_clips:
                    with concatenate_videoclips(video_clips) as final_clip:
                        final_clip.write_videofile(target_file_path, audio=True, audio_codec='aac')
                item['completed'] = 'succeeded'
            except Exception as e:
                item['completed'] = f'failed: {str(e)}'

            self.update_state(state='INPROGRESS', meta={
                    'items': items
                })

        return {
            'status': 'SUCCESS',
            'info': {
                'items': items
            }
        }, 200
    
    # single request
    else:
        
        if request_json['source_files'] == None or request_json['target_file'] == None:
            return 'Invalid request. Request body must contain: source_files, target_file', 400
        if not isinstance(request_json['source_files'], list) or len(request_json['source_files']) == 0:
            return 'Invalid request. "source_files" must be a non-empty list', 400
        
        source_file_paths = [os.path.sep.join([DATA_DIR, _file]) for _file in request_json['source_files']]
        target_file_path = os.path.sep.join([DATA_DIR, request_json['target_file']])
        pathlib.Path(target_file_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            with [VideoFileClip(file_path) for file_path in source_file_paths] as video_clips:
                with concatenate_videoclips(video_clips) as final_clip:
                    final_clip.write_videofile(target_file_path, audio=True, audio_codec='aac')
        except Exception as e:
            return {
                'status': 'FAILED',
                'info': f'ERROR: {str(e)}'
            }, 500

        return {
            'status': 'SUCCEEDED',
            'info': request_json['target_file']
        }, 200

    

@shared_task(bind=True)
def _extract_mp3_from_video(self, request_json):
    if request_json['source_file'] == None or request_json['target_file'] == None:
        return 'Invalid request. Request body must contain: source_file, target_file', 400
    
    source_file_path = os.path.sep.join([DATA_DIR, request_json['source_file']])
    target_file = os.path.sep.join([DATA_DIR, request_json['target_file']])
    if 'bitrate' in request_json:
        bitrate = request_json['bitrate']
    else:
        bitrate = None

    try:
        with VideoFileClip(source_file_path) as video:
            video.audio.write_audiofile(filename=target_file, bitrate=bitrate, write_logfile=True)
        return {
            'status': 'SUCCEEDED',
            'info': target_file
        }, 200
    except Exception as e:
        return {
            'status': 'FAILED',
            'info': str(e)
        }, 500

    


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
    

@shared_task(bind=True)
def _create_wave_from_cut_multiple(self, wav_file, segments):
    full_wav_file = os.path.sep.join([DATA_DIR, wav_file])
    audio = AudioSegment.from_wav(full_wav_file)
    results = []
    for segment in segments:
        output_file = os.path.sep.join([DATA_DIR, segment['filepath']])
        t1 = segment['from_time'] * 1000 # Works in milliseconds
        t2 = segment['to_time'] * 1000
        if t1 < 0:
            segment['result'] = 'from_time is negative of wav file range'
        else:
            pathlib.Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            newAudio = audio[t1:t2]
            newAudio.export(output_file, format="wav") # Exports to a wav file in the current path.
            segment['result'] = 'OK'
        results.append(segment)
        
    return {
        'result': results
    }


@shared_task(bind=True)
def _batch_thumbnail(self, thumbnail_dir_fullpath, videos, images):

    def _download_file(dir_full_path, url):
        filename = url.split('/')[-1]
        try:
            response = urlopen(url)
        except HTTPError as e:
            return {'error_message': f'{url}: {e.code} - {e.reason}'}
        if response.status not in [200]:
            return {'error_message': f'{url}: {response.status} - {response.reason}'}
        CHUNK = 16 * 1024
        file_fp = os.path.sep.join([dir_full_path, filename])
        with open(file_fp, 'wb') as f:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
        return {'path': file_fp}

    tmp_dir_fullpath = thumbnail_dir_fullpath + "_tmp"
    pathlib.Path(tmp_dir_fullpath).mkdir(parents=True, exist_ok=True)

    images_total = len(images)
    videos_total = len(videos)
    images_processed = 0
    videos_processed = 0

    def _check_state():
        image_ratio = 0 if images_total == 0 else int((images_processed / images_total) * 100)
        video_ratio = 0 if videos_total == 0 else int((videos_processed / videos_total) * 100)

        return {
            'images_total': images_total,
            'images_processed': images_processed,
            'images_processed_ratio': image_ratio,
            'videos_total': videos_total,
            'videos_processed': videos_processed,
            'videos_processed_ratio': video_ratio
        }

    self.update_state(state='PROGRESS', meta=_check_state())

    for image_json in images:
        if 'url' not in image_json or 'width' not in image_json:
            image_json.update({'error_message': '"url" and "width" are both required'})
            images_processed += 1
            self.update_state(state='PROGRESS', meta=_check_state())
            continue

        download_result = _download_file(tmp_dir_fullpath, image_json['url'])
        if 'error_message' in download_result:
            image_json.update({'error_message': download_result['error_message']})
            images_processed += 1
            self.update_state(state='PROGRESS', meta=_check_state())
            continue

        image = cv2.imread(download_result['path'], cv2.IMREAD_UNCHANGED)
        if image is None:
            image_json.update({'error_message': f'Read failed: {download_result["path"]}'})
            images_processed += 1
            self.update_state(state='PROGRESS', meta=_check_state())
            continue 

        request_w = image_json['width']
        if len(image.shape) == 2:
            actual_h, actual_w = image.shape
        else:
            actual_h, actual_w, _ = image.shape

        request_h = int((request_w / actual_w) * actual_h)

        resized_image = cv2.resize(image, (request_w, request_h), 0, 0, cv2.INTER_CUBIC)
        resized_image_fp = os.path.sep.join([
            thumbnail_dir_fullpath,
            image_json['url'].split('/')[-1] + '.thumb.jpeg'
        ])
        if cv2.imwrite(resized_image_fp, resized_image):
            image_json.update({'thumb_file': resized_image_fp})
        else:
            image_json.update({'error_message': 'Operation failed. Please check the server log for more info'})

        images_processed += 1
        self.update_state(state='PROGRESS', meta=_check_state())
        pathlib.Path(download_result['path']).unlink(missing_ok=True)
    
    for video_json in videos:
        if 'url' not in video_json or 'width' not in video_json:
            video_json.update({'error_message': '"url" and "width" are both required'})
            videos_processed += 1
            self.update_state(state='PROGRESS', meta=_check_state())
            continue
        ss_mark = video_json.get('ss_mark', 5.0)
        download_result = _download_file(tmp_dir_fullpath, video_json['url'])
        if 'error_message' in download_result:
            video_json.update({'error_message': download_result['error_message']})
            videos_processed += 1
            self.update_state(state='PROGRESS', meta=_check_state())
            continue

        video = cv2.VideoCapture(download_result['path'])
        if not video.isOpened():
            video_json.update({'error_message': f'Read failed, path: {download_result["path"]}'})
            videos_processed += 1
            self.update_state(state='PROGRESS', meta=_check_state())
            continue
        else:
            # get video info
            fps = video.get(cv2.CAP_PROP_FPS)
            frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
            target_frame = ss_mark * fps
            if target_frame > frames:
                target_frame = frames
            video.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = video.read()
            if not ret:
                video_json.update({'error_message': f'Read frame failed, path: {download_result["path"]}, frame: {target_frame}'})
                videos_processed += 1
                self.update_state(state='PROGRESS', meta=_check_state())
                continue

        request_w = video_json['width']
        if len(frame.shape) == 2:
            actual_h, actual_w = frame.shape
        else:
            actual_h, actual_w, _ = frame.shape

        request_h = int((request_w / actual_w) * actual_h)

        resized_image = cv2.resize(frame, (request_w, request_h), 0, 0, cv2.INTER_CUBIC)
        resized_image_fp = os.path.sep.join([
            thumbnail_dir_fullpath,
            video_json['url'].split('/')[-1] + '.thumb.jpeg'
        ])
        if cv2.imwrite(resized_image_fp, resized_image):
            video_json.update({'thumb_file': resized_image_fp})
        else:
            video_json.update({'error_message': 'Operation failed. Please check the server log for more info'})

        videos_processed += 1
        self.update_state(state='PROGRESS', meta=_check_state())
        pathlib.Path(download_result['path']).unlink(missing_ok=True)



    self.update_state(state='SUCCESS', meta={
        'thumbnail_dir': thumbnail_dir_fullpath,
        'videos': videos,
        'images': images
    })
    
    shutil.rmtree(tmp_dir_fullpath)


@shared_task(bind=True)
def _musicgen(self, output_file, input_text, duration):
    try:
        # API_TOKEN = "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"
        API_URL = HF_MUSIC_API_URL
        headers = {
            "Authorization": f"Bearer {HF_MUSIC_API_TOKEN}",
            "Content-Type": "application/json"
        }

        TOKEN_PER_SECOND = 50 # 1500 token = 30s -> 50 token per second
        # This model supports maximum 1500 new token generation
        max_new_tokens = (30 if duration >= 30 else duration) * TOKEN_PER_SECOND
        payload = {
            'inputs': input_text,
            'parameters': {
                'max_new_tokens': max_new_tokens
            }
        }

        response = requests.request("POST", API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            res_json = response.json()
            npy = np.array(res_json[0]["generated_audio"]).astype(np.float32)
            sampling_rate = 32000
            scipy.io.wavfile.write(output_file, rate=sampling_rate, data=npy)
            return {
                'status': 'SUCCEEDED',
                'info': output_file
            }, 200
        else:
            return {
                'status': 'FAILED',
                'info': f'HF query error code: {response.status_code}',
                'message': response.text
            }, 500
    except Exception as e:
        return {
            'status': 'FAILED',
            'info': str(e)
        }, 500
    

@shared_task(bind=True)
def _audiogen(self, output_file, input_text, duration):
    try:
        API_URL = HF_AUDIO_API_URL
        headers = {
            "Authorization": f"Bearer {HF_AUDIO_API_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = {
            'inputs': [input_text],
            'duration': duration
        }

        response = requests.request("POST", API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            res_json = response.json()
            npy = np.array(res_json[0]["generated_audio"][0]).astype(np.float32)
            sampling_rate = 16000
            scipy.io.wavfile.write(output_file, rate=sampling_rate, data=npy)
            return {
                'status': 'SUCCEEDED',
                'info': output_file
            }, 200
        else:
            return {
                'status': 'FAILED',
                'info': f'HF query error code: {response.status_code}',
                'message': response.text
            }, 500
    except Exception as e:
        return {
            'status': 'FAILED',
            'info': str(e)
        }, 500
    


@shared_task(bind=True)
def _musicgen_melody(self, output_file, payload):
    try:
        API_URL = HF_MUSIC_MELODY_API_URL
        headers = {
            "Authorization": f"Bearer {HF_MUSIC_MELODY_API_TOKEN}",
            "Content-Type": "application/json"
        }

        if 'input_audio_file' in payload["inputs"]:
            AUDIO_FILE = os.path.sep.join([DATA_DIR, payload["inputs"].pop('input_audio_file')])
            NEW_SAMPLERATE = 32000
            old_samplerate, old_audio = wavfile.read(AUDIO_FILE)

            if old_samplerate != NEW_SAMPLERATE:
                duration = old_audio.shape[0] / old_samplerate

                time_old  = np.linspace(0, duration, old_audio.shape[0])
                time_new  = np.linspace(0, duration, int(old_audio.shape[0] * NEW_SAMPLERATE / old_samplerate))

                interpolator = interpolate.interp1d(time_old, old_audio.T)
                new_audio = interpolator(time_new).T

                audio = new_audio.T[0,:].tolist()
                payload["inputs"]["audio"] = {
                    "data": audio
                }

        response = requests.request("POST", API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            res_json = response.json()
            npy = np.array(res_json[0]["generated_audio"]).astype(np.float32).T
            sampling_rate = 32000
            scipy.io.wavfile.write(output_file, rate=sampling_rate, data=npy)
            return {
                'status': 'SUCCEEDED',
                'info': output_file
            }, 200
        else:
            return {
                'status': 'FAILED',
                'info': f'HF query error code: {response.status_code}',
                'message': response.text
            }, 500
    except Exception as e:
        return {
            'status': 'FAILED',
            'info': str(e)
        }, 500
