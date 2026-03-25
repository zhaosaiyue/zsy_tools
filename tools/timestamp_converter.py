"""
时间戳转换工具

功能：
  1. 时间戳（秒/毫秒自动识别）→ 日期字符串
  2. 日期字符串 → 毫秒时间戳（自动匹配常用格式）
  3. 支持自定义格式和时区
  4. 打印当前时间戳 / 当前时间

默认格式：%Y-%m-%d %H:%M:%S.%f（精确到毫秒）
默认时区：系统本地时区

author: zsy
"""

from datetime import datetime, timezone
import time

# ── 常用格式常量 ──────────────────────────────────────────
FMT_DEFAULT  = "%Y-%m-%d %H:%M:%S.%f"   # 精确到毫秒，例: 2026-02-23 14:36:15.111
FMT_SECONDS  = "%Y-%m-%d %H:%M:%S"      # 精确到秒，  例: 2026-02-23 14:36:15
FMT_DATE     = "%Y-%m-%d"               # 仅日期，    例: 2026-02-23
# ─────────────────────────────────────────────────────────

def _normalize_ts(ts: int | float) -> float:
    """秒级(10位)/毫秒级(13位) 自动转换为秒级浮点"""
    return ts / 1000 if ts > 1e11 else float(ts)


def to_date_string(ts: int | float, fmt: str = FMT_DEFAULT, tz=None) -> str:
    """
    时间戳 → 格式化日期字符串

    :param ts:  秒级或毫秒级时间戳
    :param fmt: strftime 格式，默认精确到毫秒
    :param tz:  timezone 对象，默认本地时区（None）
    :return:    格式化字符串
    """
    dt = datetime.fromtimestamp(_normalize_ts(ts), tz=tz)
    result = dt.strftime(fmt)
    # 将微秒（6位）截断为毫秒（3位）以对齐 Java .SSS 风格
    if "%f" in fmt:
        result = result[:-3]
    return result


def to_date_string_utc(ts: int | float, fmt: str = FMT_DEFAULT) -> str:
    """时间戳 → UTC 日期字符串"""
    return to_date_string(ts, fmt, tz=timezone.utc)


# ════════════════════════════════════════════════
# 日期字符串 → 时间戳
# ════════════════════════════════════════════════

# 自动匹配的格式列表（顺序：精度从高到低）
_AUTO_PATTERNS = [
    FMT_DEFAULT,         # %Y-%m-%d %H:%M:%S.%f
    FMT_SECONDS,         # %Y-%m-%d %H:%M:%S
    FMT_DATE,            # %Y-%m-%d
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
    "%d-%b-%Y %H:%M:%S",
    "%d-%b-%Y",
]


def to_timestamp(date_str: str, fmt: str | None = None, tz=None) -> int:
    """
    日期字符串 → 毫秒时间戳

    :param date_str: 日期字符串
    :param fmt:      指定格式；为 None 时自动匹配常用格式
    :param tz:       timezone 对象，默认本地时区
    :return:         毫秒时间戳
    :raises ValueError: 无法解析时抛出
    """
    patterns = [fmt] if fmt else _AUTO_PATTERNS
    for pattern in patterns:
        try:
            dt = datetime.strptime(date_str, pattern)
            if tz:
                dt = dt.replace(tzinfo=tz)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    raise ValueError(
        f"无法解析日期字符串: '{date_str}'\n"
        f"支持格式: {', '.join(_AUTO_PATTERNS)}"
    )


# ════════════════════════════════════════════════
# 当前时间工具
# ════════════════════════════════════════════════

def now_timestamp() -> int:
    """当前毫秒时间戳"""
    return int(time.time() * 1000)


def now_date_string(fmt: str = FMT_DEFAULT) -> str:
    """当前时间格式化字符串"""
    return to_date_string(now_timestamp(), fmt)


# ════════════════════════════════════════════════
# 主入口：修改 INPUT 后运行
# ════════════════════════════════════════════════

def _try_parse(s: str, fmt: str) -> bool:
    try:
        datetime.strptime(s, fmt)
        return True
    except ValueError:
        return False


def _detect_fmt(s: str) -> str:
    for p in _AUTO_PATTERNS:
        if _try_parse(s, p):
            return p
    return FMT_SECONDS


if __name__ == "__main__":
    # ── 修改这里后直接运行即可 ─────────────────────────────
    # 纯数字 → 时间戳转日期
    # 日期字符串 → 日期转时间戳
    INPUT = "1747967085000"
    # ────────────────────────────────────────────────────

    SEP = "=" * 40

    print(SEP)
    print(f"当前时间戳:   {now_timestamp()}")
    print(f"当前时间：    {now_date_string()}")
    print(SEP)

    val = INPUT.strip()  # noqa

    if val.lstrip("-").isdigit():
        # ── 时间戳 → 日期 ──
        ms = int(val)
        print(f"输入时间戳:   {ms}")
        print(f"毫秒精度:     {to_date_string(ms, FMT_DEFAULT)}")
        print(f"精确到秒:     {to_date_string(ms, FMT_SECONDS)}")
        print(f"仅日期:       {to_date_string(ms, FMT_DATE)}")
    else:
        # ── 日期字符串 → 时间戳 ──
        try:
            ms = to_timestamp(val)
            fmt_used = _detect_fmt(val)
            print(f"输入日期:     {val}")
            print(f"毫秒时间戳:   {ms}")
        except ValueError as e:
            print(e)

    print(SEP)
