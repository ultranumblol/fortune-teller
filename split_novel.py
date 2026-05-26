"""
小说拆分脚本 - 将小说原文按章节/字数拆分为每期素材
"""

import re
import os
import json
import yaml
import click
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


def load_config():
    """加载配置文件"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_novel(file_path: str) -> str:
    """读取小说文件"""
    encodings = ["utf-8", "gbk", "gb2312", "gb18030"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法读取文件 {file_path}，请确认文件编码")


def split_by_chapters(text: str, chapter_pattern: str) -> list[dict]:
    """按章节标题拆分小说"""
    pattern = re.compile(chapter_pattern, re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        console.print("[yellow]未检测到章节标题，将按字数直接拆分[/yellow]")
        return [{"title": "全文", "content": text.strip()}]

    chapters = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        # 提取章节标题（取该行内容）
        line_end = text.find("\n", match.start())
        if line_end == -1:
            line_end = match.end()
        title = text[match.start():line_end].strip()

        content = text[start:end].strip()
        chapters.append({"title": title, "content": content})

    # 如果第一个章节之前有内容（如序言），也加进去
    if matches[0].start() > 100:
        preface = text[:matches[0].start()].strip()
        if preface:
            chapters.insert(0, {"title": "楔子", "content": preface})

    return chapters


def merge_into_episodes(chapters: list[dict], config: dict) -> list[dict]:
    """
    将章节合并为每期素材，确保每期字数在目标范围内。
    策略：
    - 短章节合并到一起
    - 长章节拆分
    """
    target = config["split"]["target_words_per_episode"]
    min_words = config["split"]["min_words"]
    max_words = config["split"]["max_words"]

    episodes = []
    current_episode = {"titles": [], "content": "", "word_count": 0}

    for chapter in chapters:
        chapter_words = len(chapter["content"])

        # 如果单章节就超过最大字数，需要拆分
        if chapter_words > max_words:
            # 先把当前缓存的内容作为一期（如果有的话）
            if current_episode["word_count"] >= min_words:
                episodes.append(current_episode)
                current_episode = {"titles": [], "content": "", "word_count": 0}

            # 拆分长章节
            sub_episodes = split_long_chapter(chapter, target, min_words, max_words)
            episodes.extend(sub_episodes)
            continue

        # 如果加上当前章节会超过最大字数
        if current_episode["word_count"] + chapter_words > max_words:
            # 当前缓存足够一期
            if current_episode["word_count"] >= min_words:
                episodes.append(current_episode)
                current_episode = {"titles": [], "content": "", "word_count": 0}

        # 累加到当前期
        current_episode["titles"].append(chapter["title"])
        if current_episode["content"]:
            current_episode["content"] += "\n\n"
        current_episode["content"] += chapter["content"]
        current_episode["word_count"] = len(current_episode["content"])

    # 处理剩余内容
    if current_episode["word_count"] > 0:
        if current_episode["word_count"] < min_words and episodes:
            # 太短了，合并到上一期
            last = episodes[-1]
            last["titles"].extend(current_episode["titles"])
            last["content"] += "\n\n" + current_episode["content"]
            last["word_count"] = len(last["content"])
        else:
            episodes.append(current_episode)

    return episodes


def split_long_chapter(chapter: dict, target: int, min_words: int, max_words: int) -> list[dict]:
    """拆分过长的章节，按段落边界切分"""
    content = chapter["content"]
    paragraphs = content.split("\n")

    episodes = []
    current = {"titles": [chapter["title"]], "content": "", "word_count": 0}
    part_num = 1

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if current["word_count"] + len(para) > max_words and current["word_count"] >= min_words:
            current["titles"] = [f"{chapter['title']}（第{part_num}部分）"]
            episodes.append(current)
            part_num += 1
            current = {"titles": [], "content": "", "word_count": 0}

        if current["content"]:
            current["content"] += "\n"
        current["content"] += para
        current["word_count"] = len(current["content"])

    if current["word_count"] > 0:
        current["titles"] = [f"{chapter['title']}（第{part_num}部分）"]
        episodes.append(current)

    return episodes


def save_episodes(episodes: list[dict], output_dir: str, book_name: str):
    """保存拆分结果"""
    os.makedirs(output_dir, exist_ok=True)

    # 保存索引文件
    index = []
    for i, ep in enumerate(episodes, 1):
        title = "_".join(ep["titles"][:2])  # 取前两个章节名
        # 清理文件名中的非法字符
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:50]
        filename = f"ep{i:03d}_{safe_title}.txt"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(ep["content"])

        index.append({
            "episode": i,
            "titles": ep["titles"],
            "filename": filename,
            "word_count": ep["word_count"]
        })

    # 保存索引
    index_path = os.path.join(output_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"book": book_name, "total_episodes": len(episodes), "episodes": index},
                  f, ensure_ascii=False, indent=2)

    return index


@click.command()
@click.argument("novel_path", type=click.Path(exists=True))
@click.option("--book-name", "-n", default=None, help="书名（默认用文件名）")
@click.option("--output-dir", "-o", default=None, help="输出目录（默认 output/raw_episodes）")
def main(novel_path: str, book_name: str, output_dir: str):
    """
    将小说拆分为每期素材

    NOVEL_PATH: 小说文件路径（txt格式）
    """
    config = load_config()

    if not book_name:
        book_name = Path(novel_path).stem

    if not output_dir:
        output_dir = os.path.join("output", "raw_episodes")

    console.print(f"\n[bold green]📖 开始拆分小说: {book_name}[/bold green]\n")

    # 读取小说
    text = read_novel(novel_path)
    total_words = len(text)
    console.print(f"  总字数: {total_words:,}")

    # 按章节拆分
    chapter_pattern = config["split"]["chapter_pattern"]
    chapters = split_by_chapters(text, chapter_pattern)
    console.print(f"  检测到章节数: {len(chapters)}")

    # 合并为每期素材
    episodes = merge_into_episodes(chapters, config)
    console.print(f"  生成期数: {len(episodes)}")
    console.print(f"  预计更新天数: {len(episodes)} 天\n")

    # 保存
    index = save_episodes(episodes, output_dir, book_name)

    # 展示结果表格
    table = Table(title=f"《{book_name}》拆分结果")
    table.add_column("期数", style="cyan", width=6)
    table.add_column("章节", style="white", max_width=40)
    table.add_column("字数", style="green", width=8)

    for item in index[:20]:  # 只显示前20期
        table.add_row(
            f"第{item['episode']}期",
            " / ".join(item["titles"][:2]),
            f"{item['word_count']:,}"
        )

    if len(index) > 20:
        table.add_row("...", f"（共{len(index)}期）", "...")

    console.print(table)
    console.print(f"\n[green]✅ 拆分完成！结果保存在: {output_dir}/[/green]")
    console.print(f"[dim]   索引文件: {output_dir}/index.json[/dim]\n")


if __name__ == "__main__":
    main()
