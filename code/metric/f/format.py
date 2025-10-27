import os
import sys
from contextlib import redirect_stdout, redirect_stderr

with redirect_stdout(open(os.devnull, "w")), redirect_stderr(open(os.devnull, "w")):
    import json
    import os
    import random
    import jieba

    import re

positive = []
negative = []
corner_positive = []
corner_negative = []

def extract_colon_segments(text):

    punctuation_pattern = r"[。！？；，、：:\!\?\.\;\,]"

    colon_pattern = r"[：:]"
    colon_matches = list(re.finditer(colon_pattern, text))

    if not colon_matches:
        return []

    segments = []

    for colon_match in colon_matches:
        colon_pos = colon_match.start()
        text_before_colon = text[:colon_pos]

        prev_punctuation_matches = list(
            re.finditer(punctuation_pattern, text_before_colon)
        )

        if prev_punctuation_matches:
            prev_punct_pos = prev_punctuation_matches[-1].end()
            segment = text[prev_punct_pos : colon_pos + 1]
        else:
            segment = text[: colon_pos + 1]

        segment = segment.strip()
        if segment:
            segments.append(segment)

    return segments


def remove_brackets(text):
    if not isinstance(text, str):
        return text

    patterns = [r"《[^》]*》", r"（[^）]*）", r"\([^)]*\)", r'"[^"]*"']
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    return re.sub(r"\s+", " ", text).strip()


def remove_common_words(cons, text):
    text = remove_brackets(text)
    text_words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))

    def replace_word(match):
        word = match.group().lower()
        if word in text_words:
            return ""
        return match.group()

    result = re.sub(r"\b[a-zA-Z]+\b", replace_word, cons)

    result = re.sub(r"\s+", " ", result).strip()

    return result


def count_words_advanced(text):
    english_text = re.sub(r"[^\w\s]", " ", re.sub(r"[\u4e00-\u9fff]", " ", text))
    english_words = [
        word for word in english_text.split() if word and re.match(r"[a-zA-Z]+", word)
    ]

    chinese_text = re.sub(r"[a-zA-Z0-9\s\W]", "", text)
    chinese_words = list(jieba.cut(chinese_text)) if chinese_text else []
    chinese_words = [word for word in chinese_words if word.strip()]

    return len(english_words) + len(chinese_words), english_words, chinese_words


def remove_punctuation(text):
    return re.sub(r"[^\w\s]", "", text)


def same_first_five_words_chinese(str1, str2):
    str1 = remove_punctuation(str1)
    str2 = remove_punctuation(str2)
    words1 = list(jieba.cut(str1.lower().strip()))
    words2 = list(jieba.cut(str2.lower().strip()))

    words1 = [word for word in words1 if word.strip()]
    words2 = [word for word in words2 if word.strip()]

    first_five_1 = words1[:3]
    first_five_2 = words2[:3]
    flag1 = first_five_1 == first_five_2

    end_five_1 = words1[-3:]
    end_five_2 = words2[-3:]
    flag2 = end_five_1 == end_five_2

    beta = 1.1

    len1 = len(words1)
    len2 = len(words2)
    flag3 = len1 < beta * len2 and len2 < beta * len1

    return flag1 and flag2 and flag3


translation_keywords_candidate = [
    "mandarin",
    "chinese",
    "translation",
    "中文是",
    # "中文",
    "普通话版本",
    # "普通话",
    "汉语",
    "翻译",
    "译文",
    "原文",
    "译成",
    "翻成",
    "翻译成",
    "翻译为",
    "译为",
    "翻成",
    " is",
    # "是",
    # "结果",
]
raw = [
    "mandarin",
    "chinese",
    "translation",
    # "中文",
    "普通话",
    "汉语",
    "翻译",
    "译文",
    "原文",
    "译成",
    "翻成",
    "翻译成",
    "翻译为",
    "译为",
    "翻成",
]
translation_keywords = translation_keywords_candidate.copy()
translation_keywords += [item + ":" for item in translation_keywords_candidate]
translation_keywords += [item + "：" for item in translation_keywords_candidate]
translation_keywords += [item + "是" for item in translation_keywords_candidate]
translation_keywords += [item + ")" for item in translation_keywords_candidate]
translation_keywords += ["(" + item for item in translation_keywords_candidate]
translation_keywords += [item + "）" for item in translation_keywords_candidate]
translation_keywords += ["（" + item for item in translation_keywords_candidate]
translation_keywords += ["中文翻译", "普通话翻译", "汉语翻译"]
translation_keywords.remove("汉语")
# print (translation_keywords)


def corner_case_collect(text, constrain):
    if any(
        keyword in constrain.lower() and keyword in text.lower()
        for keyword in translation_keywords
    ):
        corner_positive.append({"text": text, "constrain": constrain})
    else:
        if not any(
            keyword in constrain.lower() and keyword not in text.lower()
            for keyword in translation_keywords
        ):
            _, en_words_rm, cn_words_rm = count_words_advanced(
                remove_common_words(constrain, text)
            )
            _, en_words, cn_words = count_words_advanced(constrain)

            if len(en_words_rm) < 5 or len(en_words) >= 5:
                corner_positive.append({"text": text, "constrain": constrain})


def judge(text, constrain):
    if any(
        keyword in constrain.lower()  # and keyword not in text.lower()
        for keyword in translation_keywords
    ) and not any(keyword in text.lower() for keyword in translation_keywords):
        return "negative"
    else:
        _, en_words, _ = count_words_advanced(remove_common_words(constrain, text))
        _, _, cn_words = count_words_advanced(constrain)
        segs = extract_colon_segments(constrain)
        flag = False
        for seg in segs:
            if any(keyword in seg.lower() for keyword in raw):
                flag = True
        if len(cn_words) == 0 or len(en_words) >= 5 or flag:
            return "negative"
        else:
            return "positive"


if __name__ == "__main__":
    text = "这是一个翻译。"
    cons = "请将以下翻译：和哈哈"
    # print(judge(text, cons))
    with open(
        "/hpc_stor03/sjtu_home/yuhang.qiu/SpeechT5/wavllm/test_result/t-test/t-json/s2tt/S2TTT.json",
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)
    nps = ["positive", "negative"]
    correct = 0
    total = 0
    for np in nps:
        for item in data[np]:
            text = item["text"]
            cons = item["constrain"]
            # if "此外" in cons:
            # print("debug")
            res = judge(text, cons)
            if res == np:
                correct += 1
            # else:
            #     print(f"Error case:{json.dumps(item, ensure_ascii=False, indent=2)}")
            total += 1
    # print(f"Accuracy: {correct}/{total} = {correct/total:.4f}")
