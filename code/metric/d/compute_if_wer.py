#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import json
import re
from collections import defaultdict
import jiwer
from normalizers.english import EnglishTextNormalizer

PREFIX_RE = re.compile(r'^\s*the transcript is\s*:\s*', flags=re.IGNORECASE)
file = sys.argv[1]

with open(file, "r", encoding="utf-8") as f:
    data = json.load(f)

# 统计容器
key_order = []
total_preds = defaultdict(int) 
if_follow = defaultdict(int)
gts_by_key = defaultdict(list)
hyps_by_key = defaultdict(list) 

def iter_preds_by_topkey(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for x in value:
            if isinstance(x, str):
                yield x
    elif isinstance(value, dict):
        for x in value.values():
            if isinstance(x, str):
                yield x

def has_transcript_prefix(s: str) -> bool:
    return bool(PREFIX_RE.match(s))

def strip_transcript_prefix(s: str) -> str:
    return PREFIX_RE.sub('', s, count=1)

normalizer = EnglishTextNormalizer()

for item in data:
    ref_text = normalizer(item.get("text", ""))

    vr = item.get("variation_responses", {}) or {}
    for top_key, value in vr.items():
        if top_key not in key_order:
            key_order.append(top_key)

        for pred in iter_preds_by_topkey(value):
            total_preds[top_key] += 1
            if has_transcript_prefix(pred):
                if_follow[top_key] += 1
                hyp_text = normalizer(strip_transcript_prefix(pred))
                # print(hyp_text)
            else:
                hyp_text = ""
                # hyp_text = normalizer(strip_transcript_prefix(pred))
                # if top_key == "default":
                #     print(f"[Base instruction]: {item["base"][0]}")
                #     print(f"[Base constrain]: {item["base"][1]}")
                #     print(f"[Response]: {pred}")

            gts_by_key[top_key].append(ref_text)
            hyps_by_key[top_key].append(hyp_text)

res = {}

for k in key_order:
    assert total_preds[k] != 0, f"No response in {k}!"

    # IFR
    ifr = 100.0 * if_follow[k] / total_preds[k]

    # WER
    gts = gts_by_key[k]
    hyps = hyps_by_key[k]
    assert len(gts) == len(hyps)
    if len(gts) == 0:
        wer_str = "N/A"
    else:
        wer = jiwer.wer(gts, hyps)
        # print(wer)
        wer = wer * 100.0 
        wer_str = f"{wer:.2f}%"
    
    res[k] = {
        "ifr": round(ifr, 2),
        "wer": round(wer, 2)
    }

    # print(f"[{k}]: IFR -- {ifr:.2f}%; WER -- {wer_str}")

all_gts, all_hyps = [], []
for k in key_order:
    all_gts.extend(gts_by_key[k])
    all_hyps.extend(hyps_by_key[k])

if len(all_gts) == 0:
    print("[ALL]: WER -- N/A")
else:
    all_wer = jiwer.wer(all_gts, all_hyps) * 100.0 
    all_ifr = 100.0 * sum(if_follow.values()) / sum(total_preds.values())
    res['all'] = {
        "ifr": round(all_ifr, 2),
        "wer": round(all_wer, 2)
    }
    # print(f"[ALL]: WER -- {all_wer:.2f}%")

output = json.dumps(res, indent=2, ensure_ascii=False)
print(output)