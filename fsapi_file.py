from flask_restful import Resource
from fsapi_utils import *
from fsapi_utils import _create_file_by_youtube_download, _create_file_by_mp3_concat, \
    _create_wave_from_midi_sf, _create_wave_from_cut
from flask import request, Response
from urllib.request import urlopen
from zipfile import ZipFile
import os 
import pathlib
import shutil
import pretty_midi


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
                        zipObj.write(entry)
                else:
                    zipObj.write(target_full_path)

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
        
        
        