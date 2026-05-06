"""
JSON 工具

功能：
  1. 格式化（美化）
  2. 压缩（最小化）
  3. 转义    —— " → \\"  \\ → \\\\
  4. 去转义  —— \\" → "  \\\\ → \\  \\n\\t 等还原
  5. Unicode 解码  —— \\uXXXX → 中文
  6. URL 解码
  7. 自动修复 —— 去转义后解析失败时，在不修改数据的前提下尝试补全结构
  8. 深度解包 —— 递归展开字符串字段中的内嵌 JSON

author: zsy
"""

import json
import re
from urllib.parse import unquote


# ════════════════════════════════════════════════════════════
#  注释剥离（预处理）
# ════════════════════════════════════════════════════════════

def _strip_comments(text: str) -> str:
    """
    剥离 JSON 中的注释，支持：
      - 单行注释：// ...
      - 多行注释：/* ... */
    仅去除字符串外的注释，不修改字符串内容。
    """
    result = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            result.append(ch)
            if ch == '\\' and i + 1 < n:
                # 转义字符，连同下一个字符一起保留
                i += 1
                result.append(text[i])
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
                result.append(ch)
            elif ch == '/' and i + 1 < n:
                next_ch = text[i + 1]
                if next_ch == '/':
                    # 单行注释，跳到行尾
                    i += 2
                    while i < n and text[i] != '\n':
                        i += 1
                    continue
                elif next_ch == '*':
                    # 多行注释，跳到 */
                    i += 2
                    while i < n - 1 and not (text[i] == '*' and text[i + 1] == '/'):
                        i += 1
                    i += 2  # 跳过 */
                    continue
                else:
                    result.append(ch)
            else:
                result.append(ch)
        i += 1
    return ''.join(result)


# ════════════════════════════════════════════════════════════
#  核心功能
# ════════════════════════════════════════════════════════════

def fmt(text: str, indent: int = 2) -> str:
    """格式化（美化）JSON，自动忽略注释"""
    return json.dumps(json.loads(_strip_comments(text)), ensure_ascii=False, indent=indent)


def compress(text: str) -> str:
    """压缩 JSON（移除字符串外的空白，保留字符串内空格），自动忽略注释"""
    return json.dumps(json.loads(_strip_comments(text)), ensure_ascii=False, separators=(",", ":"))


def escape(text: str) -> str:
    """转义：先压缩 JSON 再整体转义，用于嵌套传输"""
    compressed = compress(text)
    return compressed.replace("\\", "\\\\").replace('"', '\\"')


def unescape(text: str) -> str:
    """
    去转义：仅还原 \\" → " 和 \\\\ → \\，其余转义序列（\\n \\t \\uXXXX 等）
    保持原样，留给后续 JSON 解析器处理。
    这样去转义后的文本可直接作为合法 JSON 文本再次解析，不会产生裸控制字符。
    """
    result = []
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == '"':
                result.append('"')
                i += 2
                continue
            elif nxt == '\\':
                result.append('\\')
                i += 2
                continue
            # \n \t \r \b \f \uXXXX 等保留为转义序列，JSON 解析器会正确处理
        result.append(text[i])
        i += 1
    return ''.join(result)


def decode_unicode(text: str) -> str:
    """Unicode 解码：\\uXXXX → 中文（及其他 Unicode 字符）"""
    return re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda m: chr(int(m.group(1), 16)),
        text,
    )


def decode_url(text: str) -> str:
    """URL 解码：%XX → 原始字符"""
    return unquote(text)


# ════════════════════════════════════════════════════════════
#  自动修复（在不修改数据的前提下补全结构）
# ════════════════════════════════════════════════════════════

def _try_parse(text: str):
    """尝试解析，成功返回对象，失败返回 None"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # 尝试剥离注释后再解析
        try:
            return json.loads(_strip_comments(text))
        except (json.JSONDecodeError, ValueError):
            return None


def _extract_json(text: str) -> tuple[str, str] | tuple[None, None]:
    """
    从含有非 JSON 前后缀的文本中提取第一个完整 JSON 对象或数组。
    通过括号计数找到匹配的结束位置，不修改内容。
    返回 (json字符串, 提取说明) 或 (None, None)
    """
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        pos = 0
        while True:
            start = text.find(start_char, pos)
            if start == -1:
                break
            depth = 0
            in_string = False
            escape_next = False
            found_end = -1
            for i, ch in enumerate(text[start:], start):
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == start_char:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                    if depth == 0:
                        found_end = i
                        break
            if found_end == -1:
                break
            candidate = text[start:found_end + 1]
            if _try_parse(candidate) is not None:
                prefix = text[:start].strip(', \t\n')
                suffix = text[found_end + 1:].strip(', \t\n')
                note = "提取JSON片段"
                if prefix:
                    note += f"（忽略前缀: {prefix[:30]}{'...' if len(prefix) > 30 else ''}）"
                if suffix:
                    note += f"（忽略后缀: {suffix[:30]}{'...' if len(suffix) > 30 else ''}）"
                return candidate, note
            # 当前起点的候选无效，从下一个位置继续搜索
            pos = start + 1
    return None, None


def _repair(text: str) -> tuple[str, str] | tuple[None, str]:
    """
    尝试修复 JSON 结构，仅在原文本前后补充缺失的包裹符号。
    不修改文本内容，只做最保守的外层补全。
    返回 (修复后文本, 修复说明) 或 (None, 失败原因)
    """
    stripped = text.strip()

    # 策略1：包裹为对象
    candidate = stripped if stripped.startswith("{") else "{" + stripped + "}"
    if _try_parse(candidate) is not None:
        return candidate, '已自动补全外层 {}'

    # 策略2：包裹为数组
    candidate = stripped if stripped.startswith("[") else "[" + stripped + "]"
    if _try_parse(candidate) is not None:
        return candidate, '已自动补全外层 []'

    # 策略3：补全尾部缺失的括号
    for suffix in ["}", "]", "}}", "]]", "}]", "]{", "},"]:
        candidate = stripped + suffix
        if _try_parse(candidate) is not None:
            return candidate, f'已自动补全尾部 {suffix!r}'

    # 策略4：补全首部
    for prefix in ["{", "["]:
        candidate = prefix + stripped
        if _try_parse(candidate) is not None:
            return candidate, f'已自动补全首部 {prefix!r}'

    # 策略5：去掉首尾多余的引号后再试
    if stripped.startswith('"') and stripped.endswith('"'):
        inner = stripped[1:-1]
        if _try_parse(inner) is not None:
            return inner, '已去除外层多余引号'

    return None, '无法自动修复，请检查数据格式'


# ════════════════════════════════════════════════════════════
#  深度解包
# ════════════════════════════════════════════════════════════

_MAX_DEPTH = 32


def deep_unwrap(obj, _depth: int = 0) -> tuple[any, int]:
    """
    递归遍历 dict/list，将值为内嵌 JSON 字符串的字段替换为解析后的对象。
    返回 (新对象, 展开字段数)。不修改原始对象。
    """
    if _depth > _MAX_DEPTH:
        return obj, 0

    if isinstance(obj, dict):
        new_dict = {}
        count = 0
        for k, v in obj.items():
            new_v, c = deep_unwrap(v, _depth + 1)
            new_dict[k] = new_v
            count += c
        return new_dict, count

    if isinstance(obj, list):
        new_list = []
        count = 0
        for item in obj:
            new_item, c = deep_unwrap(item, _depth + 1)
            new_list.append(new_item)
            count += c
        return new_list, count

    if isinstance(obj, str):
        s = obj.strip()
        if s and s[0] in ('{', '['):
            parsed = _try_parse(s)
            if parsed is not None:
                # 对解析结果继续递归
                unwrapped, c = deep_unwrap(parsed, _depth + 1)
                return unwrapped, c + 1
        return obj, 0

    return obj, 0


def unescape_and_fmt(text: str, indent: int = 2) -> str:
    """
    去转义 → 尝试格式化，失败则尝试修复后再格式化。
    数据内容绝不修改，只做结构补全。
    """
    unescaped = unescape(text.strip())

    obj = _try_parse(unescaped)
    if obj is not None:
        return json.dumps(obj, ensure_ascii=False, indent=indent)

    # 解析失败 → 尝试修复
    repaired, note = _repair(unescaped)
    if repaired is not None:
        obj = _try_parse(repaired)
        result = json.dumps(obj, ensure_ascii=False, indent=indent)
        print(f"[修复提示] {note}")
        return result

    # 修复失败 → 返回去转义后的原文
    print(f"[修复失败] {note}")
    print("[原文返回] 去转义已完成，但无法解析为合法 JSON")
    return unescaped


# ════════════════════════════════════════════════════════════
#  自动识别
# ════════════════════════════════════════════════════════════

def _has_url_encoding(text: str) -> bool:
    return bool(re.search(r"%[0-9a-fA-F]{2}", text))

def _has_unicode_escape(text: str) -> bool:
    return bool(re.search(r"\\u[0-9a-fA-F]{4}", text))

def _has_escape(text: str) -> bool:
    return '\\"' in text or '\\n' in text or '\\t' in text


def _fmt_obj(obj, indent: int = 2) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=indent)


def _try_fmt(text: str, steps: list, indent: int = 2, allow_extract: bool = False) -> str | None:
    """尝试直接解析 → 结构修复 → （可选）提取片段 → 格式化，成功返回字符串，失败返回 None"""
    obj = _try_parse(text)
    if obj is not None:
        steps.append("格式化")
        return _fmt_obj(obj, indent)
    # 先尝试结构修复（补首尾括号），避免 extract 截断数据
    repaired, note = _repair(text)
    if repaired is not None:
        steps.append(f"自动修复({note})")
        steps.append("格式化")
        return _fmt_obj(_try_parse(repaired), indent)
    # 修复失败再尝试从日志前后缀中提取 JSON 片段
    if allow_extract:
        extracted, note = _extract_json(text)
        if extracted is not None:
            steps.append(note)
            steps.append("格式化")
            return _fmt_obj(_try_parse(extracted), indent)
    return None


def auto(text: str, indent: int = 2, deep: bool = True) -> tuple[str, bool]:
    """
    自动识别数据类型并处理，识别顺序：
      1. URL 编码      → 解码后继续
      2. 已是合法 JSON → 直接格式化（允许从日志前后缀中提取）
      3. 含 Unicode    → 解码后尝试格式化
      4. 含转义序列    → 去转义后尝试格式化（含自动修复，不截断数据）
      5. 兜底          → 转换失败，返回 (原文, False)

    deep=True（默认）：解析成功后对所有字符串字段递归尝试展开内嵌 JSON。
    返回 (结果文本, 是否成功转换为合法JSON)
    """
    steps: list[str] = []
    val = text.strip()

    # Step 1：URL 编码
    if _has_url_encoding(val):
        val = unquote(val)
        steps.append("URL解码")

    # Step 2：直接是合法 JSON（允许从日志前后缀中提取片段）
    # 含转义序列时禁用 extract，避免误匹配转义文本中的括号
    allow_extract = not _has_escape(val)
    result = _try_fmt(val, steps, indent, allow_extract=allow_extract)
    if result is not None:
        result = _apply_deep_unwrap(result, steps, indent, deep)
        _print_steps(steps)
        return result, True

    # Step 3：含 Unicode 转义（\\uXXXX）
    if _has_unicode_escape(val):
        decoded = decode_unicode(val)
        steps_copy = steps + ["Unicode解码"]
        result = _try_fmt(decoded, steps_copy, indent, allow_extract=False)
        if result is not None:
            result = _apply_deep_unwrap(result, steps_copy, indent, deep)
            _print_steps(steps_copy)
            return result, True

    # Step 4：含转义序列（\" \n \t 等），支持多层嵌套转义
    if _has_escape(val):
        current = val
        layer = 0
        while _has_escape(current) and layer < 5:
            current = unescape(current)
            layer += 1
            step_label = "去转义" if layer == 1 else f"去转义x{layer}"
            steps_attempt = steps + [step_label]
            # 去转义后允许提取（处理"日志前缀 + 转义JSON"场景）
            result = _try_fmt(current, steps_attempt, indent, allow_extract=True)
            if result is not None:
                result = _apply_deep_unwrap(result, steps_attempt, indent, deep)
                _print_steps(steps_attempt)
                return result, True

    # Step 5：兜底 → 转换失败
    steps.append("无法识别为合法JSON")
    _print_steps(steps)
    return val, False


def _apply_deep_unwrap(json_str: str, steps: list, indent: int, deep: bool) -> str:
    """解析后对象做深度解包，并在 steps 里追加提示。"""
    if not deep:
        return json_str
    obj = _try_parse(json_str)
    if obj is None:
        return json_str
    unwrapped, count = deep_unwrap(obj)
    if count > 0:
        steps.append(f"深度解包({count}处)")
    return json.dumps(unwrapped, ensure_ascii=False, indent=indent)


def _print_steps(steps: list[str]) -> None:
    print(f"[自动识别] {' → '.join(steps)}")


# ════════════════════════════════════════════════════════════
#  主入口：将内容粘贴到 json_data 文件，运行后结果写入 json_result
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import os

    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")
    input_file  = os.path.join(base_dir, "json_data")
    output_file = os.path.join(base_dir, "json_result")

    if not os.path.exists(input_file):
        open(input_file, "w", encoding="utf-8").close()
        print(f"[提示] 已创建 json_data，请将数据粘贴进去后重新运行")
    else:
        text = open(input_file, encoding="utf-8").read()
        if not text.strip():
            print("[提示] json_data 文件为空，请粘贴数据后重新运行")
        else:
            SEP = "=" * 50
            print(SEP)
            try:
                result, success = auto(text)
                if success:
                    print(result)
                    open(output_file, "w", encoding="utf-8").write(result)
                    print(f"[完成] 结果已写入 json_result")
                else:
                    print("[转换失败] 数据无法解析为合法 JSON，可能原因：")
                    print("  1. 数据被截断，请确认 json_data 内容是否完整")
                    print("  2. 数据格式不是 JSON（如纯文本、XML 等）")
                    print("  3. 存在无法自动修复的语法错误")
                    print(f"  原始数据预览（前200字符）：{text.strip()[:200]}")
            except Exception as e:
                print(f"[错误] 处理过程中发生异常：{e}")
            print(SEP)
