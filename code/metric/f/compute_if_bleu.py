#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import json
import re
from collections import defaultdict
import sacrebleu
from format import judge


TOKENIZE = "zh"             
USE_EFFECTIVE_ORDER = False  

CH_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

def has_chinese(s: str) -> bool:
    return bool(CH_RE.search(s or ""))

UPPER_RE = re.compile(r"[A-Z]")
LOWER_RE = re.compile(r"[a-z]")

LABEL_RE = re.compile(
    r'^\s*(the\s+transcript(?:ion)?\s*is|the\s+transcription\s*is|asr|result)\s*:\s*',
    flags=re.IGNORECASE,
)
BAD_MARKER_RE = re.compile(r'[\{\}\[\]\<\>]|`{3}|\*\*')

def ifr_constrain(resp: str, ref: str):
    follow = True if judge(ref, resp) == 'positive' else False
    return follow, (resp.strip() if follow else "")

def ifr_upper(resp: str):
    s = resp or ""
    has_lower = bool(LOWER_RE.search(s))
    has_upper = bool(UPPER_RE.search(s))
    follow = (not has_lower) and has_upper
    return follow, (s.strip() if follow else "")

def ifr_lower(resp: str):
    s = resp or ""
    has_upper = bool(UPPER_RE.search(s))
    has_lower = bool(LOWER_RE.search(s))
    follow = (not has_upper) and has_lower
    return follow, (s.strip() if follow else "")

def ifr_prefix(prefix: str, resp: str):
    s = (resp or "")
    p = prefix or ""
    t = s.lstrip()
    follow = t.startswith(p)
    if follow:
        return True, t[len(p):].lstrip()
    return False, ""

def ifr_suffix(suffix: str, resp: str):
    s = (resp or "")
    su = suffix or ""
    t = s.rstrip()
    follow = t.endswith(su)
    if follow:
        return True, t[:len(t)-len(su)].rstrip()
    return False, ""

def ifr_wrap(lrt: str, resp: str):
    s = (resp or "")
    spec = lrt or ""
    if "|" not in spec:
        return False, ""
    left, right = spec.split("|", 1)
    t = s.strip()
    follow = t.startswith(left) and t.endswith(right)
    if follow:
        return True, t[len(left):len(t)-len(right)].strip()
    return False, ""

def ifr_json(resp: str, expected_key: str | None = None):
    try:
        obj = json.loads(resp)
    except Exception:
        return False, ""
    if not isinstance(obj, dict):
        return False, ""
    if expected_key:
        v = obj.get(expected_key)
        return (True, str(v).strip()) if isinstance(v, str) else (False, "")
    for k in ["voice_to_text", "transcript", "transcription", "text", "asr"]:
        v = obj.get(k)
        if isinstance(v, str):
            return True, v.strip()
    parts = [str(v).strip() for v in obj.values() if isinstance(v, str)]
    return (True, " ".join(parts)) if parts else (False, "")

def iter_preds_by_topkey(value):
    if isinstance(value, str):
        yield value, {}
    elif isinstance(value, list):
        for x in value:
            if isinstance(x, dict):
                yield x.get("response", ""), x
            elif isinstance(x, str):
                yield x, {}
    elif isinstance(value, dict):
        for x in value.values():
            if isinstance(x, str):
                yield x, {}

def main():
    if len(sys.argv) < 2:
        print("Usage: python compute_if_bleu.py infer.json")
        sys.exit(1)
    path = sys.argv[1]
    data = json.load(open(path, "r", encoding="utf-8"))

    res = {}

    key_order = []
    total_preds = defaultdict(int)
    if_follow = defaultdict(int)
    gts_by_key = defaultdict(list)
    hyps_by_key = defaultdict(list)

    all_gts, all_hyps = [], []
    all_total = all_follow_cnt = 0

    for item in data:
        ref_text = (item.get("text", "") or "")
        vr = item.get("variation_responses", {}) or {}

        for top_key, value in vr.items():
            if top_key not in key_order:
                key_order.append(top_key)

            for resp, meta in iter_preds_by_topkey(value):
                total_preds[top_key] += 1
                all_total += 1

                if top_key == "constrain":
                    follow, hyp = ifr_constrain(resp, ref_text)
                elif top_key == "upper_case":
                    follow, hyp = ifr_upper(resp)
                elif top_key == "lower_case":
                    follow, hyp = ifr_lower(resp)
                elif top_key == "prefix":
                    follow, hyp = ifr_prefix(meta.get("prefix", ""), resp)
                elif top_key == "suffix":
                    follow, hyp = ifr_suffix(meta.get("suffix", ""), resp)
                elif top_key == "wrap":
                    follow, hyp = ifr_wrap(meta.get("lrt", ""), resp)
                elif top_key == "json":
                    follow, hyp = ifr_json(resp, expected_key=meta.get("key"))
                else:
                    follow, hyp = False, "" 

                if follow and not has_chinese(hyp):
                    follow, hyp = False, ""

                if_follow[top_key] += int(follow)
                all_follow_cnt += int(follow)

                gts_by_key[top_key].append(ref_text.strip())
                hyps_by_key[top_key].append((hyp or "").strip())
                all_gts.append(ref_text.strip())
                all_hyps.append((hyp or "").strip())

    for k in key_order:
        assert total_preds[k] != 0, f"No response in {k}!"
        ifr = 100.0 * if_follow[k] / total_preds[k]
        refs = gts_by_key[k]
        hyps = hyps_by_key[k]
        bleu = sacrebleu.corpus_bleu(
            hyps, [refs], tokenize=TOKENIZE, use_effective_order=USE_EFFECTIVE_ORDER
        ).score if refs else 0.0
        # print(f"[{k}]: IFR -- {ifr:.2f}%; BLEU -- {bleu:.2f}")
        res[k] = {
            "ifr": round(ifr, 2),
            "bleu": round(bleu, 2)
        }

    all_ifr = 100.0 * all_follow_cnt / all_total if all_total else 0.0
    all_bleu = sacrebleu.corpus_bleu(
        all_hyps, [all_gts], tokenize=TOKENIZE, use_effective_order=USE_EFFECTIVE_ORDER
    ).score if all_gts else 0.0
    # print("-" * 64)
    # print(f"[ALL]: IFR -- {all_ifr:.2f}%; BLEU -- {all_bleu:.2f}")
    res['all'] = {
        "ifr": round(all_ifr, 2),
        "bleu": round(all_bleu, 2)
    }

    output = json.dumps(res, indent=2, ensure_ascii=False)
    print(output)

if __name__ == "__main__":
    main()
