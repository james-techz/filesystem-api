from flask_restful import Resource
from fsapi_utils import *
from fsapi_utils import _create_file_by_youtube_download, _create_file_by_mp3_concat, \
    _create_wave_from_midi_sf, _create_wave_from_cut, _batch_thumbnail, \
    _create_wave_from_cut_multiple
from flask import request, Response
from urllib.request import urlopen
from zipfile import ZipFile
import os 
import pathlib
import shutil
import pretty_midi
# from madmom.features.beats import RNNBeatProcessor
# from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor
# from madmom.features.tempo import TempoEstimationProcessor
# from madmom.features.key import CNNKeyRecognitionProcessor

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
            try:
                with open(full_path, 'rb') as f:
                    pass
                return Response(self.stream_file_content(full_path), mimetype='application/octet-stream')
            except OSError as e:
                return {'error_message': f'{path}: {e.strerror}', }, 400
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
                target_full_path = pathlib.Path(os.path.sep.join([DATA_DIR, _file_path]))
                if target_full_path.is_dir():
                    for entry in target_full_path.rglob('*'):
                        entry_arcname = os.path.sep.join(entry.parts[1:])
                        zipObj.write(filename=entry, arcname=entry_arcname)
                else:
                    arc_name = os.path.sep.join(target_full_path.parts[1:])
                    zipObj.write(target_full_path, arcname=arc_name)

        return File().get(path) 
    
    def _create_file_by_zip_v2(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        if 'files' not in request.json:
            return None, 400
        files = request.json['files']
        if not isinstance(files, list):
            return None, 400
        with ZipFile(full_path, 'x') as zipObj:
            for _file_path in files:
                target_full_path = pathlib.Path(os.path.sep.join([DATA_DIR, _file_path]))
                if target_full_path.is_dir():
                    for entry in target_full_path.rglob('*'):
                        entry_arcname = str(entry).replace(str(target_full_path), '')
                        zipObj.write(filename=entry, arcname=entry_arcname)
                else:
                    arc_name = os.path.sep.join(target_full_path.parts[1:])
                    zipObj.write(target_full_path, arcname=arc_name)

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
        elif request.args['action'] == 'zip_v2':
            return self._create_file_by_zip_v2(path)
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


class TextReplaceRequest (Resource):

    def _text_replace_file(self, job):
        paths = job['paths']
        full_paths = [os.path.sep.join([DATA_DIR, path]) for path in paths]
        phrases = job['phrases']
        for phrase in phrases:
            phrase['replaced_count'] = 0

        MAX_READ_SIZE_BYTES = 1024 * 1024 * 50  
        for full_path in full_paths:
            try:
                with open(full_path, 'r') as f:
                    # read at most 50MB per chunk
                    content = f.read(MAX_READ_SIZE_BYTES)
                    for phrase in phrases:
                        search_term = phrase['search_term']
                        replace_term = phrase['replace_term']

                        if search_term == '':
                            phrase['error_message'] = "search_term must be defined"
                        else:
                            occurs = content.count(search_term)
                            if occurs > 0:
                                content = content.replace(search_term, replace_term)
                            phrase['replaced_count'] += occurs

                with open(full_path, 'w') as f:
                    f.write(content)
            except OSError as e:
                trimmed_filename = os.path.sep.join(e.filename.split(os.path.sep)[1:])
                if 'error_messages' not in job:
                    job['error_messages'] = []
                job['error_messages'].append(f'{trimmed_filename}: {e.strerror}')


    @require_token
    @os_exception_handle
    def post(self):
        if 'jobs' not in request.json:
            return None, 400
        if not isinstance(request.json['jobs'], list):
            return '{"error_message": "\'jobs\' must be a list"}', 400

        jobs = request.json['jobs']
        for job in jobs:
            self._text_replace_file(job)
        response = {
            'jobs': jobs
        }
        return response, 200


class BatchFileCopyRequest (Resource):
    @require_token
    @os_exception_handle
    def post(self):
        if 'files' not in request.json:
            return {"error_message": "'files' not found"}, 400
        
        files = request.json['files']
        if not isinstance(files, list):
            return {"error_message": "'files' must be a list"}, 400


        # read at most 50MB per chunk
        MAX_READ_SIZE_BYTES = 1024 * 1024 * 50  
        results = []
        for item in files:
            full_src_path = os.path.sep.join([DATA_DIR, item['src']])
            full_dest_path = os.path.sep.join([DATA_DIR, item['dest']])
            
            try:
                full_src_path_obj = pathlib.Path(full_src_path)
                full_dest_path_obj = pathlib.Path(full_dest_path)

                if full_src_path_obj.is_dir():
                    try:
                        shutil.copytree(full_src_path, full_dest_path, dirs_exist_ok=True)
                        msg = 'OK' 
                    except OSError as e:
                        msg = e.strerror
                else:
                    with open(full_src_path, 'rb') as f:
                        content = f.read(MAX_READ_SIZE_BYTES)
                        
                        # make sure destination directory path exist
                        full_dest_path_obj.parent.mkdir(parents=True, exist_ok=True)
                        with open(full_dest_path, 'wb') as out:
                            out.write(content)

                    msg = 'OK' 

            except OSError as e:
                msg = e.strerror

            results.append({
                'src': item['src'],
                'dest': item['dest'],
                'result': msg
            })


        response = {
            'results': results
        }
        
        return response, 200



class MIDIRequest(Resource):
    @require_token
    @os_exception_handle
    def post(self, path):

        full_path = os.path.sep.join([DATA_DIR, path])

        if 'notes' not in request.json:
            return {"error_message": "'notes' not found"}, 400
        
        notes = request.json['notes']
        if not isinstance(notes, list):
            return {"error_message": "'notes' must be a list"}, 400
        
        instrument_name = request.json.get('instrument_name', 'cello')

        midi_obj = pretty_midi.PrettyMIDI()
        instrument = pretty_midi.Instrument(program=pretty_midi.instrument_name_to_program(instrument_name))
        for note in notes:
            n_name = note['name']
            n_velocity = note['velocity']
            n_start = note['start']
            n_end = note['end']

            note_number = pretty_midi.note_name_to_number(n_name)
            note = pretty_midi.Note(velocity=n_velocity, pitch=note_number, start=n_start, end=n_end)
            # Add it to our cello instrument
            instrument.notes.append(note)
        # Add the cello instrument to the PrettyMIDI object
        midi_obj.instruments.append(instrument)
        # Write out the MIDI data
        pathlib.Path(full_path).parent.mkdir(parents=True, exist_ok=True)
        midi_obj.write(full_path)

        return File().get(path) 


class WAVRequest(Resource):
    @require_token
    @os_exception_handle
    def post(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        action = request.json.get('action', '')

        if action == 'from_midi':
            if 'midi_file' not in request.json or 'sf_file' not in request.json:
                return {"error_message": "'midi_file' or 'sf_file' not found"}, 400
            
            pathlib.Path(full_path).parent.mkdir(parents=True, exist_ok=True)
            midi_file  = request.json['midi_file']
            sf_file  = request.json['sf_file']

            async_result = _create_wave_from_midi_sf.delay(path, midi_file, sf_file)
            return {"task_id": async_result.id}
        elif action == 'from_wav_cut':
            if 'wav_file' not in request.json \
                or 'from_time' not in request.json \
                or 'to_time' not in request.json:
                    return {"error_message": "'wav_file' or 'from_time' or 'to_time' not found"}, 400
            
            pathlib.Path(full_path).parent.mkdir(parents=True, exist_ok=True)
            wav_file  = request.json['wav_file']
            from_time  = request.json['from_time']
            to_time  = request.json['to_time']

            async_result = _create_wave_from_cut.delay(path, wav_file, from_time, to_time)
            return {"task_id": async_result.id}

        else:
            return {"error_message": "'action' is not defined"}
        
class BatchWAVRequest(Resource):
    @require_token
    @os_exception_handle
    def post(self):
        
        action = request.json.get('action', '')
        if action == 'from_wav_cut_multiple':
            if 'wav_file' not in request.json \
                or 'segments' not in request.json \
                or not isinstance(request.json['segments'], list):
                    return {"error_message": "'wav_file' or 'segments' not found or invalid"}, 400
            
            async_result = _create_wave_from_cut_multiple.delay(request.json['wav_file'], request.json['segments'])
            return {"task_id": async_result.id}

        else:
            return {"error_message": "'action' is not defined or invalid"}
        
class WaveForm(Resource):
    @require_token
    @os_exception_handle
    def post(self):
        action = request.json.get('action', '')
        if action == 'waveform_from_file':
            if 'wav_file' not in request.json \
                or 'output_file' not in request.json:
                return {"error_message": "'wav_file' or 'output_file' not found or invalid"}, 400
            wav_file_path = os.sep.join([DATA_DIR, request.json['wav_file']])
            output_file_path = os.sep.join([DATA_DIR, request.json['output_file']])
            
            pathlib.Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
            import subprocess
            import importlib
            importlib.reload(subprocess)
            completed_process = subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', wav_file_path, '-filter_complex', 'showwavespic', '-frames:v', '1', output_file_path], capture_output=True)
            result = request.json
            if len(completed_process.stderr) > 0:
                result['result'] = completed_process.stderr.decode('utf-8')
            else:
                result['result'] = 'OK'
            return result

        else:
            return {"error_message": "'action' is not defined or invalid"}
    
# class MusicExtract(Resource):

#     @require_token
#     @os_exception_handle
#     def post(self):
#         action = request.json.get('action', '')
#         if action == 'extract_music_info':
#             if 'wav_file' not in request.json:
#                 return {"error_message": "'wav_file' not found or invalid"}, 400

#             wav_file_path = os.sep.join([DATA_DIR, request.json['wav_file']])
#             result = request.json

#             import subprocess
#             import importlib
#             importlib.reload(subprocess)

#             beat_act = RNNBeatProcessor()(wav_file_path)
#             downbeat_act = RNNDownBeatProcessor()(wav_file_path)
#             downbeat_proc = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=60)
#             tempo_proc = TempoEstimationProcessor(fps=60)
#             key_proc = CNNKeyRecognitionProcessor()

#             result = {
#                 "downbeat": downbeat_proc(downbeat_act).tolist(),
#                 "tempo": tempo_proc(beat_act).tolist(), 
#                 "key": key_proc(wav_file_path).tolist(),
#             }
#             return result
#         else:
#             return {"error_message": "'action' is not defined or invalid"}

class BatchThumbnailRequest(Resource):
    @require_token
    @os_exception_handle
    def post(self):
        if 'thumbnail_dir' not in request.json:
            return {'error_message': '"thumbnail_dir" parameter is missing'}, 400
        if 'videos' not in request.json and 'images' not in request.json:
            return {'error_message': '"videos" and "images" parameters are missing'}, 400
        
        videos = request.json.get('videos', [])
        images = request.json.get('images', [])

        if not isinstance(videos, list) or not isinstance(images, list):
            return {'error_message': '"videos" and "images" must be lists'}, 400

        thumbnail_dir_fullpath = os.path.sep.join([DATA_DIR, request.json['thumbnail_dir']])
        pathlib.Path(thumbnail_dir_fullpath).mkdir(parents=True, exist_ok=True)
        async_result = _batch_thumbnail.delay(thumbnail_dir_fullpath, videos, images)
        return {"task_id": async_result.id}

class AHKScript(Resource):
    ROOT_DIR = 'Desktop\\ahkscript'
    DATA_DIR = 'Desktop\\ahkdata'

    @require_token
    @os_exception_handle
    def post(self):
        import subprocess
        import importlib
        importlib.reload(subprocess)

        if 'files' not in request.json:
            return {"error_message": "'files' not found"}, 400
        
        files = request.json['files']
        if not isinstance(files, list):
            return {"error_message": "'files' must be a list"}, 400

        results = []
        for file in files:
            full_path = os.path.sep.join([DATA_DIR, file])
            filename = file.split(os.sep)[-1]
            status = 'OK'
            print(full_path)
            try:
                cmd = ["scp", "-P", AHK_SERVER_PORT, full_path, f"{AHK_SERVER_USER}@{AHK_SERVER}:{AHKScript.ROOT_DIR}\\{filename}"]
                print(cmd)
                print(os.path.abspath(os.path.curdir))
                result = subprocess.run(cmd, capture_output=True)
                print(result.stdout)
                print(result.stderr)
                err = result.stderr.decode('utf-8')
                if err == '':
                    results.append({
                        'file': file,
                        'status': status,
                    })
                else:
                    status = 'ERROR'
                    results.append({
                        'file': file,
                        'status': status,
                        'error_message': err,
                    })

            except OSError as e:
                msg = e.strerror
                status = 'ERROR'
                results.append({
                    'file': file,
                    'status': status,
                    'error_message': msg,
                })

        response = {
            'results': results
        }
        
        return response, 200
    
    def _list(self, directory):
        import subprocess
        import importlib
        importlib.reload(subprocess)
        directory = "" if directory is None else directory
        result = {}
        try:
            cmd = ["ssh", "-p", AHK_SERVER_PORT, f"{AHK_SERVER_USER}@{AHK_SERVER}", f"dir {AHKScript.DATA_DIR}\\{directory}"]
            print(cmd)
            result = subprocess.run(cmd, capture_output=True)
            print(result.stdout)
            print(result.stderr)
            err = result.stderr.decode('utf-8')
            if err == '':
                # only take files and directories lines, without '.' and '..'
                lines = result.stdout.splitlines()
                items = [line.decode("utf-8") for index, line in enumerate(lines) if index >= 7 and index <= len(lines) - 3]
                # filter directories only
                dirs = [item.split(' ')[-1] for item in items if '<DIR>' in item]
                # filter files only
                files = [item.split(' ')[-1] for item in items if '<DIR>' not in item]
                
                result = {
                    'files': files,
                    'dirs': dirs
                }
                
            else:
                status = 'ERROR'
                result = {
                    'status': status,
                    'error_message': err,
                }

        except OSError as e:
            msg = e.strerror
            status = 'ERROR'
            print(msg)
            result = {
                'status': status,
                'error_message': msg,
            }

        response = {
            'result': result
        }
        
        return response, 200
    
    def _get_file(self, filename):
        import subprocess
        import importlib
        importlib.reload(subprocess)
        result = {}
        remote_path = f"{AHKScript.DATA_DIR}\\{filename}"
        local_path = os.sep.join([DATA_DIR, filename])
        try:
            cmd = ["scp", "-P", AHK_SERVER_PORT, "-T", f"{AHK_SERVER_USER}@{AHK_SERVER}:{remote_path}", local_path]
            print(cmd)
            result = subprocess.run(cmd, capture_output=True)
            print(result.stdout)
            print(result.stderr)

            err = result.stderr.decode('utf-8')
            if err == '':
                result = {
                    'file': filename,
                    'status': 'OK'
                }
                
            else:
                result = {
                    'status': 'ERROR',
                    'error_message': err,
                }

        except OSError as e:
            msg = e.strerror
            status = 'ERROR'
            print(msg)
            result = {
                'status': status,
                'error_message': msg,
            }

        response = {
            'result': result
        }
        
        return response, 200

    @require_token
    @os_exception_handle
    def get(self):
        
        if 'action' not in request.args:
            return {"error_message": "'action' not found"}, 400
        
        action = request.args.get('action')
        if action == 'get' and 'file' not in request.args:
            return {"error_message": "'action' is 'get' but 'file' is not specified"}, 400

        if action == 'list':
            return self._list(request.args.get('directory', None))
        elif action == 'get':
            return self._get_file(request.args.get('file', None))
        