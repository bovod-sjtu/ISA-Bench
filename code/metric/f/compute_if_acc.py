#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import json
import re
from collections import defaultdict

SER_SET = {"HAPPY", "SAD", "NEUTRAL", "ANGRY"}
GR_SET  = {"MALE", "FEMALE"}

SER_PAT = re.compile(r"\b(happy|sad|neutral|angry)\b", re.IGNORECASE)
GR_PAT  = re.compile(r"\b(male|female)\b", re.IGNORECASE)

def task_of(item):
    t = (item.get("task") or "").lower()
    if any(k in t for k in ["emotion_recognition"]):
        return "SER"
    if any(k in t for k in ["gender_recognition"]):
        return "GR"
    txt = str(item.get("text", ""))
    if SER_PAT.search(txt):
        return "SER"
    if GR_PAT.search(txt):
        return "GR"
    return "SER"

def canon(label: str, task: str):
    if not label:
        return None
    s = label.strip().strip("'\"").strip()
    m = (SER_PAT if task=="SER" else GR_PAT).search(s)
    if not m:
        return None
    val = m.group(1).upper()
    if task == "SER":
        if val in SER_SET:
            return val
    else:
        if val in GR_SET:
            return val
    return None

def gt_label(item, task: str):
    txt = str(item.get("text", ""))
    return canon(txt, task)

UPPER_RE = re.compile(r"[A-Z]")
LOWER_RE = re.compile(r"[a-z]")

def strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0]==s[-1] and s[0] in ("'", '"'):
        return s[1:-1].strip()
    return s

def ifr_constrain(resp: str, task: str):
    s = strip_quotes(resp or "")
    if " " in s.strip():
        return False, ""
    lab = canon(s, task)
    follow = lab is not None and s.strip().upper() == lab
    return (True, s) if follow else (False, "")

def ifr_upper(resp: str):
    s = resp or ""
    has_lower = bool(LOWER_RE.search(s))
    has_upper = bool(UPPER_RE.search(s))
    follow = (not has_lower) and has_upper
    return (follow, s.strip() if follow else "")

def ifr_lower(resp: str):
    s = resp or ""
    has_upper = bool(UPPER_RE.search(s))
    has_lower = bool(LOWER_RE.search(s))
    follow = (not has_upper) and has_lower
    return (follow, s.strip() if follow else "")

def ifr_prefix(prefix: str, resp: str):
    s = (resp or "")
    p = prefix or ""
    t = s.lstrip()
    if t.startswith(p):
        return True, t[len(p):].lstrip()
    return False, ""

def ifr_suffix(suffix: str, resp: str):
    s = (resp or "")
    su = suffix or ""
    t = s.rstrip()
    if t.endswith(su):
        return True, t[:len(t)-len(su)].rstrip()
    return False, ""

def ifr_wrap(lrt: str, resp: str):
    s = (resp or "")
    spec = lrt or ""
    if "|" not in spec:
        return False, ""
    left, right = spec.split("|", 1)
    t = s.strip()
    if t.startswith(left) and t.endswith(right):
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
    parts = [str(v).strip() for v in obj.values() if isinstance(v, str)]
    if parts:
        return True, " ".join(parts)
    return False, ""

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
        print("Usage: python eval_ifr_acc_ser_gr.py infer.json")
        sys.exit(1)
    path = sys.argv[1]
    data = json.load(open(path, "r", encoding="utf-8"))

    key_order = []
    total_preds = defaultdict(int)      
    if_follow = defaultdict(int)       

    acc_total = defaultdict(int)       
    acc_correct = defaultdict(int)     

    all_ifr_total = 0
    all_ifr_follow = 0
    all_acc_total = 0
    all_acc_correct = 0

    for item in data:
        task = task_of(item) 
        gold = gt_label(item, task)
        vr = item.get("variation_responses", {}) or {}

        for top_key, value in vr.items():
            if top_key not in key_order:
                key_order.append(top_key)

            for resp, meta in iter_preds_by_topkey(value):
                total_preds[top_key] += 1
                all_ifr_total += 1

                if top_key == "constrain":
                    follow, body = ifr_constrain(resp, task)
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
                all_ifr_follow += int(follow)

                pred = canon(body, task) if follow else None

                if gold is not None:
                    acc_total[top_key] += 1
                    all_acc_total += 1
                    if pred is not None and pred == gold:
                        acc_correct[top_key] += 1
                        all_acc_correct += 1


    res = {}

    for k in key_order:
        assert total_preds[k] != 0, f"No response in {k}!"
        ifr = 100.0 * if_follow[k] / total_preds[k]
        if acc_total[k] > 0:
            acc = 100.0 * acc_correct[k] / acc_total[k]
        else:
            acc = 0.0
        # print(f"[{k}]: IFR -- {ifr:.2f}%; ACC -- {acc:.2f}%")
        res[k] = {
            "ifr": round(ifr, 2),
            "acc": round(acc, 2)
        }

    # Overall（micro）
    all_ifr = 100.0 * all_ifr_follow / all_ifr_total if all_ifr_total else 0.0
    all_acc = 100.0 * all_acc_correct / all_acc_total if all_acc_total else 0.0
    # print("-" * 64)
    # print(f"[ALL]: IFR -- {all_ifr:.2f}%; ACC -- {all_acc:.2f}%")
    res['all'] = {
        "ifr": round(all_ifr, 2),
        "acc": round(all_acc, 2)
    }

    output = json.dumps(res, indent=2, ensure_ascii=False)
    print(output)

if __name__ == "__main__":
    main()
