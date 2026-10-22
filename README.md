# media-data-analysis

对 MediaCrawler 导出的抖音搜索数据做**离线销售分析**（纯 Python 标准库，无大模型、无第三方依赖）。

## 目录结构

```
.
├── analyze.py                  # 离线分析脚本（一键运行）
├── config/品类规则.json         # 意图/规格/品牌词典（通用词 + 品类词，按关键词自动加载）
├── .trae/rules/project_rules.md   # 项目规则（TRAE 自动加载）
├── .trae/skills/analyze-douyin-keyword/  # 标准分析流程 skill
├── input/                      # 【不入库】爬取数据（search_contents_* / search_comments_*）
└── output/                     # 【不入库】分析结果批次（关键词_平台_yyyymmddhhmm/）
```

## 运行

```
python analyze.py [数据目录]
```

- 数据默认读 `input/`，产出写 `output/关键词_平台_yyyymmddhhmm/`（每次运行新批次，不覆盖旧结果）。
- 分析流程（识别关键词 → 规划词典 → 跑脚本 → 提炼新词 → 用户决策重跑）见项目内 SKILL 与说明文档。

## 数据说明

`input/`（爬取数据）与 `output/`（含潜在客户名单、KOC 用户主页链接）**不随仓库提交**，已由 `.gitignore` 排除（目录以 `.gitkeep` 占位保留）。如需分析，请自行将 MediaCrawler 导出的 CSV 放入 `input/` 后运行。

## 其他 Agent 无缝接入

- **Codex**：仓库根目录已提供 `AGENTS.md`（Codex 自动加载的项目指令），克隆后用 Codex 打开项目即自动按五步流程分析，无需额外配置。
- **TRAE**：`.trae/rules/project_rules.md` 与 `.trae/skills/analyze-douyin-keyword/` 在会话中自动加载，规则与 `AGENTS.md` 一致。

