"""批量将经典 SQLAlchemy 模型字段写法

    field = Column(Integer, nullable=False, default=0)

转换为 2.0 推荐的带类型注解写法：

    field: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

脚本特点:
1. 仅处理指定文件(默认: src/common/database/sqlalchemy_models.py)。
2. 自动识别多行 Column(...) 定义 (括号未闭合会继续合并)。
3. 已经是 Mapped 写法的行会跳过。
4. 根据类型名 (Integer / Float / Boolean / Text / String / DateTime / get_string_field) 推断 Python 类型。
5. nullable=True 时自动添加 "| None"。
6. 保留 Column(...) 内的原始参数顺序与内容。
7. 生成 .bak 备份文件，确保可回滚。
8. 支持 --dry-run 查看差异，不写回文件。

局限/注意:
- 简单基于正则/括号计数，不解析完整 AST；非常规写法(例如变量中构造 Column 再赋值)不会处理。
- 复杂工厂/自定义类型未在映射表中的，统一映射为 Any。
- 不自动添加 from __future__ import annotations；如需 Python 3.10 以下更先进类型表达式，请自行处理。

使用方式: (在项目根目录执行)

    python scripts/convert_sqlalchemy_models.py \
        --file src/common/database/sqlalchemy_models.py --dry-run

确认无误后去掉 --dry-run 真实写入。
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

TYPE_MAP = {
    "Integer": "int",
    "Float": "float",
    "Boolean": "bool",
    "Text": "str",
    "String": "str",
    "DateTime": "datetime.datetime",
    # 自定义帮助函数 get_string_field(...) 也返回字符串类型
    "get_string_field": "str",
}


COLUMN_ASSIGN_RE = re.compile(r"^(?P<indent>\s+)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*Column\(")
ALREADY_MAPPED_RE = re.compile(r"^[ \t]*[A-Za-z_][A-Za-z0-9_]*\s*:\s*Mapped\[")


def detect_column_block(lines: list[str], start_index: int) -> tuple[int, int] | None:
    """检测从 start_index 开始的 Column(...) 语句跨越的行范围 (包含结束行)。

    使用括号计数法处理多行。
    返回 (start, end) 行号 (包含 end)。"""
    line = lines[start_index]
    if "Column(" not in line:
        return None
    open_parens = line.count("(") - line.count(")")
    i = start_index
    while open_parens > 0 and i + 1 < len(lines):
        i += 1
        l2 = lines[i]
        open_parens += l2.count("(") - l2.count(")")
    return (start_index, i)


def extract_column_body(block_lines: list[str]) -> str:
    """提取 Column(...) 内部参数文本 (去掉首尾 Column( 和 最后一个 ) )。"""
    joined = "\n".join(block_lines)
    # 找到第一次出现 Column(
    start_pos = joined.find("Column(")
    if start_pos == -1:
        return ""
    inner = joined[start_pos + len("Column(") :]
    # 去掉最后一个 ) —— 简单方式: 找到最后一个 ) 并截断
    last_paren = inner.rfind(")")
    if last_paren != -1:
        inner = inner[:last_paren]
    return inner.strip()


def guess_python_type(column_body: str) -> str:
    # 简单取第一个类型标识符 (去掉前导装饰/空格)
    # 可能形式: Integer, Text, get_string_field(50), DateTime, Boolean
    # 利用正则抓取第一个标识符
    m = re.search(r"([A-Za-z_][A-Za-z0-9_]*)", column_body)
    if not m:
        return "Any"
    type_token = m.group(1)
    py_type = TYPE_MAP.get(type_token, "Any")
    # nullable 检测
    if "nullable=True" in column_body or "nullable = True" in column_body:
        # 避免重复 Optional
        if py_type != "Any" and not py_type.endswith(" | None"):
            py_type = f"{py_type} | None"
        elif py_type == "Any":
            py_type = "Any | None"
    return py_type


def convert_block(block_lines: list[str]) -> list[str]:
    first_line = block_lines[0]
    m_name = re.match(r"^(?P<indent>\s+)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=", first_line)
    if not m_name:
        return block_lines
    indent = m_name.group("indent")
    name = m_name.group("name")
    body = extract_column_body(block_lines)
    py_type = guess_python_type(body)
    # 构造新的多行 mapped_column 写法
    # 保留内部参数的换行缩进: 重新缩进为 indent + 4 空格 (延续原风格: 在 indent 基础上再加 4 空格)
    inner_lines = body.split("\n")
    if len(inner_lines) == 1:
        new_line = f"{indent}{name}: Mapped[{py_type}] = mapped_column({inner_lines[0].strip()})\n"
        return [new_line]
    else:
        # 多行情况
        ind2 = indent + "    "
        rebuilt = [f"{indent}{name}: Mapped[{py_type}] = mapped_column(",]
        for il in inner_lines:
            if il.strip():
                rebuilt.append(f"{ind2}{il.rstrip()}")
        rebuilt.append(f"{indent})\n")
        return [l + ("\n" if not l.endswith("\n") else "") for l in rebuilt]


def ensure_imports(content: str) -> str:
    if "Mapped," in content or "Mapped[" in content:
        # 已经可能存在导入
        if "from sqlalchemy.orm import Mapped, mapped_column" not in content:
            # 简单插到第一个 import sqlalchemy 之后
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if "sqlalchemy" in line and line.startswith("from sqlalchemy"):
                    lines.insert(i + 1, "from sqlalchemy.orm import Mapped, mapped_column")
                    return "\n".join(lines)
    return content


def process_file(path: Path) -> tuple[str, str]:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    i = 0
    out: list[str] = []
    changed = 0
    while i < len(lines):
        line = lines[i]
        # 跳过已是 Mapped 风格
        if ALREADY_MAPPED_RE.match(line):
            out.append(line)
            i += 1
            continue
        if "= Column(" in line and re.match(r"^\s+[A-Za-z_][A-Za-z0-9_]*\s*=", line):
            start, end = detect_column_block(lines, i) or (i, i)
            block = lines[start : end + 1]
            converted = convert_block(block)
            out.extend(converted)
            i = end + 1
            # 如果转换结果与原始不同，计数
            if "".join(converted) != "".join(block):
                changed += 1
        else:
            out.append(line)
            i += 1
    new_content = "".join(out)
    new_content = ensure_imports(new_content)
    # 在文件末尾或头部预留统计信息打印(不写入文件，只返回)
    return original, new_content if changed else original


def main():
    parser = argparse.ArgumentParser(description="批量转换 SQLAlchemy 模型字段为 2.0 Mapped 写法")
    parser.add_argument("--file", default="src/common/database/sqlalchemy_models.py", help="目标模型文件")
    parser.add_argument("--dry-run", action="store_true", help="仅显示差异，不写回")
    parser.add_argument("--write", action="store_true", help="执行写回 (与 --dry-run 互斥)")
    args = parser.parse_args()

    target = Path(args.file)
    if not target.exists():
        raise SystemExit(f"文件不存在: {target}")

    original, new_content = process_file(target)

    if original == new_content:
        print("[INFO] 没有需要转换的内容或转换后无差异。")
        return

    # 简单差异输出 (行对比)
    if args.dry_run or not args.write:
        print("[DRY-RUN] 以下为转换后预览 (仅显示不同段落):")
        import difflib

        diff = difflib.unified_diff(
            original.splitlines(), new_content.splitlines(), fromfile="original", tofile="converted", lineterm=""
        )
        count = 0
        for d in diff:
            print(d)
            count += 1
        if count == 0:
            print("[INFO] 差异为空 (可能未匹配到 Column 定义)。")
        if not args.write:
            print("\n未写回。若确认无误，添加 --write 执行替换。")
        return

    backup = target.with_suffix(target.suffix + ".bak")
    shutil.copyfile(target, backup)
    target.write_text(new_content, encoding="utf-8")
    print(f"[DONE] 已写回: {target}，备份文件: {backup.name}")


if __name__ == "__main__":  # pragma: no cover
    main()
