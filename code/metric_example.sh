# ./examples
# ./examples/f
# ./examples/f/covost2_translation_results.processed.json
# ./examples/f/iemocap_emotion_results.processed.json
# ./examples/f/audiocaps_results.processed.json
# ./examples/f/librispeech_gender_results.processed.json
# ./examples/f/librispeech_asr_results.processed.json
# ./examples/read_json_files.py
# ./examples/d
# ./examples/d/librispeech_asr_results.json
# ./examples/d/audiocaps_results.json
# ./examples/d/librispeech_gender_results.json
# ./examples/d/covost2_translation_results.json
# ./examples/d/iemocap_emotion_results.json
# ./examples/n
# ./examples/n/output_with_responses.json

python metric.py --dim d --task asr --input ./examples/d/librispeech_asr_results.json
python metric.py --dim d --task aac --input ./examples/d/audiocaps_results.json
python metric.py --dim d --task s2tt --input ./examples/d/covost2_translation_results.json
python metric.py --dim d --task ser --input ./examples/d/iemocap_emotion_results.json
python metric.py --dim d --task gr --input ./examples/d/librispeech_gender_results.json
python metric.py --dim f --task asr --input ./examples/f/librispeech_asr_results.processed.json
python metric.py --dim f --task aac --input ./examples/f/audiocaps_results.processed.json
python metric.py --dim f --task s2tt --input ./examples/f/covost2_translation_results.processed.json
python metric.py --dim f --task ser --input ./examples/f/iemocap_emotion_results.processed.json
python metric.py --dim f --task gr --input ./examples/f/librispeech_gender_results.processed.json
python metric.py --dim n --input ./examples/n/output_with_responses.json