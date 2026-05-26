"""
一键管线脚本 - 串联完整流程：拆分小说 → 生成说书稿 → 生成音频
"""

import os
import sys
import json
import yaml
import click
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
console = Console()


def load_config():
    """加载配置文件"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_env():
    """检查环境变量是否配置"""
    issues = []
    if not os.getenv("DEEPSEEK_API_KEY"):
        issues.append("DEEPSEEK_API_KEY 未设置")
    if not os.getenv("FISH_AUDIO_API_KEY"):
        issues.append("FISH_AUDIO_API_KEY 未设置")
    return issues


def run_step(cmd: list[str], step_name: str) -> bool:
    """运行子步骤"""
    console.print(f"\n[bold blue]{'─'*50}[/bold blue]")
    console.print(f"[bold blue]▶ {step_name}[/bold blue]")
    console.print(f"[dim]  命令: {' '.join(cmd)}[/dim]\n")
    result = subprocess.run(cmd, cwd=str(Path(__file__).parent))
    if result.returncode != 0:
        console.print(f"\n[red]✗ {step_name} 失败 (返回码: {result.returncode})[/red]")
        return False
    return True



@click.command()
@click.argument("novel_path", type=click.Path(exists=True))
@click.option("--book-name", "-n", default=None, help="书名（默认用文件名）")
@click.option("--start", "-s", type=int, default=1, help="起始期数")
@click.option("--end", "-e", type=int, default=None, help="结束期数（默认全部）")
@click.option("--skip-split", is_flag=True, help="跳过拆分步骤（已拆分过）")
@click.option("--skip-script", is_flag=True, help="跳过说书稿生成（已生成过）")
@click.option("--skip-audio", is_flag=True, help="跳过音频生成")
@click.option("--dry-run", is_flag=True, help="只拆分，不调用API")
def main(novel_path, book_name, start, end, skip_split, skip_script, skip_audio, dry_run):
    """
    一键运行完整管线：小说 → 说书稿 → 音频

    NOVEL_PATH: 小说文件路径（txt格式）
    """
    config = load_config()

    if not book_name:
        book_name = Path(novel_path).stem

    console.print(Panel(
        f"[bold white]📖 AI 说书自动化管线[/bold white]\n\n"
        f"  书名: [cyan]{book_name}[/cyan]\n"
        f"  文件: [dim]{novel_path}[/dim]\n"
        f"  范围: 第{start}期 ~ {'全部' if end is None else f'第{end}期'}",
        title="[bold green]AI Storyteller[/bold green]",
        border_style="green",
    ))

    if not dry_run:
        issues = check_env()
        if issues:
            console.print("\n[red]⚠️  环境检查未通过:[/red]")
            for issue in issues:
                console.print(f"  [red]• {issue}[/red]")
            console.print("\n[dim]请复制 .env.example 为 .env 并填入 API Key[/dim]")
            if not skip_script and "DEEPSEEK_API_KEY" in str(issues):
                raise SystemExit(1)
            if not skip_audio and "FISH_AUDIO_API_KEY" in str(issues):
                raise SystemExit(1)

    python_cmd = sys.executable
    raw_episodes_dir = "output/raw_episodes"
    scripts_dir = config["output"]["scripts_dir"]
    audio_dir = config["output"]["audio_dir"]

    # 第一步：拆分小说
    if not skip_split:
        cmd = [python_cmd, "split_novel.py", novel_path, "-n", book_name]
        if not run_step(cmd, "第一步: 拆分小说"):
            raise SystemExit(1)
    else:
        console.print("\n[yellow]⏭️  跳过拆分步骤[/yellow]")

    index_path = os.path.join(raw_episodes_dir, "index.json")
    if not os.path.exists(index_path):
        console.print(f"[red]错误: 未找到拆分索引 {index_path}[/red]")
        raise SystemExit(1)

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    total_episodes = index["total_episodes"]
    actual_end = end if end else total_episodes

    if dry_run:
        console.print(Panel(
            f"[yellow]🏁 Dry Run 完成[/yellow]\n\n"
            f"  总期数: {total_episodes}\n"
            f"  如果继续，将生成第{start}期到第{actual_end}期的说书稿和音频\n\n"
            f"  [dim]去掉 --dry-run 参数运行完整流程[/dim]",
            border_style="yellow",
        ))
        return

    # 第二步：生成说书稿
    if not skip_script:
        cmd = [python_cmd, "generate_script.py", "-i", raw_episodes_dir,
               "-o", scripts_dir, "-s", str(start), "-e", str(actual_end)]
        if not run_step(cmd, "第二步: 生成说书稿 (DeepSeek)"):
            console.print("[yellow]说书稿生成中断，可使用 --skip-split 重新运行[/yellow]")
            raise SystemExit(1)
    else:
        console.print("\n[yellow]⏭️  跳过说书稿生成[/yellow]")

    # 第三步：生成音频
    if not skip_audio:
        cmd = [python_cmd, "generate_audio.py", "-i", scripts_dir,
               "-o", audio_dir, "-s", str(start), "-e", str(actual_end)]
        if not run_step(cmd, "第三步: 生成音频 (Fish Audio)"):
            console.print("[yellow]音频生成中断，可使用 --skip-split --skip-script 重新运行[/yellow]")
            raise SystemExit(1)
    else:
        console.print("\n[yellow]⏭️  跳过音频生成[/yellow]")

    # 完成总结
    console.print(f"\n[bold blue]{'═'*50}[/bold blue]")
    scripts_count = len(list(Path(scripts_dir).glob("ep*_script.txt"))) if os.path.exists(scripts_dir) else 0
    audio_count = len(list(Path(audio_dir).glob("ep*.mp3"))) if os.path.exists(audio_dir) else 0

    table = Table(title="📊 管线执行结果")
    table.add_column("项目", style="cyan")
    table.add_column("结果", style="green")
    table.add_row("书名", book_name)
    table.add_row("总期数", str(total_episodes))
    table.add_row("已生成说书稿", f"{scripts_count} 期")
    table.add_row("已生成音频", f"{audio_count} 期")
    table.add_row("说书稿目录", scripts_dir)
    table.add_row("音频目录", audio_dir)
    console.print(table)

    console.print(Panel(
        "[bold green]🎉 全部完成！[/bold green]\n\n"
        f"  说书稿: [cyan]{scripts_dir}/[/cyan]\n"
        f"  音频:   [cyan]{audio_dir}/[/cyan]\n\n"
        "  [dim]每天取一期音频发布到公众号即可[/dim]",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
