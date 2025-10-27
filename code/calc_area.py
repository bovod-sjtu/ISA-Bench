import numpy as np
import json
import math
from typing import Iterable, List
import sys

def radar_polygon_area(values: Iterable[float], normalize: bool = False, max_value: float = None) -> float:
    vals: List[float] = list(values)
    n = len(vals)
    if n < 3:
        return 0.0  

    if normalize:
        if max_value is None:
            m = max(vals)
        else:
            m = max_value
        if m == 0:
            raise ValueError("Max_value for normalizing = 0!")
        vals = [v / m for v in vals]

    pts = []
    for i, r in enumerate(vals):
        theta = 2 * math.pi * i / n
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        pts.append((x, y))

    area = 0.5 * abs(sum(x0 * y1 - x1 * y0
                         for (x0, y0), (x1, y1) in zip(pts, pts[1:] + [pts[0]])))
    return area

d_labels = ["default", "case", "robust", "semantic_equal", "alter_symbol"]
t_labels = ["constrain", "case", "decoration", "json"]
n_labels = ["2-task", "3-task"]

models = ['desta2.5-audio', 'gemini-2.5-pro', 'qwen2.5_omni', 'gpt-4o-audio-preview', 'qwen2_audio', 'kimi-audio', 'phi4-multimodal-instruct', 'salmonn', 'wavllm']

tasks = ['asr', 'gr', 'ser', 's2tt', 'aac']

eps = 1e-6

metric_feats = {
    'ifr': 'higher',
    'wer': 'lower',
    'acc': 'higher',
    'bleu': 'higher',
    'METEOR': 'higher',
    'CIDEr-D': 'higher',
}

task2metrics = {
    'asr': 'wer',
    'gr': 'acc',
    'ser': 'acc',
    's2tt': 'bleu',
    'aac': 'METEOR',
}

def calc_metrics(model_dict):

    total_d = {
        'case': 0.0,
        'robust': 0.0,
        'semantic_equal': 0.0,
        'default': 0.0,
        'alter_symbol': 0.0,
    }

    d_norm = {key: 0 for key in total_d.keys()}

    for k in model_dict['d'].keys():
        if not 'case' in model_dict['d'][k]:
            model_dict['d'][k]['case'] = {}
            for metric in model_dict['d'][k]['lower_case'].keys():
                model_dict['d'][k]['case'][metric] = round((model_dict['d'][k]['lower_case'][metric] + model_dict['d'][k]['upper_case'][metric]) / 2, 2)

        if not 'robust' in model_dict['d'][k]:
            model_dict['d'][k]['robust'] = {}
            for metric in model_dict['d'][k]['grammar_robust'].keys():
                model_dict['d'][k]['robust'][metric] = round((model_dict['d'][k]['grammar_robust'][metric] + model_dict['d'][k]['syntax_robust'][metric]) / 2, 2)

        if not 'semantic_equal' in model_dict['d'][k]:
            model_dict['d'][k]['semantic_equal'] = {}
            for metric in model_dict['d'][k]['semantic_equal_complex'].keys():
                model_dict['d'][k]['semantic_equal'][metric] = round((model_dict['d'][k]['semantic_equal_complex'][metric] + model_dict['d'][k]['semantic_equal_neutral'][metric] + model_dict['d'][k]['semantic_equal_simple'][metric]) / 3, 2)

        for key in total_d.keys():
            total_d[key] += model_dict['d'][k][key]['ifr']
            d_norm[key] += 1

    total_d = {key: round(total_d[key] / d_norm[key], 2) for key in total_d.keys()}
    model_dict['d']['total'] = total_d

    total_t = {
        'case': 0.0,
        'decoration': 0.0,
        'constrain': 0.0,
        'json': 0.0,
    }

    t_norm = {key: 0 for key in total_t.keys()}

    for k in model_dict['f'].keys():
        if (not 'case' in model_dict['f'][k]) and ('lower_case' in model_dict['f'][k]):
            model_dict['f'][k]['case'] = {}
            for metric in model_dict['f'][k]['lower_case'].keys():
                model_dict['f'][k]['case'][metric] = round((model_dict['f'][k]['lower_case'][metric] + model_dict['f'][k]['upper_case'][metric]) / 2, 2)

        if not 'decoration' in model_dict['f'][k]:
            model_dict['f'][k]['decoration'] = {}
            for metric in model_dict['f'][k]['prefix'].keys():
                model_dict['f'][k]['decoration'][metric] = round((model_dict['f'][k]['prefix'][metric] + model_dict['f'][k]['suffix'][metric] + model_dict['f'][k]['wrap'][metric]) / 3, 2)

        for key in total_t.keys():
            if key in model_dict['f'][k]:
                total_t[key] += model_dict['f'][k][key]['ifr']
                t_norm[key] += 1
    
    total_t = {key: round(total_t[key] / t_norm[key], 2) for key in total_t.keys()}
    model_dict['f']['total'] = total_t

    total_n = {
        '2-task': 0.0,
        '3-task': 0.0,
    }

    if 'only' in model_dict['n']:
        val2task = 0.0
        val3task = 0.0
        for item in model_dict['n']['only']['single-stage']['2-TASK'].values():
            val2task += item['ifr']
        val2task /= len(model_dict['n']['only']['single-stage']['2-TASK'].values())

        for item in model_dict['n']['only']['single-stage']['3-TASK'].values():
            val3task += item['ifr']
        val3task /= len(model_dict['n']['only']['single-stage']['3-TASK'].values())

        total_n['2-task'] = round(val2task, 2)
        total_n['3-task'] = round(val3task, 2)
    model_dict['n']['total'] = total_n

    model_dict['overall'] = {f"D-{k}": total_d[k] for k in total_d.keys()}
    model_dict['overall'].update({f"F-{k}": total_t[k] for k in total_t.keys()})
    model_dict['overall'].update({f"N-{k}": total_n[k] for k in total_n.keys()})


def norm_metrics(data):
    # Normalize metrics to [0, 1] based on whether higher or lower is better
    norm_data = {}

    # d-dimension
    norm_data['d'] = {}
    for label in d_labels:
        norm_data['d'][label] = {}
        for task in tasks:
            metric_id = task2metrics[task]
            model2metrics = {model: data[model]['d'][task][label][metric_id] for model in data.keys() if 'd' in data[model] and task in data[model]['d'] and label in data[model]['d'][task] and metric_id in data[model]['d'][task][label]}
            values = np.array(list(model2metrics.values()))
            if metric_feats[metric_id] == 'higher':
                maxval = np.max(values)
                normed = {model: round(val / (maxval + eps), 2) for model, val in model2metrics.items()}
            else:
                minval = np.min(values)
                normed = {model: round(minval / (val + eps), 2) for model, val in model2metrics.items()}
            norm_data['d'][label][task] = normed
    
    # t-dimension
    norm_data['f'] = {}
    for label in t_labels:
        norm_data['f'][label] = {}
        for task in tasks:
            if label == 'case' and task == 's2tt':
                continue
            metric_id = task2metrics[task]
            model2metrics = {model: data[model]['f'][task][label][metric_id] for model in data.keys() if 'f' in data[model] and task in data[model]['f'] and label in data[model]['f'][task] and metric_id in data[model]['f'][task][label]}
            values = np.array(list(model2metrics.values()))
            # print(label, task)
            if metric_feats[metric_id] == 'higher':
                maxval = np.max(values)
                normed = {model: round(val / (maxval + eps), 2) for model, val in model2metrics.items()}
            else:
                minval = np.min(values)
                normed = {model: round(minval / (val + eps), 2) for model, val in model2metrics.items()}
            norm_data['f'][label][task] = normed

    # n-dimension
    def metric_dict(model):
        return data[model]['n']['only']['single-stage']['2-TASK']

    def metric_dict_alt(model):
        return data[model]['n']['only']['single-stage']['3-TASK']

    norm_data['n'] = {}
    for label in n_labels:
        norm_data['n'][label] = {}
        if label == '2-task':

            asr_metrics = {model: metric_dict(model)['ASR']['wer'] for model in data.keys() if 'n' in data[model] and 'only' in data[model]['n'] and 'single-stage' in data[model]['n']['only'] and '2-TASK' in data[model]['n']['only']['single-stage'] and 'ASR' in data[model]['n']['only']['single-stage']['2-TASK'] and 'wer' in data[model]['n']['only']['single-stage']['2-TASK']['ASR']}

            ser_metrics = {model: metric_dict(model)['SER']['acc'] for model in data.keys() if 'n' in data[model] and 'only' in data[model]['n'] and 'single-stage' in data[model]['n']['only'] and '2-TASK' in data[model]['n']['only']['single-stage'] and 'SER' in data[model]['n']['only']['single-stage']['2-TASK'] and 'acc' in data[model]['n']['only']['single-stage']['2-TASK']['SER']}

            gr_metrics = {model: metric_dict(model)['GR']['acc'] for model in data.keys() if 'n' in data[model] and 'only' in data[model]['n'] and 'single-stage' in data[model]['n']['only'] and '2-TASK' in data[model]['n']['only']['single-stage'] and 'GR' in data[model]['n']['only']['single-stage']['2-TASK'] and 'acc' in data[model]['n']['only']['single-stage']['2-TASK']['GR']}

            asr_values = np.array(list(asr_metrics.values()))
            ser_values = np.array(list(ser_metrics.values()))
            gr_values = np.array(list(gr_metrics.values()))

            asr_minval = np.min(asr_values)
            ser_maxval = np.max(ser_values)
            gr_maxval = np.max(gr_values)

            normed_asr = {model: round(asr_minval / (val + eps), 2) for model, val in asr_metrics.items()}
            normed_ser = {model: round(val / (ser_maxval + eps), 2) for model, val in ser_metrics.items()}
            normed_gr = {model: round(val / (gr_maxval + eps), 2) for model, val in gr_metrics.items()}

            normed = {model: round((normed_asr.get(model, 0) + normed_ser.get(model, 0) + normed_gr.get(model, 0)) / 3, 2) for model in set(list(normed_asr.keys()) + list(normed_ser.keys()) + list(normed_gr.keys()))}
            norm_data['n'][label] = normed
        else:

            asr_metrics = {model: metric_dict_alt(model)['ASR']['wer'] for model in data.keys() if 'n' in data[model] and 'only' in data[model]['n'] and 'single-stage' in data[model]['n']['only'] and '3-TASK' in data[model]['n']['only']['single-stage'] and 'ASR' in data[model]['n']['only']['single-stage']['3-TASK'] and 'wer' in data[model]['n']['only']['single-stage']['3-TASK']['ASR']}

            ser_metrics = {model: metric_dict_alt(model)['SER']['acc'] for model in data.keys() if 'n' in data[model] and 'only' in data[model]['n'] and 'single-stage' in data[model]['n']['only'] and '3-TASK' in data[model]['n']['only']['single-stage'] and 'SER' in data[model]['n']['only']['single-stage']['3-TASK'] and 'acc' in data[model]['n']['only']['single-stage']['3-TASK']['SER']}

            gr_metrics = {model: metric_dict_alt(model)['GR']['acc'] for model in data.keys() if 'n' in data[model] and 'only' in data[model]['n'] and 'single-stage' in data[model]['n']['only'] and '3-TASK' in data[model]['n']['only']['single-stage'] and 'GR' in data[model]['n']['only']['single-stage']['3-TASK'] and 'acc' in data[model]['n']['only']['single-stage']['3-TASK']['GR']}

            asr_values = np.array(list(asr_metrics.values()))
            ser_values = np.array(list(ser_metrics.values()))
            gr_values = np.array(list(gr_metrics.values()))

            asr_minval = np.min(asr_values)
            ser_maxval = np.max(ser_values)
            gr_maxval = np.max(gr_values)

            normed_asr = {model: round(asr_minval / (val + eps), 2) for model, val in asr_metrics.items()}
            normed_ser = {model: round(val / (ser_maxval + eps), 2) for model, val in ser_metrics.items()}
            normed_gr = {model: round(val / (gr_maxval + eps), 2) for model, val in gr_metrics.items()}

            normed = {model: round((normed_asr.get(model, 0) + normed_ser.get(model, 0) + normed_gr.get(model, 0)) / 3, 2) for model in set(list(normed_asr.keys()) + list(normed_ser.keys()) + list(normed_gr.keys()))}
            norm_data['n'][label] = normed

    #  complete 
    # for dim in ['d', 'f']:
    #     for label in norm_data[dim].keys():
    #         for task in norm_data[dim][label].keys():
    #             for model in models:
    #                 # print(dim, label, task, model)
    #                 if not model in norm_data[dim][label][task]:
    #                     norm_data[dim][label][task][model] = 0.0
    for label in norm_data['n'].keys():
        for model in models:
            if not model in norm_data['n'][label]:
                norm_data['n'][label][model] = 0.0

    return norm_data

def norm_area(areas):
    ref_area = areas['ref']
    normed_areas = {key: round(val / ref_area * 100, 1) for key, val in areas.items() if key != 'ref'}
    return normed_areas

def calc_overall_normed(normed_data):
    res = {}
    for label in d_labels:
        model2avg = {model: np.mean([normed_data['d'][label][task][model] for task in tasks if model in normed_data['d'][label][task]]) for model in models}
        res[f"D-{label}"] = {k: round(w, 2) for k, w in model2avg.items()}
    for label in t_labels:
        model2avg = {model: np.mean([normed_data['f'][label][task][model] for task in tasks if task in normed_data['f'][label] and (model in normed_data['f'][label][task])]) for model in models}
        res[f"F-{label}"] = {k: round(w, 2) for k, w in model2avg.items()}
    for label in n_labels:
        res[f"N-{label}"] = normed_data['n'][label]
    return res

# load data
if len(sys.argv) < 2:
    print("Usage: python calc_area.py <tested_model_name>")
    sys.exit(1)
test_model_key = sys.argv[1] 
path = f"egs/{test_model_key}/output/{test_model_key}_collect_all_metrics.json"
isa_orig_path = "../data/collect_all_metrics.json"

with open(isa_orig_path, "r") as f:
    data = json.load(f)

with open(path, "r") as f:
    test_data = json.load(f)
data[test_model_key] = test_data[test_model_key]
models.append(test_model_key)

for model in data.keys():
    calc_metrics(data[model])

normed_data = norm_metrics(data)

overall_labels = [f"D-{s}" for s in d_labels] + [f"F-{s}" for s in t_labels] + [f"N-{s}" for s in n_labels]

data_dict = {}

for model in models:
    if 'overall' in data[model]:
        data_dict[model] = [data[model]['overall'][label] for label in overall_labels]

ref_dims = [100.0] * len(overall_labels)
ref_area = radar_polygon_area(ref_dims, normalize=True, max_value=100)

areas = {'ref': ref_area}

for model in data_dict.keys():
    areas[model] = radar_polygon_area(data_dict[model], normalize=True, max_value=100)

print("Overall IFR Areas Score:")
print(norm_area(areas))

normed_overall = calc_overall_normed(normed_data)

data_dict = {}

for model in models:
    data_dict[model] = [normed_overall[label][model] for label in overall_labels]

ref_dims = [1.0] * len(overall_labels)
ref_area = radar_polygon_area(ref_dims)

areas = {'ref': ref_area}

for model in data_dict.keys():
    areas[model] = radar_polygon_area(data_dict[model])

print("Overall RPS Areas Score:")
print(norm_area(areas))