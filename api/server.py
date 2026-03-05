"""
八字命理 AI 命师 — API Server
FastAPI + Anthropic Claude (streaming)
"""

import os, sys, json, time, uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import anthropic

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from bazi import calculate_bazi, chart_to_dict, chart_to_prompt

CLAUDE_KEY = os.environ.get("CLAUDE_API_KEY", "")
PRICE_CENTS = int(os.environ.get("PRICE_CENTS", "0"))  # set >0 to enable paid mode

client = anthropic.Anthropic(api_key=CLAUDE_KEY) if CLAUDE_KEY else None

SYSTEM_PROMPT = """你是一位融通古今的八字命理大师，深研以下典籍：
《三命通会》（万民英）·《滴天髓征义》（任铁樵批注）
陆致极《八字命理学基础教程》《八字命理动态分析教程》《现代八字命理学纲要》
梁湘润《八字务实研究》《八字细批终身详解》

【分析原则，必须遵守】
1. 以日主为核心，先定旺衰，再论格局，后取用神
2. 旺衰三要素：月令（最重）、地支（次）、天干（辅）
3. 格局优先：正格（财官印食伤）成格者以格论命；从格（从强/弱/儿/财/杀）需验证不破
4. 用神取用：身旺取食财官，身弱取印比，特殊格局另议
5. 每个结论必须引用命盘中的具体干支作为依据，不得空论

【十神象意参照梁湘润体系】
正官：仕途名誉、约束力、配偶（女命）
七杀：压力竞争、权威魄力，需食神/正印制化方为用
正印：智慧学业、母亲、文书资质
偏印：技艺专长、思维独特，过旺则多虑
正财：稳健财富、妻子（男命）、脚踏实地
偏财：父亲、横财机遇、社交广
食神：才华寿元、子女（女命）、福气
伤官：创意才华、桀骜不驯，克官，需谨慎
比肩：兄弟同类、合作竞争、独立自主
劫财：劫财破财风险、竞争耗损

【输出规范】
- 分段清晰，标题加【】，每段落重点突出
- 语气：专业、平实、有温度，绝不吓唬人
- 具体：每个判断后附（×柱×干/支，×五行关系）
- 长度：1500-2500字之间，核心分析不遗漏，废话不展开
- 最后给出3条实用建议（符合命格的发展方向）

【禁止】
绝对化预言、无依据的恐吓、违背伦理的内容"""


app = FastAPI(title="八字命理AI", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 临时存储待解读命盘（生产环境建议换 Redis）
_pending: dict[str, dict] = {}


class CalcRequest(BaseModel):
    name: str
    gender: str = '男'
    year: int
    month: int
    day: int
    hour: int
    minute: int = 0
    question: str = '综合命运解读'


@app.get("/")
def root():
    idx = os.path.join(static_dir, "index.html")
    if os.path.exists(idx):
        return FileResponse(idx)
    return {"status": "ok", "message": "八字命理AI API"}


@app.get("/health")
def health():
    return {"status": "ok", "claude": bool(CLAUDE_KEY)}


@app.post("/api/calculate")
def calculate(req: CalcRequest):
    """免费：排盘计算，返回四柱数据"""
    try:
        chart = calculate_bazi(req.name, req.year, req.month, req.day,
                               req.hour, req.minute, req.gender)
        d = chart_to_dict(chart)
        # 同时保存 prompt 供解读使用
        rid = str(uuid.uuid4())
        _pending[rid] = {
            "chart": d,
            "prompt": chart_to_prompt(chart, req.question),
            "ts": time.time(),
        }
        d["reading_id"] = rid
        return d
    except Exception as e:
        raise HTTPException(400, f"排盘失败：{e}")


@app.get("/api/reading/{reading_id}")
def reading_stream(reading_id: str):
    """
    流式 AI 解读（SSE）
    前端 EventSource 接收，逐字显示
    """
    if reading_id not in _pending:
        raise HTTPException(404, "命盘数据已过期，请重新排盘")

    if not client:
        raise HTTPException(503, "CLAUDE_API_KEY 未配置，无法生成解读")

    prompt_text = _pending[reading_id]["prompt"]

    def generate():
        try:
            with client.messages.stream(
                model="claude-opus-4-5",
                max_tokens=3000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt_text}],
            ) as stream:
                for chunk in stream.text_stream:
                    yield f"data: {json.dumps({'t': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/ask")
def ask_question(reading_id: str, question: str):
    """追问（同一命盘，不同问题）"""
    if reading_id not in _pending:
        raise HTTPException(404, "命盘已过期，请重新排盘")
    chart_dict = _pending[reading_id]["chart"]
    # 重建 prompt
    from bazi import BaZiChart, Pillar, TIANGAN, DIZHI, CANGGAN, WUXING_GAN, WUXING_ZHI
    # 简单方式：直接在原命盘文本后追加问题
    base_prompt = _pending[reading_id]["prompt"]
    new_prompt = base_prompt + f"\n\n【追加问题】\n{question}\n\n请针对此追加问题，基于上述命盘数据给出专项解读。"

    if not client:
        raise HTTPException(503, "CLAUDE_API_KEY 未配置")

    def generate():
        try:
            with client.messages.stream(
                model="claude-opus-4-5",
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": new_prompt}],
            ) as stream:
                for chunk in stream.text_stream:
                    yield f"data: {json.dumps({'t': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
