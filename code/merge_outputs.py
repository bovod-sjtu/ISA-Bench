#!/usr/bin/env python3
"""Merge selected metric JSON files into a single consolidated JSON.

Reads the files listed by the user from the `code/output` tree and writes
the merged result to `data/collect_all_metrics.json`. If that file exists
it will be backed up with a .bak timestamp.

Usage: python code/merge_outputs.py
"""
import argparse
import json
import os
import shutil
from datetime import datetime



def find_single_json_in_dir(dirpath):
    """Return the path to the sole .json file in dirpath, or None.

    If there are zero or more than one .json files, print a warning and return None.
    """
    try:
        entries = os.listdir(dirpath)
    except FileNotFoundError:
        print(f'Warning: directory not found: {dirpath}')
        return None
    jsons = [os.path.join(dirpath, f) for f in entries if f.lower().endswith('.json') and os.path.isfile(os.path.join(dirpath, f))]
    if len(jsons) == 1:
        return jsons[0]
    if len(jsons) == 0:
        print(f'Warning: no json files found in {dirpath}')
    else:
        print(f'Warning: multiple json files found in {dirpath}, skipping (need exactly one)')
    return None


def read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f'Warning: file not found: {path}')
        return None
    except json.JSONDecodeError as e:
        print(f'Error decoding JSON {path}: {e}')
        return None


def merge(output_path):
    """Build merged dict using a fixed directory hierarchy at the given path.

    output_path should be a filesystem path. Expected content under that path:
      - d/{asr,gr,ser,aac,s2tt} each contain exactly one json
      - f/{asr,gr,ser,aac,s2tt} each contain exactly one json
      - n/None contains exactly one json
    """
    base = output_path
    merged = {}

    tasks = ['asr', 'gr', 'ser', 'aac', 's2tt']

    if not os.path.isdir(base):
        print(f'Error: output directory not found: {base}')
        return merged

    # If base points to the top-level output/ containing d,f,n, iterate those
    if os.path.isdir(os.path.join(base, 'd')) and os.path.isdir(os.path.join(base, 'f')):
        # read both d and f splits
        for split in ['d', 'f']:
            merged[split] = {}
            split_base = os.path.join(base, split)
            for t in tasks:
                dirpath = os.path.join(split_base, t)
                jp = find_single_json_in_dir(dirpath)
                if jp:
                    data = read_json(jp)
                    if data is not None:
                        merged[split][t] = data

        # handle n under base/output/n/None
        n_base = os.path.join(base, 'n')
        merged['n'] = {}
        if os.path.isdir(n_base):
            sub = 'only'
            subpath = os.path.join(n_base, sub)
            jp = find_single_json_in_dir(subpath)
            if jp:
                data = read_json(jp)
                if data is not None:
                    merged['n'][sub] = data
    else:
        # previous behavior: read tasks directly under base (for e.g., code/output/f)
        for t in tasks:
            dirpath = os.path.join(base, t)
            jp = find_single_json_in_dir(dirpath)
            if jp:
                data = read_json(jp)
                if data is not None:
                    merged[t] = data

        # handle n/None if present
        n_dir = os.path.join(base, 'n')
        if os.path.isdir(n_dir):
            merged['n'] = {}
            sub = 'only'
            subpath = os.path.join(n_dir, sub)
            jp = find_single_json_in_dir(subpath)
            if jp:
                data = read_json(jp)
                if data is not None:
                    merged['n'][sub] = data

    return merged


def write_output(obj, OUT_FILE):
    if os.path.exists(OUT_FILE):
        bak = OUT_FILE + '.bak.' + datetime.now().strftime('%Y%m%d%H%M%S')
        shutil.copy2(OUT_FILE, bak)
        print(f'Backed up existing {OUT_FILE} to {bak}')
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    print(f'Wrote merged metrics to {OUT_FILE}')


def main():
    parser = argparse.ArgumentParser(description='Merge metric JSONs from a provided output PATH into data/collect_all_metrics.json')
    parser.add_argument('--model_output', required=True, help='path to the output folder containing fixed d,f,n hierarchy (e.g. /path/to/output). The basename of this path will be used as the top-level model key in the result.')
    parser.add_argument('--model_name', required=True, help='your model name')
    args = parser.parse_args()
    out_path = args.model_output
    # resolve to absolute path
    out_path = os.path.abspath(out_path)

    merged_body = merge(out_path)
    model_key = args.model_name
    wrapped = {model_key: merged_body}
    # os.path.join(DATA_DIR, 'collect_all_metrics.json')
    OUT_FILE = os.path.join(args.model_output, f"{model_key}_collect_all_metrics.json")
    write_output(wrapped, OUT_FILE)


if __name__ == '__main__':
    main()
