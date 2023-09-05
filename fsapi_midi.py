from flask_restful import Resource
from flask import request
from fsapi_utils import os_exception_handle, require_token, DATA_DIR
import os 
import time
from magenta.models.melody_rnn import melody_rnn_model
from magenta.models.melody_rnn import melody_rnn_sequence_generator
import tensorflow.compat.v1 as tf
from magenta.models.shared import sequence_generator_bundle
import note_seq
from note_seq.protobuf import generator_pb2
# Ref: https://github.com/magenta/magenta/blob/main/magenta/models/melody_rnn/melody_rnn_generate.py#L113

CONFIG = {
    'bundle_file': './attention_rnn.mag',
}

class MIDIGenerator(Resource):

    def _get_bundle(self):
        # Load model file & model config
        bundle = sequence_generator_bundle.read_bundle_file(CONFIG['bundle_file'])
        config_id = bundle.generator_details.id
        config = melody_rnn_model.default_configs[config_id]
        return bundle, config

    @require_token
    @os_exception_handle
    def post(self):
        if 'file_path' not in request.json:
            return 'Invalid request. file_path must be defined', 400
        
        primer_midi = os.path.sep.join([DATA_DIR, request.json['file_path']])
        output_dir = os.path.sep.join([DATA_DIR, request.json.get('output_dir', 'midi_gen')])
        num_steps = request.json.get('num_steps', 128)
        num_outputs = request.json.get('num_outputs', 10)
        temperature = request.json.get('temperature', 1.0)
        beam_size = request.json.get('beam_size', 1)
        branch_factor = request.json.get('branch_factor', 1)
        steps_per_iteration = request.json.get('steps_per_iteration', 1)

        bundle, config = self._get_bundle()

        generator = melody_rnn_sequence_generator.MelodyRnnSequenceGenerator(
            model=melody_rnn_model.MelodyRnnModel(config),
            details=config.details,
            steps_per_quarter=config.steps_per_quarter,
            checkpoint=None,
            bundle=bundle
        )

        # Create output dir
        if not tf.gfile.Exists(output_dir):
            tf.gfile.MakeDirs(output_dir)

        # Set melody configuration
        qpm = note_seq.DEFAULT_QUARTERS_PER_MINUTE
        primer_sequence = note_seq.midi_file_to_sequence_proto(primer_midi)
        if primer_sequence.tempos and primer_sequence.tempos[0].qpm:
            qpm = primer_sequence.tempos[0].qpm

        # Derive the total number of seconds to generate based on the QPM of the
        # priming sequence and the num_steps flag.
        seconds_per_step = 60.0 / qpm / generator.steps_per_quarter
        total_seconds = num_steps * seconds_per_step
        
        # Define generatings section & options
        generator_options = generator_pb2.GeneratorOptions()
        input_sequence = primer_sequence
        last_end_time = max(n.end_time for n in primer_sequence.notes)
        generate_section = generator_options.generate_sections.add(
                start_time=last_end_time + seconds_per_step,
                end_time=total_seconds)
        generator_options.args['temperature'].float_value = temperature
        generator_options.args['beam_size'].int_value = beam_size
        generator_options.args['branch_factor'].int_value = branch_factor
        generator_options.args['steps_per_iteration'].int_value = steps_per_iteration
        tf.logging.debug('input_sequence: %s', input_sequence)
        tf.logging.debug('generator_options: %s', generator_options)

        # Make the generate request num_outputs times and save the output as midi files.
        date_and_time = time.strftime('%Y-%m-%d_%H%M%S')
        digits = len(str(num_outputs))
        midi_paths = []
        for i in range(num_outputs):
            generated_sequence = generator.generate(input_sequence, generator_options)
            midi_filename = '%s_%s.mid' % (date_and_time, str(i + 1).zfill(digits))
            midi_path = os.path.join(output_dir, midi_filename)
            midi_paths.append(midi_path)
            note_seq.sequence_proto_to_midi_file(generated_sequence, midi_path)

        tf.logging.info('Wrote %d MIDI files to %s', num_outputs, output_dir)

        return {'generated_files': [path for path in midi_paths]}, 200