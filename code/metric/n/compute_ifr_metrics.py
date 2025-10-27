#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import json
import re
from collections import defaultdict
from typing import Dict, List, Tuple

import jiwer
from normalizers.english import EnglishTextNormalizer

# ---------- 规范化（仅用于 ASR->WER） ----------
normalizer = EnglishTextNormalizer()
def norm_asr(s: str) -> str:
    return normalizer(s or "")

# ---------- 任务集合与正则 ----------
TASKS = ("ASR", "SER", "GR")
ALLOWED_SER = {"happy", "sad", "angry", "neutral"}
ALLOWED_GR  = {"male", "female"}
SER_RE = re.compile(r"\b(happy|sad|angry|neutral)\b", re.IGNORECASE)
GR_RE  = re.compile(r"\b(male|female)\b", re.IGNORECASE)

res = {}

import string

candidates = [
    'the speaker',
    'the audio',
    'the spoken content',
    'summary:',
    'the sentence'
]

import re

def normed_in(resp: str, list_of_str: List[str]) -> bool:
    return resp.lower().strip() in (s.lower() for s in list_of_str)

def preprocess(text: str) -> str:
    # 全部转小写
    text = text.lower()
    # 去掉标点（只保留字母、数字和空格）
    text = re.sub(f"[{re.escape(string.punctuation)}]", "", text)
    # 去掉多余空格
    text = re.sub(r"\s+", " ", text).strip()
    return text

def wer_with_ops(ref: str, hyp: str):
    # 预处理
    ref = preprocess(ref)
    hyp = preprocess(hyp)

    ref_words = ref.split()
    hyp_words = hyp.split()
    n = len(ref_words)

    # 初始化DP矩阵
    dp = [[0] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]
    backtrace = [[None] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]

    for i in range(len(ref_words) + 1):
        dp[i][0] = i
        backtrace[i][0] = "D" if i > 0 else None  # 删除
    for j in range(len(hyp_words) + 1):
        dp[0][j] = j
        backtrace[0][j] = "I" if j > 0 else None  # 插入

    # 动态规划
    for i in range(1, len(ref_words) + 1):
        for j in range(1, len(hyp_words) + 1):
            if ref_words[i-1] == hyp_words[j-1]:
                dp[i][j] = dp[i-1][j-1]
                backtrace[i][j] = "M"  # 匹配
            else:
                # 三种操作
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

    # 回溯，统计 S, D, I
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
    # 正则化：标点转空格 + 小写
    normalized = re.sub(r"[^\w\s]", " ", sentence).lower()
    words = normalized.split()
    n = len(words)
    if n < 2:
        return False
    
    # 检查是否由某个片段重复组成
    for size in range(1, n // 2 + 1):
        if n % size == 0:
            unit = words[:size]
            if unit * (n // size) == words:
                return True
    return False

def judge(resp, ref):
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

# ---------- 小工具 ----------
def canon_ser(s: str) -> str:
    if not s: return ""
    m = SER_RE.search(s)
    return (m.group(1).lower() if m else "")

def canon_gr(s: str) -> str:
    if not s: return ""
    m = GR_RE.search(s)
    return (m.group(1).lower() if m else "")

def asr_wer(refs: List[str], hyps: List[str]) -> float:
    """返回 WER（百分数）。"""
    r = [norm_asr(x) for x in refs]
    h = [norm_asr(x) for x in hyps]
    return jiwer.wer(r, h) * 100.0 if r else 0.0

# 结构化统计器
class Stat:
    def __init__(self, task: str):
        self.task = task
        self.total = 0        # 条目数（按条累计）
        self.follow = 0       # IFR 通过条数
        self.refs: List[str] = []   # ASR 引用/ SER/GR 标签
        self.hyps: List[str] = []   # 预测

    def add(self, follow: bool, ref: str, hyp: str):
        self.total += 1
        self.follow += int(bool(follow))
        self.refs.append(ref or "")
        self.hyps.append(hyp or "")

    def metric(self) -> Tuple[str, float]:
        """ASR->WER(%，越小越好)，SER/GR->ACC(%，越大越好)"""
        if self.task == "ASR":
            return "WER(%)", asr_wer(self.refs, self.hyps)
        elif self.task in ("SER", "GR"):
            hit = 0
            if self.task == "SER":
                for r, h in zip(self.refs, self.hyps):
                    hit += int(canon_ser(h) == (r or "").strip().lower())
            else:
                for r, h in zip(self.refs, self.hyps):
                    hit += int(canon_gr(h) == (r or "").strip().lower())
            acc = (100.0 * hit / len(self.refs)) if self.refs else 0.0
            return "ACC(%)", acc
        else:
            return "N/A", 0.0

    def ifr_pct(self) -> float:
        return 100.0 * self.follow / self.total if self.total else 0.0

# 嵌套容器：stage -> taskcount -> task -> Stat
def ensure_stat(box, stage: str, n_task: int, task: str) -> Stat:
    if stage not in box: box[stage] = {}
    if n_task not in box[stage]: box[stage][n_task] = {}
    if task not in box[stage][n_task]:
        box[stage][n_task][task] = Stat(task)
    return box[stage][n_task][task]

# 额外：overall 的 taskcount 聚合（跨 stage）
def ensure_overall_stat(box, n_task: int, task: str) -> Stat:
    if n_task not in box: box[n_task] = {}
    if task not in box[n_task]:
        box[n_task][task] = Stat(task)
    return box[n_task][task]

# ---------- 核心评测 ----------
def eval_file(path: str):
    data = json.load(open(path, "r", encoding="utf-8"))
    items = data["annotation"] if isinstance(data, dict) and "annotation" in data else data

    # 主聚合：Stage × TaskCount（2/3 为主；1 也支持，以便 single-task）
    stage_tasknum_stats: Dict[str, Dict[int, Dict[str, Stat]]] = {}
    # overall（跨 stage）的 taskcount 聚合
    overall_tasknum_stats: Dict[int, Dict[str, Stat]] = {}

    # 便于打印：按 stage 保存分支细项
    detail_collect = defaultdict(lambda: defaultdict(list))  # stage -> {"separation": [...], "json":[...]}

    for samp in items:
        ref_asr = (samp.get("text") or "").strip()
        ref_ser = (samp.get("emotion") or "").strip().lower()
        ref_gr  = (samp.get("gender") or "").strip().lower()

        variations = (((samp.get("instructions") or {}).get("variations")) or {})
        for stage in ("single-stage", "multi-stage"):
            stage_obj = variations.get(stage, {})
            if not stage_obj: 
                continue

            # -------- separation --------
            sep_blocks = stage_obj.get("separation", [])
            for block in sep_blocks:
                if not isinstance(block, list): 
                    continue
                for rec in block:
                    if not isinstance(rec, dict): 
                        continue
                    task_str = rec.get("task", "")
                    resp = rec.get("response", "")
                    sep = rec.get("separator", "\\")
                    tasks = [t.strip() for t in task_str.split("|") if t.strip() in TASKS]
                    n_task = len(tasks)

                    parts = resp.split(sep)
                    follow = (len(parts) == n_task)

                    if follow:
                        if 'ASR' in tasks:
                            # 进一步检查 ASR 部分的合理性
                            asr_index = tasks.index('ASR')
                            asr_part = parts[asr_index].strip()
                            follow = judge(asr_part, ref_asr)
                        if 'SER' in tasks and follow:
                            ser_index = tasks.index('SER')
                            ser_part = parts[ser_index].strip()
                            follow = follow and normed_in(ser_part, ALLOWED_SER)
                        if 'GR' in tasks and follow:
                            gr_index = tasks.index('GR')
                            gr_part = parts[gr_index].strip()
                            follow = follow and normed_in(gr_part, ALLOWED_GR)

                    # 若不遵循，将各任务预测置空串
                    hyps_by_task = {t: "" for t in tasks}
                    if follow:
                        # 清理两端括号/引号/空白
                        clean = []
                        for p in parts:
                            x = p.strip().strip("\"' ").strip()
                            # 去掉对称括号
                            if len(x) >= 2 and ((x[0], x[-1]) in {("(", ")"), ("[", "]"), ("{", "}")}):
                                x = x[1:-1].strip()
                            clean.append(x)
                        for t, p in zip(tasks, clean):
                            hyps_by_task[t] = p
                    # else:
                    #     print(f"Task: {task_str}; Response: {resp}")

                    # 累积到 Stage × TaskCount 的每个子任务 & overall
                    for t in tasks:
                        st = ensure_stat(stage_tasknum_stats, stage, n_task, t)
                        ost = ensure_overall_stat(overall_tasknum_stats, n_task, t)
                        if t == "ASR":
                            st.add(follow, ref_asr, hyps_by_task[t])
                            ost.add(follow, ref_asr, hyps_by_task[t])
                        elif t == "SER":
                            st.add(follow, ref_ser, hyps_by_task[t])
                            ost.add(follow, ref_ser, hyps_by_task[t])
                        elif t == "GR":
                            st.add(follow, ref_gr,  hyps_by_task[t])
                            ost.add(follow, ref_gr,  hyps_by_task[t])

                    detail_collect[stage]["separation"].append((tasks, follow))

            # -------- json --------
            json_blocks = stage_obj.get("json", [])
            for block in json_blocks:
                if not isinstance(block, list): 
                    continue
                for rec in block:
                    if not isinstance(rec, dict): 
                        continue
                    # 任务由 "task" 决定，不再用 key 名推断
                    task_str = rec.get("task", "")
                    tasks = [t.strip() for t in task_str.split("|") if t.strip() in TASKS]
                    n_task = len(tasks)

                    key_str = rec.get("key", "")
                    keys = [k.strip() for k in key_str.split("|") if k.strip()]
                    resp = rec.get("response", "")

                    # 需要严格 JSON
                    try:
                        obj = json.loads(resp)
                        is_json = isinstance(obj, dict)
                    except Exception:
                        obj, is_json = None, False

                    # IFR 条件：json 解析成功 + 任务数与 key 数一致 + 所有 key 存在
                    follow = bool(is_json and (len(keys) == n_task) and all(k in obj for k in keys))

                    if follow:
                        if 'ASR' in tasks:
                            # 进一步检查 ASR 部分的合理性
                            asr_index = tasks.index('ASR')
                            asr_key = keys[asr_index]
                            asr_part = str(obj.get(asr_key, "")).strip()
                            follow = judge(asr_part, ref_asr)
                        if 'SER' in tasks and follow:
                            ser_index = tasks.index('SER')
                            ser_key = keys[ser_index]
                            ser_part = str(obj.get(ser_key, "")).strip()
                            follow = follow and normed_in(ser_part, ALLOWED_SER)
                        if 'GR' in tasks and follow:
                            gr_index = tasks.index('GR')
                            gr_key = keys[gr_index]
                            gr_part = str(obj.get(gr_key, "")).strip()
                            follow = follow and normed_in(gr_part, ALLOWED_GR)

                    # 将 key 的值按顺序映射到相同位置上的任务
                    hyps_by_task = {t: "" for t in tasks}
                    if follow:
                        for t, k in zip(tasks, keys):
                            v = obj.get(k, "")
                            hyps_by_task[t] = str(v)
                    # else:
                        # print(f"Task: {task_str}; Response: {resp}; Keys: {keys}")

                    # 累积
                    for t in tasks:
                        st = ensure_stat(stage_tasknum_stats, stage, n_task, t)
                        ost = ensure_overall_stat(overall_tasknum_stats, n_task, t)
                        if t == "ASR":
                            st.add(follow, ref_asr, hyps_by_task[t])
                            ost.add(follow, ref_asr, hyps_by_task[t])
                        elif t == "SER":
                            st.add(follow, ref_ser, hyps_by_task[t])
                            ost.add(follow, ref_ser, hyps_by_task[t])
                        elif t == "GR":
                            st.add(follow, ref_gr,  hyps_by_task[t])
                            ost.add(follow, ref_gr,  hyps_by_task[t])

                    detail_collect[stage]["json"].append((tasks, follow))

    # ---------- 打印：主汇总 = Stage × TaskCount(2/3) ----------
    def print_stat_block(title: str, bucket: Dict[int, Dict[str, Stat]], only_nums=(2, 3)):
        # print("=" * 68)
        # print(title)
        res[title] = {}
        for n in only_nums:
            if n not in bucket: 
                continue
            # print(f"--- {n}-TASK ---")
            res[title][f"{n}-TASK"] = {}
            for t in TASKS:
                st = bucket[n].get(t, None)
                if not st or st.total == 0: 
                    continue
                mname, mval = st.metric()
                # print(f"{t:>3} | IFR {st.ifr_pct():6.2f}% | {mname} {mval:8.2f} | N={st.total}")
                res[title][f"{n}-TASK"][t] = {
                    "ifr": round(st.ifr_pct(), 2),
                    mname.lower()[:3]: round(mval, 2),
                    "n": st.total
                }

    for stage in ("single-stage", "multi-stage"):
        if stage in stage_tasknum_stats:
            print_stat_block(stage, stage_tasknum_stats[stage], only_nums=(2, 3))

    # ---------- 打印：Single-Task（跨 stage 汇总，若存在 n=1） ----------
    if 1 in overall_tasknum_stats and any(overall_tasknum_stats[1].get(t, None) for t in TASKS):
        print("=" * 68)
        print("[Single-Task (across stages)]")
        for t in TASKS:
            st = overall_tasknum_stats[1].get(t, None)
            if not st or st.total == 0: 
                continue
            mname, mval = st.metric()
            print(f"{t:>3} | IFR {st.ifr_pct():6.2f}% | {mname} {mval:8.2f} | N={st.total}")

    # ----------（可选）细节：每个 stage 下分支通过率 ----------
    for stage in ("single-stage", "multi-stage"):
        if stage not in detail_collect: 
            continue
        # print("=" * 68)
        # print(f"[Details] {stage}")
        for branch in ("separation", "json"):
            if branch not in detail_collect[stage]: 
                continue
            L = detail_collect[stage][branch]
            if not L: 
                continue
            total = len(L)
            follow = sum(int(f) for _tasks, f in L)
            # print(f"{branch:>11}: IFR {100.0*follow/total:6.2f}% | N={total}")
            res[stage][branch] = {
                "ifr": round(100.0 * follow / total, 2),
                "n": total
            }

    output = json.dumps(res, indent=2, ensure_ascii=False)
    print(output)

def main():
    if len(sys.argv) < 2:
        print("Usage: python eval_ifr_stage_tasknum.py infer_result.json")
        sys.exit(1)
    eval_file(sys.argv[1])

if __name__ == "__main__":
    main()
