import sys
import json
from collections import defaultdict

def task_of(item):
    t = (item.get("task") or "").lower()
    if any(k in t for k in ["emotion_recognition"]):
        return "SER"
    if any(k in t for k in ["gender_recognition"]):
        return "GR"
    txt = str(item.get("text", ""))
    return "SER"

file = sys.argv[1]

# file name format: /path/to/file_prefix_taskname.json
# task = file.split("/")[-1].split('.')[1].split('_')[-1]

SER_VALID = ["happy", "sad", "angry", "neutral"]
GR_VALID = ["male", "female"]

with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)

task = task_of(data[0]).lower()

if_cnt = defaultdict(int)
correct = defaultdict(int)
total = defaultdict(int)

if task == "ser":
    valid = SER_VALID
elif task == "gr":
    valid = GR_VALID
else:
    print(f"Unknown task: {task}")
    raise NotImplementedError

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

def extract_label(s: str):
    s = s.strip("'").strip('"').strip(".").lower()
    return s

key_order = []
for item in data:
    label = item["text"].lower()
    vr = item.get("variation_responses", {}) or {}
    
    for top_key, value in vr.items():
        if top_key not in key_order:
            key_order.append(top_key)

        for pred in iter_preds_by_topkey(value):
            # print(f"pred: {pred}")
            pred_norm = extract_label(pred)
            # print(f"pred_norm: {pred_norm}")
            if pred_norm in valid:
                if_cnt[top_key] += 1
                total[top_key] += 1
                if pred_norm == label:
                    correct[top_key] += 1
            else:
                total[top_key] += 1

res = {}
total_cnt = sum(total.values())
total_follow = sum(if_cnt.values())
total_correct = sum(correct.values())
res['all'] = {
    "ifr": round(100.0 * total_follow / total_cnt, 2),
    "acc": round(100.0 * total_correct / total_cnt, 2)
}

for k in key_order:
    assert total[k] != 0, f"No response in {k}!"
    ifr = 100.0 * if_cnt[k] / total[k]
    acc = 100.0 * correct[k] / total[k]
    res[k] = {
        "ifr": round(ifr, 2),
        "acc": round(acc, 2)
    }
    # print(f"[{k}]: IFR / ACC : {ifr:.2f} / {acc:.2f}")

output = json.dumps(res, indent=2, ensure_ascii=False)
print(output)
