#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import sys
from collections import defaultdict
from typing import Any, Dict, List, Tuple, Union

import sacrebleu 


PREFIX_RE = re.compile(r"^\s*the translation is:\s*", re.IGNORECASE)
STRIP_PREFIX_FOR_EVAL = True    
SACREBLEU_TOKENIZE = "zh"       


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
                if not ln:
                    continue
                out.append(json.loads(ln))
        return out

def flatten_variation_values(v: Union[str, List, Dict]) -> List[str]:
    results: List[str] = []
    if isinstance(v, str):
        results.append(v)
    elif isinstance(v, list):
        for x in v:
            results.append(str(x))
    elif isinstance(v, dict):
        for x in v.values():
            results.extend(flatten_variation_values(x))
    else:
        results.append(str(v))
    return results

def strip_surrounding_quotes(s: str) -> str:
    if len(s) >= 2 and ((s[0] == s[-1]) and s[0] in ("'", '"')):
        return s[1:-1]
    return s

def sanitize_text(s: str) -> str:
    return " ".join(s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").split())

def prepare_dataset(
    samples: List[Dict[str, Any]]
) -> Tuple[Dict[str, List[str]], Dict[str, List[List[str]]], Dict[str, Tuple[int, int]]]:

    var2cands: Dict[str, List[str]] = defaultdict(list)
    var2refs:  Dict[str, List[List[str]]] = defaultdict(list)
    var2ifr_cnt: Dict[str, List[int]] = defaultdict(lambda: [0, 0])  # [follow_cnt, total_cnt]

    for ex in samples:
        raw_refs = ex.get("text", "")
        refs = [sanitize_text(r) for r in str(raw_refs).split("|") if r.strip()]
        if not refs:
            continue

        vr = ex.get("variation_responses", {})
        if not isinstance(vr, dict):
            continue

        for var_name, var_value in vr.items():
            if isinstance(var_value, dict):
                for var_name, var_value in var_value.items():
                    cand_list = flatten_variation_values(var_value)
                    for cand in cand_list:
                        var2ifr_cnt[var_name][1] += 1  # total++
                        cand = sanitize_text(str(cand))

                        if PREFIX_RE.match(cand):
                            var2ifr_cnt[var_name][0] += 1
                            if STRIP_PREFIX_FOR_EVAL:
                                cand = PREFIX_RE.sub("", cand).strip()
                            cand = strip_surrounding_quotes(cand)
                        else:
                            cand = ""

                        var2cands[var_name].append(cand)
                        var2refs[var_name].append(refs)
            else:
                cand_list = flatten_variation_values(var_value)
                for cand in cand_list:
                    var2ifr_cnt[var_name][1] += 1  # total++
                    cand = sanitize_text(str(cand))

                    if PREFIX_RE.match(cand):
                        var2ifr_cnt[var_name][0] += 1
                        if STRIP_PREFIX_FOR_EVAL:
                            cand = PREFIX_RE.sub("", cand).strip()
                        cand = strip_surrounding_quotes(cand)
                    else:
                        cand = ""

                    var2cands[var_name].append(cand)
                    var2refs[var_name].append(refs)

    return var2cands, var2refs, {k: (v[0], v[1]) for k, v in var2ifr_cnt.items()}

def to_sacrebleu_refs(mult_refs: List[List[str]]) -> List[List[str]]:
    if not mult_refs:
        return []
    max_nrefs = max(len(r) for r in mult_refs)
    ref_sets = [[] for _ in range(max_nrefs)]
    for refs in mult_refs:
        for j in range(max_nrefs):
            ref_sets[j].append(refs[j] if j < len(refs) else refs[0])
    return ref_sets

def score_bleu(cands: List[str], mult_refs: List[List[str]]) -> sacrebleu.metrics.bleu.BLEUScore:
    ref_sets = to_sacrebleu_refs(mult_refs)
    return sacrebleu.corpus_bleu(cands, ref_sets, tokenize=SACREBLEU_TOKENIZE) 

def main(json_path: str):
    res = {}
    data = load_json_either_array_or_ndjson(json_path)
    var2cands, var2refs, var2ifr_cnt = prepare_dataset(data)

    # print("== Translation Variation Evaluation (BLEU) ==")
    # print(f"Prefix requirement: /^{PREFIX_RE.pattern}$/  strip_prefix_for_eval={STRIP_PREFIX_FOR_EVAL}  tokenize={SACREBLEU_TOKENIZE}")
    # print()

    header = "{:<28} {:>8} {:>8} {:>9} {:>10} {:>11} {:>11} {:>8}"
    row    = "{:<28} {:>8} {:>8} {:>8.1f}% {:>10.2f} {:>11.2f} {:>11.2f} {:>8.3f}"
    # print(header.format("variation", "samples", "follow", "IFR", "BLEU", "P1/P2/P3/P4", "BP", "len-r"))
    for var in sorted(var2cands.keys()):
        hyps = var2cands[var]
        mrefs = var2refs[var]
        follow, total = var2ifr_cnt.get(var, (0, 0))
        if total == 0:
            continue
        score = score_bleu(hyps, mrefs)
        p1, p2, p3, p4 = score.precisions
        bp = score.bp
        len_ratio = (score.sys_len / score.ref_len) if score.ref_len > 0 else 0.0
        ifr_pct = 100.0 * follow / total
        # print(row.format(
        #     var[:28], total, follow, ifr_pct,
        #     score.score,  # BLEU
        #     (p1 + p2 + p3 + p4) / 4.0, 
        #     bp,
        #     len_ratio
        # ))
        res[var] = {
            "ifr": round(ifr_pct, 2),
            "bleu": round(score.score, 2),
            "p1": round(p1, 2),
            "p2": round(p2, 2),
            "p3": round(p3, 2),
            "p4": round(p4, 2),
            "bp": round(bp, 4),
            "len_ratio": round(len_ratio, 4)
        }

    all_hyps, all_mrefs, all_follow, all_total = [], [], 0, 0
    for var in var2cands:
        all_hyps.extend(var2cands[var])
        all_mrefs.extend(var2refs[var])
        f, t = var2ifr_cnt[var]
        all_follow += f
        all_total  += t
    if all_total > 0:
        score = score_bleu(all_hyps, all_mrefs)
        p1, p2, p3, p4 = score.precisions
        bp = score.bp
        len_ratio = (score.sys_len / score.ref_len) if score.ref_len > 0 else 0.0
        ifr_pct = 100.0 * all_follow / all_total
        # print("-" * 100)
        # print(row.format(
        #     "ALL", all_total, all_follow, ifr_pct,
        #     score.score, (p1 + p2 + p3 + p4) / 4.0, bp, len_ratio
        # ))
        res['all'] = {
            "ifr": round(ifr_pct, 2),
            "bleu": round(score.score, 2),
            "p1": round(p1, 2),
            "p2": round(p2, 2),
            "p3": round(p3, 2),
            "p4": round(p4, 2),
            "bp": round(bp, 4),
            "len_ratio": round(len_ratio, 4)
        }

    output = json.dumps(res, indent=2, ensure_ascii=False)
    print(output) 

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python compute_if_bleu.py <json_path>")
        sys.exit(1)
    main(sys.argv[1])
