# AI 说书 - 自动化有声书生产管线

将小说原文自动改编为现代有声书风格说书稿，并生成 AI 配音音频。适合微信公众号日更有声书栏目。

## 功能特点

- **智能拆分** - 按章节自动拆分小说，每期约15分钟（4000-4500字）
- **AI 改编** - DeepSeek 将古典/网络小说改编为适合听觉的现代有声书稿
- **上下衔接** - 自动生成每期摘要，下期开头自然承接
- **高质量配音** - Fish Audio TTS 生成接近真人的中文语音
- **一键流程** - 从原文到音频一条命令搞定
- **断点续做** - 支持指定期数范围，可从中断处继续

## 流程图

```
小说原文(txt) → [拆分] → 每期素材 → [DeepSeek改编] → 说书稿 → [Fish Audio TTS] → 音频(mp3)
```

## 快速开始

### 1. 安装依赖

```bash
# 需要 Python 3.10+
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API Key
```

需要的 API Key：
- **DeepSeek** - https://platform.deepseek.com
- **Fish Audio** - https://fish.audio

### 3. 准备小说文件

```bash
cp 你的小说.txt input/
```

### 4. 一键运行

```bash
python pipeline.py input/你的小说.txt -n "书名"

# 只拆分看看效果（不花钱）
python pipeline.py input/你的小说.txt --dry-run

# 只处理前5期试试水
python pipeline.py input/你的小说.txt --start 1 --end 5

# 从第6期继续
python pipeline.py input/你的小说.txt --skip-split --start 6 --end 10
```

## 分步运行

```bash
# 1. 拆分小说
python split_novel.py input/你的小说.txt -n "书名"

# 2. 生成说书稿
python generate_script.py --start 1 --end 5

# 3. 查看可用音色
python generate_audio.py --list-voices

# 4. 生成音频
python generate_audio.py --start 1 --end 5
```

## 配置说明

编辑 `config.yaml`：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `split.target_words_per_episode` | 每期目标字数 | 4200 |
| `split.chapter_pattern` | 章节标题正则 | `^第[...]+[章回节]` |
| `script.model` | DeepSeek 模型 | deepseek-chat |
| `audio.voice_id` | Fish Audio 音色ID | (平台默认) |

## 费用估算（80万字小说约200期）

| 项目 | 估算 |
|------|------|
| DeepSeek | 约 ¥20-40 |
| Fish Audio TTS | 约 ¥50-100 |
| **合计** | **约 ¥70-140** |

## License

MIT
