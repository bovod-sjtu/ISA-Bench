#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Tuple, Union

from aac_metrics.functional import meteor, cider_d, rouge_l
from aac_metrics.utils.tokenization import preprocess_mono_sents, preprocess_mult_sents

LABEL_RE = re.compile(
    r'^\s*(the\s+audio\s+caption\s+is|caption|result|description)\s*:\s*',
    flags=re.IGNORECASE,
)
BAD_MARKER_RE = re.compile(r'[\{\}\[\]\<\>]|`{3}|\*\*')  # { } [ ] < >  ```  **

UPPER_RE = re.compile(r"[A-Z]")
LOWER_RE = re.compile(r"[a-z]")

def is_repeated_sentence(sentence: str) -> bool:
    normalized = re.sub(r"[^\w\s]", " ", sentence).lower()
    words = normalized.split()
    n = len(words)
    if n < 2:
        return False
    
    for size in range(1, n // 2 + 1):
        if n % size == 0:
            unit = words[:size]
            if unit * (n // size) == words:
                return True
    return False

def ifr_constrain(resp: str) -> Tuple[bool, str]:

    candidates = [
        'there is',
        'the clip',
        'the audio',
        'the recording',
        'no audio',
        'there are',
        'sorry',
        'can\'t',
        'caption',
        'label',
        ':',
        'the scene',
        'this is',
        'element',
        'the soundscape',
        'the text',
        'the speaker',
        'capture',
        '?',
    ]

    def judge(item):
        flag = True
        for cand in candidates:
            if (cand.lower() in item.lower()) or is_repeated_sentence(item):
                flag = False
                break
        return flag
    follow = judge(resp)
    return follow, (resp.strip() if follow else "")

def ifr_upper(resp: str) -> Tuple[bool, str]:
    s = resp or ""
    has_lower = bool(LOWER_RE.search(s))
    has_upper = bool(UPPER_RE.search(s))
    follow = (not has_lower) and has_upper
    return follow, (s.strip() if follow else "")

def ifr_lower(resp: str) -> Tuple[bool, str]:
    s = resp or ""
    has_upper = bool(UPPER_RE.search(s))
    has_lower = bool(LOWER_RE.search(s))
    follow = (not has_upper) and has_lower
    return follow, (s.strip() if follow else "")

def ifr_prefix(prefix: str, resp: str) -> Tuple[bool, str]:
    s = (resp or "")
    p = prefix or ""
    t = s.lstrip()
    if t.startswith(p):
        return True, t[len(p):].lstrip()
    return False, ""

def ifr_suffix(suffix: str, resp: str) -> Tuple[bool, str]:
    s = (resp or "")
    su = suffix or ""
    t = s.rstrip()
    if t.endswith(su):
        return True, t[:len(t)-len(su)].rstrip()
    return False, ""

def ifr_wrap(lrt: str, resp: str) -> Tuple[bool, str]:
    s = (resp or "")
    spec = lrt or ""
    if "|" not in spec:
        return False, ""
    left, right = spec.split("|", 1)
    t = s.strip()
    if t.startswith(left) and t.endswith(right):
        return True, t[len(left):len(t)-len(right)].strip()
    return False, ""

def ifr_json(resp: str, expected_key: str | None = None) -> Tuple[bool, str]:
    try:
        obj = json.loads(resp)
    except Exception:
        return False, ""

    def from_obj(d: Dict[str, Any]) -> Union[str, None]:
        if expected_key and isinstance(d.get(expected_key), str):
            return d[expected_key].strip()
        return None

    if isinstance(obj, dict):
        v = from_obj(obj)
        return (True, v) if v else (False, "")
    if isinstance(obj, list):
        parts = []
        for x in obj:
            if isinstance(x, dict):
                v = from_obj(x)
                if v:
                    parts.append(v)
        if parts:
            return True, " ".join(parts)
    return False, ""

def load_json_either_array_or_ndjson(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
        else:
            raise ValueError("Top-level JSON must be array or object.")
    except json.JSONDecodeError:
        out = []
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    out.append(json.loads(ln))
        return out

def iter_preds_with_meta(value):
    if isinstance(value, str):
        yield value, {}
    elif isinstance(value, list):
        for x in value:
            if isinstance(x, dict):
                yield x.get("response", ""), x
            elif isinstance(x, str):
                yield x, {}
    elif isinstance(value, dict):
        for v in value.values():
            if isinstance(v, str):
                yield v, {}
            elif isinstance(v, dict):
                yield v.get("response", ""), v

def sanitize(s: str) -> str:
    s = s.replace("\n", " ")
    s = re.sub(r"[\r\u000B\u000C\u0085\u2028\u2029]+", " ", s)
    return s.strip()


def score_variation(cands: List[str], mult_refs: List[List[str]]) -> Dict[str, Union[float, str]]:
    c_proc = preprocess_mono_sents([sanitize(c) for c in cands])
    r_proc = preprocess_mult_sents([[sanitize(r) for r in rs] for rs in mult_refs])

    out: Dict[str, Union[float, str]] = {}
    try:
        m_corpus, _ = meteor(c_proc, r_proc)
        out["METEOR"] = float(m_corpus["meteor"].item())
    except Exception:
        out["METEOR"] = "N/A"

    c_corpus, _ = cider_d(c_proc, r_proc)
    r_corpus, _ = rouge_l(c_proc, r_proc)
    out["CIDEr-D"] = float(c_corpus["cider_d"].item())
    out["ROUGE-L"] = float(r_corpus["rouge_l"].item())
    return out

def main(infer_path: str):
    data = load_json_either_array_or_ndjson(infer_path)

    res = {}

    key_order = []
    total_preds = defaultdict(int)   
    if_follow = defaultdict(int)    

    var2cands: Dict[str, List[str]] = defaultdict(list)
    var2refs:  Dict[str, List[List[str]]] = defaultdict(list)

    # overall
    all_cands, all_refs = [], []
    all_total = all_follow_cnt = 0

    for item in data:
        refs_raw = item.get("text", "")
        refs = [r.strip() for r in str(refs_raw).split("|") if r.strip()]
        if not refs:
            continue

        vr = item.get("variation_responses", {}) or {}
        for top_key, value in vr.items():
            if top_key not in key_order:
                key_order.append(top_key)

            for resp, meta in iter_preds_with_meta(value):
                total_preds[top_key] += 1
                all_total += 1

                if top_key == "constrain":
                    follow, body = ifr_constrain(resp)
                elif top_key == "upper_case":
                    follow, body = ifr_upper(resp)
                elif top_key == "lower_case":
                    follow, body = ifr_lower(resp)
                elif top_key == "prefix":
                    follow, body = ifr_prefix(meta.get("prefix", ""), resp)
                elif top_key == "suffix":
                    follow, body = ifr_suffix(meta.get("suffix", ""), resp)
                elif top_key == "wrap":
                    follow, body = ifr_wrap(meta.get("lrt", ""), resp)
                elif top_key == "json":
                    follow, body = ifr_json(resp, expected_key=meta.get("key"))
                else:
                    follow, body = False, ""

                if_follow[top_key] += int(follow)
                all_follow_cnt += int(follow)

                cand_eval = body if follow else ""
                var2cands[top_key].append(cand_eval)
                var2refs[top_key].append(refs)

                all_cands.append(cand_eval)
                all_refs.append(refs)

    # print("== Audio Caption Metrics by Variation ==")
    header = "{:<28} {:>8} {:>8} {:>9} {:>12} {:>12} {:>12}"
    row    = "{:<28} {:>8} {:>8} {:>8.1f}% {:>12} {:>12} {:>12}"
    # print(header.format("variation", "samples", "follow", "IFR", "METEOR", "CIDEr-D", "ROUGE-L"))

    for k in key_order:
        tot = total_preds[k]
        if tot == 0:
            continue
        follow = if_follow[k]
        ifr = 100.0 * follow / tot
        scores = score_variation(var2cands[k], var2refs[k])
        m = scores["METEOR"]
        m_str = f"{m:.4f}" if isinstance(m, float) else "N/A"
        # print(row.format(
        #     k[:28], tot, follow, ifr,
        #     m_str, f"{scores['CIDEr-D']:.4f}", f"{scores['ROUGE-L']:.4f}"
        # ))
        res[k] = {
            "ifr": round(ifr, 2),
            "METEOR": round(scores["METEOR"], 4) if isinstance(scores["METEOR"], float) else scores["METEOR"],
            "CIDEr-D": round(scores["CIDEr-D"], 4),
            "ROUGE-L": round(scores["ROUGE-L"], 4)
        }

    if all_cands:
        scores = score_variation(all_cands, all_refs)
        all_ifr = 100.0 * all_follow_cnt / all_total if all_total else 0.0
        m = scores["METEOR"]
        m_str = f"{m:.4f}" if isinstance(m, float) else "N/A"
        # print("-" * 96)
        # print(row.format(
        #     "ALL", all_total, all_follow_cnt, all_ifr,
        #     m_str, f"{scores['CIDEr-D']:.4f}", f"{scores['ROUGE-L']:.4f}"
        # ))
        res['all'] = {
            "ifr": round(all_ifr, 2),
            "METEOR": round(scores["METEOR"], 4) if isinstance(scores["METEOR"], float) else scores["METEOR"],
            "CIDEr-D": round(scores["CIDEr-D"], 4),
            "ROUGE-L": round(scores["ROUGE-L"], 4)
        }
    output = json.dumps(res, indent=2, ensure_ascii=False)
    print(output)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python eval_aac_ifr_variations.py infer.json")
        sys.exit(1)
    main(sys.argv[1])
