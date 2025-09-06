"""
错别字生成器 - 基于拼音和字频的中文错别字生成工具
"""

import itertools
import math
import os
import random
import time

import jieba
import orjson

from collections import defaultdict
from pathlib import Path
from pypinyin import Style, pinyin

from src.common.logger import get_logger

logger = get_logger("typo_gen")


class ChineseTypoGenerator:
    """
    中文错别字生成器。
    可以根据拼音、字频等信息，为给定的中文句子生成包含错别字的句子。
    支持单字替换和整词替换。
    """

    def __init__(self, error_rate=0.3, min_freq=5, tone_error_rate=0.2, word_replace_rate=0.3, max_freq_diff=200):
        """
        初始化错别字生成器。

        Args:
            error_rate (float): 控制单个汉字被替换为错别字的基础概率。
                                这个概率会根据词语长度进行调整，词语越长，单个字出错的概率越低。
            min_freq (int): 候选替换字的最小词频阈值。一个汉字的频率低于此值时，
                            它不会被选为替换候选字，以避免生成过于生僻的错别字。
            tone_error_rate (float): 在寻找同音字时，有多大的概率会故意使用一个错误的声调来寻找候选字。
                                     这可以模拟常见的声调错误，如 "shí" -> "shì"。
            word_replace_rate (float): 控制一个多字词语被整体替换为同音词的概率。
                                       例如，“天气” -> “天气”。
            max_freq_diff (int): 允许的原始字与替换字之间的最大归一化频率差异。
                                 用于确保替换字与原字的常用程度相似，避免用非常常见的字替换罕见字，反之亦然。
        """
        self.error_rate = error_rate
        self.min_freq = min_freq
        self.tone_error_rate = tone_error_rate
        self.word_replace_rate = word_replace_rate
        self.max_freq_diff = max_freq_diff

        # 加载核心数据
        logger.info("正在加载汉字数据库...")
        self.pinyin_dict = self._create_pinyin_dict()
        self.char_frequency = self._load_or_create_char_frequency()
        logger.info("汉字数据库加载完成。")

    def _load_or_create_char_frequency(self):
        """
        加载或创建汉字频率字典。
        如果存在缓存文件 `depends-data/char_frequency.json`，则直接加载以提高启动速度。
        否则，通过解析 `jieba` 的内置词典文件 `dict.txt` 来创建。
        创建过程中，会统计每个汉字的累计频率，并进行归一化处理，然后保存为缓存文件。

        Returns:
            dict: 一个将汉字映射到其归一化频率（0-1000范围）的字典。
        """
        cache_file = Path("depends-data/char_frequency.json")

        # 如果缓存文件存在，则直接从缓存加载，提高效率
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                return orjson.loads(f.read())

        # 如果没有缓存，则通过解析jieba词典来创建
        char_freq = defaultdict(int)
        # 定位jieba内置词典文件的路径
        dict_path = os.path.join(os.path.dirname(jieba.__file__), "dict.txt")

        # 读取jieba词典文件，统计每个汉字的频率
        with open(dict_path, "r", encoding="utf-8") as f:
            for line in f:
                word, freq = line.strip().split()[:2]
                # 将词中每个汉字的频率进行累加
                for char in word:
                    if self._is_chinese_char(char):
                        char_freq[char] += int(freq)

        # 对频率值进行归一化处理，使其在0-1000的范围内
        max_freq = max(char_freq.values())
        normalized_freq = {char: freq / max_freq * 1000 for char, freq in char_freq.items()}

        # 将计算出的频率数据保存到缓存文件，以便下次快速加载
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(orjson.dumps(normalized_freq, option=orjson.OPT_INDENT_2).decode("utf-8"))

        return normalized_freq

    @staticmethod
    def _create_pinyin_dict():
        """
        创建从拼音到汉字的映射字典。
        该方法会遍历 Unicode 中定义的常用汉字范围 (U+4E00 至 U+9FFF)，
        为每个汉字生成带数字声调的拼音（例如 'hao3'），并构建一个从拼音到包含该拼音的所有汉字列表的映射。
        这个字典是生成同音字和同音词的基础。

        Returns:
            defaultdict: 一个将拼音字符串映射到汉字字符列表的字典。
                         例如: {'hao3': ['好', '郝', ...]}
        """
        # 定义常用汉字的Unicode范围
        chars = [chr(i) for i in range(0x4E00, 0x9FFF)]
        pinyin_dict = defaultdict(list)

        # 为范围内的每个汉字建立拼音到汉字的映射
        for char in chars:
            try:
                py = pinyin(char, style=Style.TONE3)
                if py:
                    pinyin_dict[py].append(char)
            except (IndexError, TypeError):
                continue

        return pinyin_dict

    @staticmethod
    def _is_chinese_char(char):
        """
        判断一个字符是否为中文字符。

        Args:
            char (str): 需要判断的字符。

        Returns:
            bool: 如果是中文字符，返回 True，否则返回 False。
        """
        try:
            # 通过Unicode范围判断是否为中文字符
            return "\u4e00" <= char <= "\u9fff"
        except Exception as e:
            logger.debug(f"判断字符 '{char}' 时出错: {e}")
            return False

    def _get_pinyin(self, sentence):
        """
        获取一个句子中每个汉字的拼音。

        Args:
            sentence (str): 输入的中文句子。

        Returns:
            list: 一个元组列表，每个元组包含 (汉字, 拼音)。
        """
        characters = list(sentence)
        result = []
        for char in characters:
            if self._is_chinese_char(char):
                try:
                    py = pinyin(char, style=Style.TONE3)
                    if py:
                        result.append((char, py))
                except (IndexError, TypeError):
                    continue
        return result

    @staticmethod
    def _get_similar_tone_pinyin(py):
        """
        为一个给定的拼音生成一个声调错误的相似拼音。
        例如，输入 'hao3'，可能返回 'hao1'、'hao2' 或 'hao4'。
        此函数用于模拟中文输入时常见的声调错误。
        对于轻声（拼音末尾无数字声调），会随机分配一个声调。

        Args:
            py (str): 带数字声调的原始拼音 (e.g., 'hao3')。

        Returns:
            str: 一个声调被随机改变的新拼音。
        """
        # 检查拼音是否有效
        if not py or len(py) < 1:
            return py

        # 如果拼音末尾不是数字（如轻声），则默认添加一声
        if not py[-1].isdigit():
            return f"{py}1"

        base = py[:-1]  # 拼音的基本部分 (e.g., 'hao')
        tone = int(py[-1])  # 声调 (e.g., 3)

        # 处理轻声（通常用5表示）或无效声调
        if tone not in [1, 2, 3, 4]:
            return base + str(random.choice([1, 2, 3, 4]))

        # 正常处理声调
        possible_tones = [1, 2, 3, 4]
        possible_tones.remove(tone)  # 移除原声调
        new_tone = random.choice(possible_tones)  # 随机选择一个新声调
        return base + str(new_tone)

    def _calculate_replacement_probability(self, orig_freq, target_freq):
        """
        根据原始字和目标替换字的频率差异，计算替换概率。
        这个概率模型遵循以下原则：
        1. 如果目标字比原始字更常用，替换概率为 1.0（倾向于换成更常见的字）。
        2. 如果频率差异超过 `max_freq_diff` 阈值，替换概率为 0.0。
        3. 否则，使用指数衰减函数计算概率，频率差异越大，替换概率越低。
           这使得替换更倾向于选择频率相近的字。

        Args:
            orig_freq (float): 原始字的归一化频率。
            target_freq (float): 目标替换字的归一化频率。

        Returns:
            float: 替换概率，介于 0.0 和 1.0 之间。
        """
        # 如果目标字更常用，则替换概率为1
        if target_freq > orig_freq:
            return 1.0

        freq_diff = orig_freq - target_freq
        # 如果频率差异过大，则不进行替换
        if freq_diff > self.max_freq_diff:
            return 0.0

        # 使用指数衰减函数来计算概率，频率差异越大，概率越低
        return math.exp(-3 * freq_diff / self.max_freq_diff)

    def _get_similar_frequency_chars(self, char, py, num_candidates=5):
        """
        获取与给定汉字发音相似且频率相近的候选替换字。
        此方法首先根据 `tone_error_rate` 决定是否寻找声调错误的同音字，
        然后合并声调正确的同音字。接着，根据字频进行过滤和排序：
        1. 移除原始字本身和频率低于 `min_freq` 的字。
        2. 计算每个候选字的替换概率。
        3. 按替换概率降序排序，并返回前 `num_candidates` 个候选字。

        Args:
            char (str): 原始汉字。
            py (str): 原始汉字的拼音。
            num_candidates (int): 返回的候选字数量上限。

        Returns:
            list or None: 一个包含候选替换字的列表，如果没有找到合适的候选字则返回 None。
        """
        homophones = []

        # 根据设定概率，可能使用声调错误的拼音来寻找候选字
        if random.random() < self.tone_error_rate:
            wrong_tone_py = self._get_similar_tone_pinyin(py)
            homophones.extend(self.pinyin_dict.get(wrong_tone_py, []))

        # 添加声调正确的同音字
        homophones.extend(self.pinyin_dict.get(py, []))

        if not homophones:
            return None

        orig_freq = self.char_frequency.get(char, 0)

        # 过滤掉低频字和原始字本身
        freq_diff = [
            (h, self.char_frequency.get(h, 0))
            for h in homophones
            if h != char and self.char_frequency.get(h, 0) >= self.min_freq
        ]

        if not freq_diff:
            return None

        # 计算每个候选字的替换概率
        candidates_with_prob = []
        for h, freq in freq_diff:
            prob = self._calculate_replacement_probability(orig_freq, freq)
            if prob > 0:
                candidates_with_prob.append((h, prob))

        if not candidates_with_prob:
            return None

        candidates_with_prob.sort(key=lambda x: x, reverse=True)

        # 返回概率最高的几个候选字
        return [c for c, _ in candidates_with_prob[:num_candidates]]

    @staticmethod
    def _get_word_pinyin(word):
        """
        获取一个词语中每个汉字的拼音列表。

        Args:
            word (str): 输入的词语。

        Returns:
            List[str]: 包含每个汉字拼音的列表。
        """
        return ["".join(p) for p in pinyin(word, style=Style.TONE3)]

    @staticmethod
    def _segment_sentence(sentence):
        """
        使用 jieba 对句子进行分词。

        Args:
            sentence (str): 输入的句子。

        Returns:
            list: 分词后的词语列表。
        """
        return list(jieba.cut(sentence))

    def _get_word_homophones(self, word):
        """
        获取一个词语的所有同音词。
        该方法首先获取词语中每个字的拼音，然后为每个字找到所有同音字。
        接着，使用 `itertools.product` 生成所有可能的同音字组合。
        最后，过滤掉原始词本身，并只保留在 `jieba` 词典中存在的、有意义的词语。
        这可以有效避免生成无意义的同音词组合。

        Args:
            word (str): 原始词语。

        Returns:
            List[str]: 一个包含所有有效同音词的列表。
        """
        if len(word) <= 1:
            return []

        word_pinyin = self._get_word_pinyin(word)

        # 为词语中的每个字找到所有同音字
        candidates = []
        for py in word_pinyin:
            chars = self.pinyin_dict.get(py, [])
            if not chars:
                return []  # 如果某个字没有同音字，则无法构成同音词
            candidates.append(chars)

        all_combinations = itertools.product(*candidates)
        homophones = [
            "".join(combo)
            for combo in all_combinations
            if ("".join(combo) != word and "".join(combo) in jieba.dt.FREQ)
        ]

        return homophones

    def create_typo_sentence(self, sentence):
        """
        为输入句子生成一个包含错别字的版本。
        这是核心的错别字生成方法，其流程如下：
        1. 使用 jieba 对输入句子进行分词。
        2. 遍历每个词语：
           a. 如果词语长度大于1，根据 `word_replace_rate` 概率尝试进行整词替换。
              如果找到了合适的同音词，则替换并跳过后续步骤。
           b. 如果不进行整词替换，则遍历词语中的每个汉字。
           c. 对每个汉字，调用 `_char_replace` 方法，根据 `error_rate` 和词语长度调整后的概率，
              决定是否进行单字替换。
        3. 将处理后的词语拼接成最终的错别字句子。
        4. 从所有发生的替换中，随机选择一个作为修正建议返回。

        Args:
            sentence (str): 原始中文句子。

        Returns:
            tuple: 包含三个元素的元组：
                - original_sentence (str): 原始句子。
                - typo_sentence (str): 包含错别字的句子。
                - correction_suggestion (Optional[tuple(str, str)]): 一个随机的修正建议，格式为 (错字/词, 正确字/词)，或 None。
        """
        result = []
        typo_info = []  # 用于调试，记录详细的替换信息
        word_typos = []  # 记录 (错词, 正确词)
        char_typos = []  # 记录 (错字, 正确字)

        # 对句子进行分词
        words = self._segment_sentence(sentence)

        for word in words:
            # 如果是标点符号或非中文字符，直接保留
            if all(not self._is_chinese_char(c) for c in word):
                result.append(word)
                continue

            word_pinyin = self._get_word_pinyin(word)

            # 步骤1: 尝试进行整词替换
            if len(word) > 1 and random.random() < self.word_replace_rate:
                word_homophones = self._get_word_homophones(word)
                if word_homophones:
                    typo_word = random.choice(word_homophones)
                    orig_freq = sum(self.char_frequency.get(c, 0) for c in word) / len(word)
                    typo_freq = sum(self.char_frequency.get(c, 0) for c in typo_word) / len(typo_word)

                    result.append(typo_word)
                    typo_info.append(
                        (
                            word,
                            typo_word,
                            " ".join(self._get_word_pinyin(word)),
                            " ".join(self._get_word_pinyin(typo_word)),
                            orig_freq,
                            typo_freq,
                        )
                    )
                    word_typos.append((typo_word, word))
                    continue

            new_word = "".join(
                self._char_replace(char, py, len(word), typo_info, char_typos) for char, py in zip(word, word_pinyin)
            )
            result.append(new_word)

        all_typos = word_typos + char_typos
        correction_suggestion = random.choice(all_typos) if all_typos and random.random() < 0.5 else None
        return sentence, "".join(result), correction_suggestion

    def _char_replace(self, char, py, word_len, typo_info, char_typos):
        """
        根据概率替换单个汉字。
        这个内部方法处理单个汉字的替换逻辑。

        Args:
            char (str): 要处理的原始汉字。
            py (str): 原始汉字的拼音。
            word_len (int): 原始汉字所在的词语的长度。
            typo_info (list): 用于记录详细调试信息的列表。
            char_typos (list): 用于记录 (错字, 正确字) 的列表。

        Returns:
            str: 替换后的汉字（可能是原汉字，也可能是错别字）。
        """
        # 根据词语长度调整错误率：词语越长，单个字出错的概率越低。
        # 这是一个启发式规则，模拟人们在输入长词时更不容易打错单个字。
        char_error_rate = self.error_rate * (0.7 ** (word_len - 1))
        if random.random() >= char_error_rate:
            return char

        # 获取发音和频率都相似的候选错别字
        similar_chars = self._get_similar_frequency_chars(char, py)
        if not similar_chars:
            return char

        # 从候选列表中随机选择一个
        typo_char = random.choice(similar_chars)
        orig_freq = self.char_frequency.get(char, 0)
        typo_freq = self.char_frequency.get(typo_char, 0)

        # 根据频率差异再次进行概率判断，决定是否执行替换
        if random.random() >= self._calculate_replacement_probability(orig_freq, typo_freq):
            return char

        # 执行替换，并记录相关信息
        typo_py = pinyin(typo_char, style=Style.TONE3)
        typo_info.append((char, typo_char, py, typo_py, orig_freq, typo_freq))
        char_typos.append((typo_char, char))
        return typo_char

    @staticmethod
    def format_typo_info(typo_info):
        """
        将错别字生成过程中的详细信息格式化为可读字符串。

        Args:
            typo_info (list): `create_typo_sentence` 方法生成的详细信息列表。

        Returns:
            str: 格式化后的字符串，用于调试和分析。
        """
        if not typo_info:
            return "未生成错别字"

        result = []
        for orig, typo, orig_py, typo_py, orig_freq, typo_freq in typo_info:
            # 判断是整词替换还是单字替换
            is_word = " " in orig_py
            if is_word:
                error_type = "整词替换"
            else:
                # 判断是声调错误还是同音字替换
                tone_error = orig_py[:-1] == typo_py[:-1] and orig_py[-1] != typo_py[-1]
                error_type = "声调错误" if tone_error else "同音字替换"

            result.append(
                f"原文：{orig}({orig_py}) [频率：{orig_freq:.2f}] -> "
                f"替换：{typo}({typo_py}) [频率：{typo_freq:.2f}] [{error_type}]"
            )

        return "\n".join(result)

    def set_params(self, **kwargs):
        """
        动态设置生成器的参数。

        Args:
            **kwargs: 键值对参数，可设置的参数包括:
                - error_rate (float)
                - min_freq (int)
                - tone_error_rate (float)
                - word_replace_rate (float)
                - max_freq_diff (int)
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
                logger.info(f"参数 {key} 已更新为 {value}")
            else:
                logger.warning(f"尝试设置不存在的参数: {key}")


def main():
    # 创建错别字生成器实例
    typo_generator = ChineseTypoGenerator(error_rate=0.03, min_freq=7, tone_error_rate=0.02, word_replace_rate=0.3)

    # 获取用户输入
    sentence = input("请输入中文句子：")

    # 创建包含错别字的句子
    start_time = time.time()
    original_sentence, typo_sentence, correction_suggestion = typo_generator.create_typo_sentence(sentence)

    # 打印结果
    print("\n原句：", original_sentence)
    print("错字版：", typo_sentence)

    # 打印纠正建议
    if correction_suggestion:
        print("\n随机纠正建议：")
        print(f"应该改为：{correction_suggestion}")

    # 计算并打印总耗时
    end_time = time.time()
    total_time = end_time - start_time
    print(f"\n总耗时：{total_time:.2f}秒")


if __name__ == "__main__":
    main()
