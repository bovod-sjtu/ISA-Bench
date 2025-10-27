#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Tuple, Union
import sys
from aac_metrics.functional import meteor, cider_d, rouge_l
from aac_metrics.utils.tokenization import preprocess_mono_sents, preprocess_mult_sents


#  "The audio caption is: ..." / "the audio caption is ..." / "  THE AUDIO CAPTION IS :   ..."
PREFIX_RE = re.compile(r"^\s*The audio caption is:\s*", re.IGNORECASE)
STRIP_PREFIX_FOR_EVAL = True  


def load_json_either_array_or_ndjson(path: str) -> List[Dict[str, Any]]:
    """既兼容单个 JSON 数组文件，也兼容 NDJSON（一行一个 JSON）。"""
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
    """把 variation 的值拍平成字符串列表。支持 str / list[str] / dict[str, (str|list)]."""
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


def prepare_dataset(samples: List[Dict[str, Any]]) -> Tuple[Dict[str, List[str]], Dict[str, List[List[str]]], Dict[str, Tuple[int, int]]]:
    var2cands: Dict[str, List[str]] = defaultdict(list)
    var2refs:  Dict[str, List[List[str]]] = defaultdict(list)
    var2ifr_cnt: Dict[str, List[int]] = defaultdict(lambda: [0, 0])  # [follow_cnt, total_cnt]

    for ex in samples:
        raw_refs = ex.get("text", "")
        refs = [r.strip() for r in str(raw_refs).split("|") if r.strip()]
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
                        cand = str(cand).replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()

                        if PREFIX_RE.match(cand):
                            var2ifr_cnt[var_name][0] += 1
                            if STRIP_PREFIX_FOR_EVAL:
                                cand = PREFIX_RE.sub("", cand, count=1).strip()
                            cand_eval = strip_surrounding_quotes(cand)
                        else:
                            cand_eval = ""

                        var2cands[var_name].append(cand_eval)
                        var2refs[var_name].append(refs)
            else:
                cand_list = flatten_variation_values(var_value)

                for cand in cand_list:
                    var2ifr_cnt[var_name][1] += 1  # total++
                    cand = str(cand).replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()

                    if PREFIX_RE.match(cand):
                        var2ifr_cnt[var_name][0] += 1
                        if STRIP_PREFIX_FOR_EVAL:
                            cand = PREFIX_RE.sub("", cand, count=1).strip()
                        cand_eval = strip_surrounding_quotes(cand)
                    else:
                        cand_eval = ""

                    var2cands[var_name].append(cand_eval)
                    var2refs[var_name].append(refs)

    return var2cands, var2refs, {k: (v[0], v[1]) for k, v in var2ifr_cnt.items()}


def score_variation(cands: List[str], mult_refs: List[List[str]]) -> Dict[str, float]:
    cand_proc = preprocess_mono_sents(cands)
    refs_proc = preprocess_mult_sents(mult_refs)

    m_corpus, _ = meteor(cand_proc, refs_proc)
    c_corpus, _ = cider_d(cand_proc, refs_proc)
    r_corpus, _ = rouge_l(cand_proc, refs_proc)

    return {
        "METEOR": float(m_corpus["meteor"].item()),
        "CIDEr-D": float(c_corpus["cider_d"].item()),
        "ROUGE-L": float(r_corpus["rouge_l"].item()),
    }


def main(json_path: str):
    data = load_json_either_array_or_ndjson(json_path)
    var2cands, var2refs, var2ifr_cnt = prepare_dataset(data)
    res = {}

    # print("== ACC Variation Evaluation ==")
    # print(f'Prefix requirement (regex): {PREFIX_RE.pattern!r}  |  strip_prefix_for_eval={STRIP_PREFIX_FOR_EVAL}')
    # print()

    header = "{:<28} {:>8} {:>8} {:>10} {:>12} {:>12} {:>12}"
    row    = "{:<28} {:>8} {:>8} {:>9.1f}% {:>12.4f} {:>12.4f} {:>12.4f}"
    # print(header.format("variation", "samples", "follow", "IFR", "METEOR", "CIDEr-D", "ROUGE-L"))

    for var in sorted(var2cands.keys()):
        cands = var2cands[var]
        refs  = var2refs[var]
        follow, total = var2ifr_cnt.get(var, (0, 0))
        if total == 0:
            continue
        scores = score_variation(cands, refs)
        ifr_pct = 100.0 * follow / total
        # print(row.format(
        #     var[:28], total, follow, ifr_pct,
        #     scores["METEOR"], scores["CIDEr-D"], scores["ROUGE-L"]
        # ))
        res[var] = {
            "ifr": round(ifr_pct, 2),
            "METEOR": round(scores["METEOR"], 4),
            "CIDEr-D": round(scores["CIDEr-D"], 4),
            "ROUGE-L": round(scores["ROUGE-L"], 4)
        }

    all_cands, all_refs, all_follow, all_total = [], [], 0, 0
    for var in var2cands:
        all_cands.extend(var2cands[var])
        all_refs.extend(var2refs[var])
        f, t = var2ifr_cnt[var]
        all_follow += f
        all_total  += t
    if all_total > 0:
        scores = score_variation(all_cands, all_refs)
        ifr_pct = 100.0 * all_follow / all_total
        # print("-" * 96)
        # print(row.format(
        #     "ALL", all_total, all_follow, ifr_pct,
        #     scores["METEOR"], scores["CIDEr-D"], scores["ROUGE-L"]
        # ))
        res['all'] = {
            "ifr": round(ifr_pct, 2),
            "METEOR": round(scores["METEOR"], 4),
            "CIDEr-D": round(scores["CIDEr-D"], 4),
            "ROUGE-L": round(scores["ROUGE-L"], 4)
        }

    output = json.dumps(res, indent=2, ensure_ascii=False)
    print(output)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python compute_if_aac.py <json_path>")
        sys.exit(1)
    json_path = sys.argv[1]
    main(json_path)
