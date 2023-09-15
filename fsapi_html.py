import grequests
from flask_restful import Resource, request
from flask import request
from bs4 import BeautifulSoup
import os
from fsapi_utils import require_token, os_exception_handle, DATA_DIR
import pathlib
import hashlib

class SVGRequest(Resource):

    SAVED_SVG_DIR = 'saved_svg'

    def _remove_svg(self, html_dir = ''):
        full_path = os.path.sep.join([DATA_DIR, html_dir])
        full_path_saved_svg_dir = os.path.sep.join([full_path, self.SAVED_SVG_DIR])
        pathlib.Path(full_path_saved_svg_dir).mkdir(parents=True, exist_ok=True)

        if not os.path.exists(full_path) or not os.path.isdir(full_path):
            return {f'error_message': f'html_dir does not exist or not a directory: {html_dir}'}, 400
        
        saved_svg_files = set()
        for html_file in pathlib.Path(full_path).rglob('*.html'):
            with open(html_file, 'r') as f:
                html_doc = f.read()

            doc_soup = BeautifulSoup(html_doc, 'html.parser')
            
            svg_tags = doc_soup.find_all('svg')
            
            for svg in svg_tags:
                saved_svg_filename = hashlib.md5(str(svg).encode()).hexdigest()
                saved_svg_path = os.path.sep.join([full_path_saved_svg_dir, f'{saved_svg_filename}.svg'])
                with open(saved_svg_path, 'w') as out_svg:
                    out_svg.write(str(svg))

                replacement_tag = doc_soup.new_tag("a")
                replacement_tag.attrs['href'] = f'{saved_svg_filename}.svg'
                replacement_tag.attrs['class'] = 'svg_replaced'
                svg.replace_with(replacement_tag)
                saved_svg_files.add(f'{saved_svg_filename}.svg')

            with open(html_file, 'w') as out_doc:
                out_doc.write(str(doc_soup))

        return {
            'action': 'svg_remove',
            'html_dir': html_dir,
            'saved_svg_dir': html_dir + '/' + self.SAVED_SVG_DIR,
            'saved_svg_files': list(saved_svg_files)
        }
    

    def _restore_svg(self, html_dir = ''):
        full_path = os.path.sep.join([DATA_DIR, html_dir])
        full_path_saved_svg_dir = os.path.sep.join([full_path, self.SAVED_SVG_DIR])
        if not os.path.exists(full_path) or not os.path.isdir(full_path):
            return {f'error_message': f'html_dir does not exist or not a directory: {html_dir}'}, 400
        if not os.path.exists(full_path_saved_svg_dir) or not os.path.isdir(full_path_saved_svg_dir):
            return {f'error_message': f'saved_svg directory not found: {os.path.sep.join([html_dir, self.SAVED_SVG_DIR])}'}, 400 

        restore_results = []
        for html_file in pathlib.Path(full_path).rglob('*.html'):
            result = {
                'file': str(html_file),
            }

            with open(html_file, 'r') as f:
                html_doc = f.read()

            doc_soup = BeautifulSoup(html_doc, 'html.parser')
            replaced_tags = doc_soup.find_all(name='a', attrs={'class':'svg_replaced'})
            
            replace_results = []
            for a in replaced_tags:
                saved_svg_filename = a.attrs['href']
                saved_svg_path = os.path.sep.join([full_path_saved_svg_dir, f'{saved_svg_filename}'])
                try:
                    with open(saved_svg_path, 'r') as _svg_file:
                        svg_tag = BeautifulSoup(_svg_file.read(), 'html.parser')
                    a.replace_with(svg_tag)

                    replace_results.append({
                        'svg': saved_svg_filename,
                        'status': 'ok',
                    })
                except Exception as e: 
                    replace_results.append({
                        'svg': saved_svg_filename,
                        'status': 'error',
                        'info': str(e)
                    })

            with open(html_file, 'w') as out_doc:
                out_doc.write(str(doc_soup))

            result.update({
                'replace_results': replace_results
            })
        
            restore_results.append(result)

        return {
            'action': 'svg_restore',
            'html_dir': html_dir,
            'saved_svg_dir': html_dir + '/' + self.SAVED_SVG_DIR,
            'restore_result': restore_results
        }



    @require_token
    @os_exception_handle
    def post(self):
        action = request.json.get( 'action', None)
        html_dir = request.json.get( 'html_dir', None)
        if action is None:
            return {f'error_message': 'action must be specified'}, 400
        if html_dir is None:
            return {f'error_message': 'html_dir must be specified'}, 400
        
        if action == 'svg_remove':
            return self._remove_svg(html_dir)
        elif action == 'svg_restore':
            return self._restore_svg(html_dir)
        else:
            return {f'error_message': 'action not supported: {action}'}, 400

        