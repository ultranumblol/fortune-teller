# 八字命理 AI 命师

基于 Claude AI + 经典命理著作的八字排盘解读系统。

## 理论依据
- 《三命通会》《滴天髓征义》（古典经典）
- 陆致极《八字命理学基础教程》《八字命理动态分析教程》
- 梁湘润《八字务实研究》《八字细批终身详解》

## 功能
- 四柱八字自动排盘（年/月/日/时柱）
- 五行力量统计与可视化
- 大运排列（顺逆推算）
- Claude AI 流式解读（格局用神/流年大运/专项分析）
- 追问功能

## 部署

### 本地运行
```bash
cd fortune-teller
pip install -r requirements.txt
export CLAUDE_API_KEY=sk-ant-xxx
python api/server.py
```

### Railway 部署
1. 推送到 GitHub
2. Railway 导入仓库
3. 添加环境变量 `CLAUDE_API_KEY`
