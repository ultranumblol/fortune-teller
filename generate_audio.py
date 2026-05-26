"""
音频生成脚本 - 使用 Fish Audio TTS 将说书稿转为语音
"""

import os
import json
import yaml
import click
from pathlib import Path
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


def get_session(config: dict):
    """初始化 Fish Audio 客户端"""
    from fish_audio_sdk import Session

    api_key = os.getenv("FISH_AUDIO_API_KEY")
    if not api_key:
        console.print("[red]错误: 未设置 FISH_AUDIO_API_KEY 环境变量[/red]")
        console.print("[dim]请在 .env 文件中设置，或 export FISH_AUDIO_API_KEY=xxx[/dim]")
        console.print("[dim]注册地址: https://fish.audio[/dim]")
        raise SystemExit(1)

    base_url = config["audio"].get("api_base", "https://api.fish.audio")
    return Session(apikey=api_key, base_url=base_url)



def split_text_for_tts(text: str, max_chars: int = 1000) -> list[str]:
    """
    将长文本按段落/句子拆分为适合 TTS 的片段。
    Fish Audio 单次请求建议不超过一定长度以保证质量。
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(para) > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            sentences = []
            temp = ""
            for char in para:
                temp += char
                if char in "。！？；…" and len(temp) > 50:
                    sentences.append(temp)
                    temp = ""
            if temp:
                sentences.append(temp)

            for sent in sentences:
                if len(current_chunk) + len(sent) > max_chars:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sent
                else:
                    current_chunk += sent
        else:
            if len(current_chunk) + len(para) + 1 > max_chars:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para
            else:
                if current_chunk:
                    current_chunk += "\n" + para
                else:
                    current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks



def generate_audio_for_episode(session, text: str, output_path: str, config: dict) -> dict:
    """为单期说书稿生成音频"""
    from fish_audio_sdk import TTSRequest

    voice_id = config["audio"].get("voice_id", "")
    audio_format = config["audio"].get("format", "mp3")

    chunks = split_text_for_tts(text, max_chars=800)

    all_audio_data = b""
    for i, chunk in enumerate(chunks):
        tts_params = {
            "text": chunk,
            "format": audio_format,
            "chunk_length": 200,
            "normalize": True,
            "latency": "normal",
        }

        if voice_id:
            tts_params["reference_id"] = voice_id

        request = TTSRequest(**tts_params)

        audio_bytes = b""
        for chunk_data in session.tts(request):
            audio_bytes += chunk_data

        all_audio_data += audio_bytes

    with open(output_path, "wb") as f:
        f.write(all_audio_data)

    file_size = len(all_audio_data)
    estimated_duration = file_size / (128 * 1024 / 8)

    return {
        "file_size": file_size,
        "estimated_duration_seconds": estimated_duration,
        "chunks_count": len(chunks),
    }


def list_available_voices(session, language: str = "zh"):
    """列出可用的中文音色"""
    models = session.list_models(
        page_size=20,
        page_number=1,
        language=[language],
        sort_by="task_count",
    )
    return models



@click.command()
@click.option("--input-dir", "-i", default=None, help="说书稿目录（默认读config）")
@click.option("--output-dir", "-o", default=None, help="音频输出目录（默认读config）")
@click.option("--start", "-s", type=int, default=1, help="起始期数")
@click.option("--end", "-e", type=int, default=None, help="结束期数")
@click.option("--single", type=int, default=None, help="只生成指定期数")
@click.option("--list-voices", is_flag=True, help="列出可用音色")
def main(input_dir: str, output_dir: str, start: int, end: int, single: int, list_voices: bool):
    """
    将说书稿转换为音频文件

    使用 Fish Audio TTS 生成高质量中文语音
    """
    config = load_config()

    if not input_dir:
        input_dir = config["output"]["scripts_dir"]
    if not output_dir:
        output_dir = config["output"]["audio_dir"]
    os.makedirs(output_dir, exist_ok=True)

    session = get_session(config)

    if list_voices:
        console.print("\n[bold]🎤 Fish Audio 热门中文音色:[/bold]\n")
        try:
            models = list_available_voices(session)
            for i, model in enumerate(models.items, 1):
                console.print(f"  {i:2d}. [cyan]{model.title}[/cyan]")
                console.print(f"      ID: {model._id}")
                if model.description:
                    console.print(f"      简介: {model.description[:60]}")
                console.print()
        except Exception as e:
            console.print(f"[red]获取音色列表失败: {e}[/red]")
        console.print("[dim]将喜欢的音色 ID 填入 config.yaml 的 audio.voice_id 字段[/dim]\n")
        return

    script_files = sorted(Path(input_dir).glob("ep*_script.txt"))
    if not script_files:
        console.print(f"[red]错误: 在 {input_dir} 中未找到说书稿文件[/red]")
        console.print("[dim]请先运行 generate_script.py 生成说书稿[/dim]")
        raise SystemExit(1)

    if single:
        start, end = single, single
    if end is None:
        end = len(script_files)

    files_to_process = []
    for f in script_files:
        try:
            ep_num = int(f.stem.split("_")[0].replace("ep", ""))
            if start <= ep_num <= end:
                files_to_process.append((ep_num, f))
        except ValueError:
            continue

    if not files_to_process:
        console.print(f"[yellow]范围 {start}-{end} 内没有找到说书稿文件[/yellow]")
        return

    voice_id = config["audio"].get("voice_id", "")
    console.print(f"\n[bold green]🔊 开始生成音频[/bold green]")
    console.print(f"  音色ID: {voice_id if voice_id else '(默认)'}")
    console.print(f"  本次生成: 第{start}期 ~ 第{end}期（共{len(files_to_process)}期）\n")

    total_duration = 0
    total_size = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("生成音频...", total=len(files_to_process))

        for ep_num, script_path in files_to_process:
            progress.update(task, description=f"第{ep_num}期音频生成中...")

            with open(script_path, "r", encoding="utf-8") as f:
                script_text = f.read()

            audio_filename = f"ep{ep_num:03d}.mp3"
            audio_path = os.path.join(output_dir, audio_filename)

            if os.path.exists(audio_path):
                console.print(f"  [yellow]⏭️[/yellow] 第{ep_num}期 已存在，跳过")
                progress.advance(task)
                continue

            try:
                result = generate_audio_for_episode(session, script_text, audio_path, config)
                duration_min = result["estimated_duration_seconds"] / 60
                size_mb = result["file_size"] / (1024 * 1024)
                total_duration += result["estimated_duration_seconds"]
                total_size += result["file_size"]

                console.print(
                    f"  [green]✓[/green] 第{ep_num}期 | "
                    f"~{duration_min:.1f}分钟 | "
                    f"{size_mb:.1f}MB | "
                    f"{result['chunks_count']}段"
                )
            except Exception as e:
                console.print(f"  [red]✗[/red] 第{ep_num}期 生成失败: {e}")

            progress.advance(task)

    console.print(f"\n[bold green]✅ 音频生成完成！[/bold green]")
    console.print(f"  总时长: ~{total_duration/60:.1f} 分钟")
    console.print(f"  总大小: {total_size/(1024*1024):.1f} MB")
    console.print(f"  输出目录: {output_dir}/\n")


if __name__ == "__main__":
    main()
