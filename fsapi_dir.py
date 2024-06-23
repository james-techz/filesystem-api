import grequests
from flask_restful import Resource, request
from fsapi_utils import *
from flask import request, Response
from urllib.request import urlopen
from bs4 import BeautifulSoup, ResultSet
import requests_cache
import requests
import os
from pywebcopy import save_webpage
import cv2
from pathlib import Path


class Directory(Resource):
    def _scan_dir(self, path):
        files = []
        dirs = []
        with os.scandir(path) as items:
            for item in items:
                if item.is_file(): 
                    files.append(item.name)
                elif item.is_dir():
                    dirs.append(item.name)
        return {'dirs': sorted(dirs), 'files': sorted(files)}

    
    def _create_dir_by_crawl(self, path):
        if request.json['url'] == None:
            return None, 400
        
        root_url = request.json['url']
        full_path = os.path.sep.join([DATA_DIR, path])
        os.makedirs(full_path, exist_ok=True)

        page_set = set()
        item_set = set()

        def _get_links_per_page(url):
            # send GET to the target URL
            response = urlopen(url)
            if response.status not in [200]:
                print({'error_message': f'{url}: {response.status} - {response.reason}'}) 

            html = response.read()
            soup = BeautifulSoup(html, 'html.parser')
            tds: ResultSet = soup.find_all('td')
            SKIP_LINKS = ['/', '../', './', '..', '.', '?C=N;O=D', '']

            # construct link lists from HTML table
            for td in tds:
                for child in td.contents:
                    if child.name == 'a':
                        # skip Parent Directory link
                        # and links in blacklist SKIP_LINKS
                        if child.contents[0] == 'Parent Directory' \
                            or child['href'] in SKIP_LINKS:
                            continue
                        
                        href = child['href']
                        # add prefix to relative links to construct a complete URL
                        if href[:4] != 'http':
                            if url[-1] == '/':
                                href = url + href
                            else:
                                href = url + '/' + href
                        # separate directories vs files into each set
                        if href[-1] == '/':
                            page_set.add(href)
                        else:
                            item_set.add(href)
        
        # init the root URL
        page_set.add(root_url)
        while len(page_set) > 0:
            url = page_set.pop()
            _get_links_per_page(url)

        def exception_request(request, exception):
            print(f"{request.url}: {exception}")

        def response_callback(response: Response, *args, **kwargs):
            filepath = str(response.url).replace(root_url, '')
            splits = [part for part in filepath.split('/') if part != '']
            if len(splits) < 1:
                print(f'Cannot determine filename from the URL: {response.url}')
                return response
                                
            if response.status_code == 200:
                parent_path = splits[:-1]
                os.makedirs(os.sep.join([full_path] + parent_path), exist_ok=True)
                full_name = os.path.sep.join([full_path] + splits)
                with open(full_name, 'wb') as f:
                    f.write(response.content)
            else:
                print(f'Error code {response.status_code} getting URL: {response.url}')

            return response

        # smultaneously get the links to speed up
        session = requests_cache.CachedSession(cache_name='my_cache')
        results = grequests.map(
            (grequests.get(u, session=session, callback=response_callback) for u in item_set),
            exception_handler=exception_request,
            size=10,
        )

        return {
            'path': path,
            'type': ITEMTYPE.DIRECTORY,
            'children': self._scan_dir(full_path)
        }


    def _create_dir_by_clone(self, path):
        if request.json['url'] == None:
            return None, 400
        url = request.json['url']
        full_path = os.path.sep.join([DATA_DIR, path])
        os.makedirs(full_path, exist_ok=True)
        # send GET to the target URL to see if we've got invalid response
        session_obj = requests.Session()
        response = session_obj.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code not in [200]:
            return {'error_message_clone': f'{url}: {response.status_code} - {response.reason}'}
        # else, we can start to save the page
        project_folder = os.path.sep.join(full_path.split(os.path.sep)[:-1]) + os.path.sep
        project_name = full_path.split(os.path.sep)[-1]
        save_webpage(
              url=url,
              project_folder=project_folder,
              project_name=project_name,
              bypass_robots=True,
              debug=True,
              open_in_browser=False,
              delay=None,
              threaded=False,
        )
        return self.get(path)

    def _create_dir_by_split(self, path):
        if request.json['file_path'] == None or request.json['size_limit'] == None:
            return None, 400
        full_path = os.path.sep.join([DATA_DIR, path])
        os.makedirs(full_path, exist_ok=True)
        # extract size_limit, file_path, file_name, file extension
        file_path = request.json['file_path']
        file_name = file_path.split(os.path.sep)[-1]
        size_limit = request.json['size_limit']
        [shortname, ext] = file_name.split('.')
        ext = '' if ext is None else f'.{ext}'
        # start reading and writing chunks
        with open(file_path, 'r') as f:
            counter = 1
            while True:
                chunk = f.read(size_limit)
                if len(chunk) == 0:
                    break
                with open(os.path.sep.join([full_path, f'{shortname}-{"%04d" % counter}{ext}']), 'w') as chunk_file:
                    chunk_file.write(chunk)
                if len(chunk) < size_limit:
                    break
                counter += 1
        return self.get(path)

    def _create_dir_by_extract_video(self, path):
        if request.json['file_path'] == None or request.json['time_interval'] == None:
            return None, 400
        full_path = os.path.sep.join([DATA_DIR, path])
        os.makedirs(full_path, exist_ok=True)
        # extract time_interval, file_path, file_name, file extension
        file_path = request.json['file_path']
        file_name = file_path.split(os.path.sep)[-1]
        time_interval = float(request.json['time_interval'])
        shortname = file_name.split('.')[0]
        ext = '.jpg'
        # read video file using cv2
        video = cv2.VideoCapture(file_path)
        if not video.isOpened():
            return {f'error_message': 'cannot read video file {file_path}'}, 500
        # calculate frame indexes to capture
        fps = video.get(cv2.CAP_PROP_FPS)
        nr_frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
        frame_interval = int(fps * time_interval)
        max_frame_interval = int(nr_frames // frame_interval)
        frame_interval_list = [i * frame_interval for i in range(max_frame_interval)]
        # capture and save frames to files
        for (index, frame_index) in enumerate(frame_interval_list):
            video.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = video.read()
            if not ret:
                print(f'Failed to read frame: {frame_index}')
            full_frame_filename = os.path.sep.join([full_path, f'{shortname}-{"%04d" % index}{ext}'])
            cv2.imwrite(full_frame_filename, frame)

        return self.get(path)

    def _create_dir_by_multiple_scrape(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        os.makedirs(full_path, exist_ok=True)

        if 'urls' not in request.json:
            return {
                'error_message': '"urls" not in request body'
            }, 400
        urls = request.json['urls']
        if not isinstance(urls, list):
            return {
                'error_message': '"urls" must be a list'
            }, 400
        
        results = []

        def exception_request(request, exception):
            result = {
                'url': request.url
            }
            result['status'] = 'ERROR'
            result['error_message'] = exception
            results.append(result)

        def response_callback(response: Response, *args, **kwargs):
            filename = str(response.url).split("/")[-1]
            full_filename = os.sep.join([full_path, filename])
            result = {
                'url': response.url
            }

            if response.status_code == 200:
                with open(full_filename, 'wb') as f:
                    f.write(response.content)
                result['status'] = 'SUCCESS'
            else:
                result['status'] = 'ERROR'
                result['error_message'] = f'{response.url}: {response.status_code}'
            results.append(result)

        # smultaneously get the links to speed up
        grequests.map(
            (grequests.get(u, callback=response_callback) for u in urls),
            exception_handler=exception_request,
            size=10,
        )

        return {
            "results": results
        }, 200


    @require_token
    @os_exception_handle
    def get(self, path = ''):
        full_path = os.path.sep.join([DATA_DIR, path])
        response = {
            'path': path,
            'type': ITEMTYPE.DIRECTORY,
            'children': self._scan_dir(full_path)
        }
        return response

    @require_token
    @os_exception_handle
    def post(self, path = ''):
        action = request.args['action'] if 'action' in request.args else None
        if action is None:
            return {f'error_message': 'action must be specified'}, 400
        if action == 'clone':
            return self._create_dir_by_clone(path)
        elif action == 'crawl':
            return self._create_dir_by_crawl(path)
        elif action == 'multiple_scrape':
            return self._create_dir_by_multiple_scrape(path)
        elif action == 'split':
            return self._create_dir_by_split(path)
        elif action == 'video_extract':
            return self._create_dir_by_extract_video(path)
        else:
            return {f'error_message': 'action not supported: {action}'}, 400

        
    @require_token
    @os_exception_handle
    def delete(self, path):
        full_path = os.path.sep.join([DATA_DIR, path])
        if full_path.replace(os.path.sep, '') == FORBIDDEN_DIR.replace(os.path.sep, ''):
            return None, 403
        def rmdir(directory):
            directory = Path(directory)
            for item in directory.iterdir():
                if item.is_dir():
                    rmdir(item)
                else:
                    item.unlink()
            directory.rmdir()
        rmdir(full_path)
        return None, 204
