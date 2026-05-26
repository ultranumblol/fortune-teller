"""
说书稿生成脚本 - 使用 DeepSeek 将小说原文改编为现代有声书风格说书稿
"""

import os
import json
import yaml
import click
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

load_dotenv()
console = Console()


def load_config():
    """加载配置文件"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_client(config: dict) -> OpenAI:
    """初始化 DeepSeek 客户端"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        console.print("[red]错误: 未设置 DEEPSEEK_API_KEY 环境变量[/red]")
        console.print("[dim]请在 .env 文件中设置，或 export DEEPSEEK_API_KEY=xxx[/dim]")
        raise SystemExit(1)

    return OpenAI(
        api_key=api_key,
        base_url=config["script"]["api_base"]
    )


def build_system_prompt(config: dict, episode_num: int, total_episodes: int) -> str:
    """构建系统提示词"""
    target_words = config["split"]["target_words_per_episode"]
    style_template = config["script"]["style"]
    style = style_template.format(target_words=target_words)

    system_prompt = f"""{style}

附加要求：
- 这是全书第 {episode_num} 期，共预计 {total_episodes} 期
- 如果是第1期，开头要有引人入胜的开场白介绍这本书
- 如果不是第1期，开头简短回顾上期内容（1-2句话）
- 结尾留下悬念，引导听众期待下一期
- 输出纯文本，不要加任何标记符号（如 **、## 等）
- 不要输出"第X期"这样的标题，直接从正文开始
"""
    return system_prompt


def build_user_prompt(raw_content: str, prev_summary: str = None) -> str:
    """构建用户提示词"""
    prompt = ""
    if prev_summary:
        prompt += f"【上期内容概要】\n{prev_summary}\n\n"

    prompt += f"【本期原文素材】\n{raw_content}\n\n"
    prompt += "请将以上原文改编为现代有声书风格的说书稿。"
    return prompt


def generate_episode_script(
    client: OpenAI,
    config: dict,
    raw_content: str,
    episode_num: int,
    total_episodes: int,
    prev_summary: str = None
) -> dict:
    """生成单期说书稿"""
    system_prompt = build_system_prompt(config, episode_num, total_episodes)
    user_prompt = build_user_prompt(raw_content, prev_summary)

    response = client.chat.completions.create(
        model=config["script"]["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=config["script"]["temperature"],
        max_tokens=config["script"]["max_tokens"],
    )

    script_text = response.choices[0].message.content.strip()

    # 生成本期摘要（用于下期衔接）
    summary = generate_summary(client, config, script_text)

    return {
        "script": script_text,
        "summary": summary,
        "word_count": len(script_text),
        "tokens_used": response.usage.total_tokens if response.usage else 0
    }


def generate_summary(client: OpenAI, config: dict, script_text: str) -> str:
    """生成本期内容摘要，用于下期开头衔接"""
    response = client.chat.completions.create(
        model=config["script"]["model"],
        messages=[
            {"role": "system", "content": "用2-3句话概括以下有声书内容的主要情节发展，简洁明了。"},
            {"role": "user", "content": script_text}
        ],
        temperature=0.3,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


def load_index(raw_episodes_dir: str) -> dict:
    """加载拆分索引"""
    index_path = os.path.join(raw_episodes_dir, "index.json")
    if not os.path.exists(index_path):
        console.print(f"[red]错误: 未找到索引文件 {index_path}[/red]")
        console.print("[dim]请先运行 split_novel.py 拆分小说[/dim]")
        raise SystemExit(1)

    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


@click.command()
@click.option("--input-dir", "-i", default="output/raw_episodes", help="原文素材目录")
@click.option("--output-dir", "-o", default=None, help="说书稿输出目录（默认读config）")
@click.option("--start", "-s", type=int, default=1, help="起始期数")
@click.option("--end", "-e", type=int, default=None, help="结束期数（默认全部）")
@click.option("--single", type=int, default=None, help="只生成指定期数")
def main(input_dir: str, output_dir: str, start: int, end: int, single: int):
    """
    将拆分后的原文素材改编为说书稿

    需要先运行 split_novel.py 拆分小说
    """
    config = load_config()

    if not output_dir:
        output_dir = config["output"]["scripts_dir"]
    os.makedirs(output_dir, exist_ok=True)

    # 加载索引
    index = load_index(input_dir)
    episodes = index["episodes"]
    book_name = index["book"]
    total_episodes = index["total_episodes"]

    console.print(f"\n[bold green]🎙️ 开始生成说书稿: 《{book_name}》[/bold green]")
    console.print(f"  总期数: {total_episodes}")

    # 确定生成范围
    if single:
        start, end = single, single
    if end is None:
        end = total_episodes

    episodes_to_process = [ep for ep in episodes if start <= ep["episode"] <= end]
    console.print(f"  本次生成: 第{start}期 ~ 第{end}期（共{len(episodes_to_process)}期）\n")

    # 初始化客户端
    client = get_client(config)

    # 加载已有的摘要（用于衔接）
    summary_path = os.path.join(output_dir, "summaries.json")
    summaries = {}
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            summaries = json.load(f)

    # 逐期生成
    total_tokens = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("生成中...", total=len(episodes_to_process))

        for ep_info in episodes_to_process:
            ep_num = ep_info["episode"]
            progress.update(task, description=f"第{ep_num}期: {ep_info['titles'][0][:20]}")

            # 读取原文素材
            raw_path = os.path.join(input_dir, ep_info["filename"])
            with open(raw_path, "r", encoding="utf-8") as f:
                raw_content = f.read()

            # 获取上期摘要
            prev_summary = summaries.get(str(ep_num - 1))

            # 生成说书稿
            result = generate_episode_script(
                client, config, raw_content,
                ep_num, total_episodes, prev_summary
            )

            # 保存说书稿
            script_filename = f"ep{ep_num:03d}_script.txt"
            script_path = os.path.join(output_dir, script_filename)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(result["script"])

            # 保存摘要
            summaries[str(ep_num)] = result["summary"]
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summaries, f, ensure_ascii=False, indent=2)

            total_tokens += result["tokens_used"]
            progress.advance(task)

            console.print(
                f"  [green]✓[/green] 第{ep_num}期 | "
                f"{result['word_count']}字 | "
                f"tokens: {result['tokens_used']:,}"
            )

    console.print(f"\n[bold green]✅ 说书稿生成完成！[/bold green]")
    console.print(f"  生成期数: {len(episodes_to_process)}")
    console.print(f"  总tokens: {total_tokens:,}")
    console.print(f"  输出目录: {output_dir}/")
    console.print(f"  摘要文件: {summary_path}\n")


if __name__ == "__main__":
    main()
