#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import json
import re
from collections import defaultdict
import jiwer
from normalizers.english import EnglishTextNormalizer

normalizer = EnglishTextNormalizer()

def norm(s: str) -> str:
    return normalizer(s or "")

UPPER_RE = re.compile(r"[A-Z]")
LOWER_RE = re.compile(r"[a-z]")

import os
import sys
import json
import string

candidates = [
    'the speaker',
    'the audio',
    'the spoken content',
    'summary:',
    'the sentence'
]

import re

def preprocess(text: str) -> str:
    text = text.lower()
    text = re.sub(f"[{re.escape(string.punctuation)}]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def wer_with_ops(ref: str, hyp: str):
    ref = preprocess(ref)
    hyp = preprocess(hyp)

    ref_words = ref.split()
    hyp_words = hyp.split()
    n = len(ref_words)

    dp = [[0] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]
    backtrace = [[None] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]

    for i in range(len(ref_words) + 1):
        dp[i][0] = i
        backtrace[i][0] = "D" if i > 0 else None  
    for j in range(len(hyp_words) + 1):
        dp[0][j] = j
        backtrace[0][j] = "I" if j > 0 else None  

    for i in range(1, len(ref_words) + 1):
        for j in range(1, len(hyp_words) + 1):
            if ref_words[i-1] == hyp_words[j-1]:
                dp[i][j] = dp[i-1][j-1]
                backtrace[i][j] = "M"  
            else:
                substitute = dp[i-1][j-1] + 1
                insert = dp[i][j-1] + 1
                delete = dp[i-1][j] + 1

                dp[i][j] = min(substitute, insert, delete)
                if dp[i][j] == substitute:
                    backtrace[i][j] = "S"
                elif dp[i][j] == insert:
                    backtrace[i][j] = "I"
                else:
                    backtrace[i][j] = "D"

    i, j = len(ref_words), len(hyp_words)
    S = D = I = 0
    while i > 0 or j > 0:
        op = backtrace[i][j]
        if op == "M":
            i -= 1
            j -= 1
        elif op == "S":
            S += 1
            i -= 1
            j -= 1
        elif op == "I":
            I += 1
            j -= 1
        elif op == "D":
            D += 1
            i -= 1

    wer_value = (S + D + I) / n if n > 0 else 0.0
    return wer_value, S, D, I, n


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

def ifr_constrain(resp: str, ref: str):
    def judge():
        wer_value, S, D, I, n = wer_with_ops(ref, resp)
        if wer_value >= 1:
            return False
        if I >= 3:
            return False
        flag = True
        for cand in candidates:
            if (cand.lower() in resp.lower()) or is_repeated_sentence(resp):
                flag = False
                break
        return flag

    follow = judge()
    return follow, (norm(resp) if follow else "")

def ifr_upper(resp: str):
    has_lower = bool(LOWER_RE.search(resp))
    has_upper = bool(UPPER_RE.search(resp))
    follow = (not has_lower) and has_upper
    return follow, (norm(resp) if follow else "")

def ifr_lower(resp: str):
    has_upper = bool(UPPER_RE.search(resp))
    has_lower = bool(LOWER_RE.search(resp))
    follow = (not has_upper) and has_lower
    return follow, (norm(resp) if follow else "")

def ifr_prefix(prefix: str, resp: str):
    s = resp.lstrip()
    follow = s.startswith(prefix)
    if follow:
        body = s[len(prefix):].lstrip()
        return True, norm(body)
    return False, ""

def ifr_suffix(suffix: str, resp: str):
    s = resp.rstrip()
    follow = s.endswith(suffix)
    if follow:
        body = s[:len(s) - len(suffix)].rstrip()
        return True, norm(body)
    return False, ""

def ifr_wrap(lrt: str, resp: str):
    if "|" not in lrt:
        return False, ""
    left, right = lrt.split("|", 1)
    s = resp.strip()
    follow = s.startswith(left) and s.endswith(right)
    if follow:
        body = s[len(left):len(s) - len(right)].strip()
        return True, norm(body)
    return False, ""

def ifr_json(resp: str, expected_key: str | None = None):
    try:
        obj = json.loads(resp)
    except Exception:
        return False, "" 

    if not isinstance(obj, dict):
        return False, ""

    if expected_key:
        v = obj.get(expected_key, None)
        if isinstance(v, str):
            return True, norm(v)
        else:
            return False, ""

    parts = [str(v) for v in obj.values() if isinstance(v, str)]
    return (True, norm(" ".join(parts))) if parts else (False, "")

def main():
    if len(sys.argv) < 2:
        print("Usage: python compute_if_wer.py <model_name>_asr_results.json")
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
    all_total, all_follow = 0, 0

    for item in data:
        ref_text = item.get("text", "")
        vr = item.get("variation_responses", {}) or {}

        for top_key, value in vr.items():
            if top_key not in key_order:
                key_order.append(top_key)

            if top_key in ("constrain", "upper_case", "lower_case"):
                preds = [value] if isinstance(value, str) else []
                metas = [{}] * len(preds)
            elif top_key in ("prefix", "suffix", "wrap", "json"):
                preds, metas = [], []
                if isinstance(value, list):
                    for elem in value:
                        if isinstance(elem, dict):
                            preds.append(elem.get("response", ""))
                            metas.append(elem)
            else:
                preds = [value] if isinstance(value, str) else []
                metas = [{}] * len(preds)

            for resp, meta in zip(preds, metas):
                total_preds[top_key] += 1
                all_total += 1

                if top_key == "constrain":
                    follow, hyp_n = ifr_constrain(resp, ref_text)
                elif top_key == "upper_case":
                    follow, hyp_n = ifr_upper(resp)
                elif top_key == "lower_case":
                    follow, hyp_n = ifr_lower(resp)
                elif top_key == "prefix":
                    follow, hyp_n = ifr_prefix(meta.get("prefix", ""), resp)
                elif top_key == "suffix":
                    follow, hyp_n = ifr_suffix(meta.get("suffix", ""), resp)
                elif top_key == "wrap":
                    follow, hyp_n = ifr_wrap(meta.get("lrt", ""), resp)
                elif top_key == "json":
                    follow, hyp_n = ifr_json(resp)
                else:
                    follow, hyp_n = False, ""

                if_follow[top_key] += int(follow)
                all_follow += int(follow)

                gts_by_key[top_key].append(norm(ref_text))
                hyps_by_key[top_key].append(hyp_n)

                all_gts.append(norm(ref_text))
                all_hyps.append(hyp_n)

    for k in key_order:
        assert total_preds[k] != 0, f"No response in {k}!"
        ifr = 100.0 * if_follow[k] / total_preds[k]

        gts = gts_by_key[k]
        hyps = hyps_by_key[k]
        wer_pct = jiwer.wer(gts, hyps) * 100.0 if gts else float("nan")

        # print(f"[{k}]: IFR -- {ifr:.2f}%; WER -- {wer_pct:.2f}%")
        res[k] = {
            "ifr": round(ifr, 2),
            "wer": round(wer_pct, 2) if not (wer_pct != wer_pct) else "N/A"  # NaN check
        }

    all_ifr = 100.0 * all_follow / all_total if all_total else 0.0
    all_wer = jiwer.wer(all_gts, all_hyps) * 100.0 if all_gts else float("nan")
    # print("-" * 64)
    # print(f"[ALL]: IFR -- {all_ifr:.2f}%; WER -- {all_wer:.2f}%")
    res['all'] = {
        "ifr": round(all_ifr, 2),
        "wer": round(all_wer, 2) if not (all_wer != all_wer) else "N/A"  # NaN check
    }

    output = json.dumps(res, indent=2, ensure_ascii=False)
    print(output)

if __name__ == "__main__":
    main()
