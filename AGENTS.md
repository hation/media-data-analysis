# 项目：抖音数据销售分析（离线）

MediaCrawler 导出的抖音搜索数据 → 离线销售分析（纯 Python 标准库，无大模型计算、无第三方依赖）。

## 目录

- `analyze.py` — 离线分析脚本，**唯一计算入口**
- `config/品类规则.json` — 意图/规格/品牌词典（通用词 + 品类词，按关键词自动加载）
- `抖音数据销售分析说明.md` — 规范文档（口径、规则、产出定义，以 0/3.2/3.3/3.8 章节为准）
- `input/` — 爬取数据放这里（`search_contents_*` / `search_comments_*`，同一关键词成对）
- `output/` — 分析结果批次 `output/关键词_平台_yyyymmddhhmm/`（5 个 CSV + 运行摘要.txt）

## 分析流程（五步）

1. **识别关键词（自动）**：从文件名解析（`search_contents|comments_时间戳_关键词_平台.csv`，按 `_` 分段倒数第二段为关键词），失败回退 CSV 的 `source_keyword`。先核对 `input/` 存在该关键词成对文件，缺失先报告，禁止硬跑。
2. **规划词典（大模型介入）**：`config/品类规则.json` 已有关键词 → 直接复用；无 → 规划 需求词/规格词/统计词 写入 config。**只改 config，禁止改 analyze.py**。
3. **运行脚本（纯脚本）**：`python analyze.py`，产出 `output/<批次>`。禁止用大模型替代脚本计算。
4. **提炼遗漏词（大模型介入）**：读 title/desc 与评论，对照词典找漏词，**按标准只收购买信号增强词**：
   - 收：容量单位（12t/24t）、存储技术（叠瓦/tlc/qlc/cmr/smr/sas/raid）、接口/主控/缓存、硬盘品牌名、需求动作词（加装/换固态/拆机）
   - 不收：描述性词（通电/噪音/发热/健康度）、宽泛场景词（服务器/nas）、二手话题词（清零/翻新）
   - 频率只作线索，对每个候选词标注「建议入 / 不建议入」及理由。
5. **用户决策三选一**：入 config 不重跑 / 入 config 并重跑 / 直接结束。选重跑 → 补词进 config 后直接 `python analyze.py`（无大模型），对比运行摘要。

## 硬约束

- 大模型只介入第 2、4 步；第 3、5 步的重跑都是纯脚本。
- 新增词必须让用户三选一，**禁止擅自决定或默认重跑**。
- 改 config 必须同步更新说明文档「3.8」，保持脚本、文档、配置三者一致。
- 每次运行生成新批次目录，禁止覆盖旧批次。
- 昵称已脱敏，定位用户以 `user_homepage` 或 `creator_hash` 为准。

## 开发流程（强制 superpowers 工作流）

任何功能新增、行为修改、Bug 修复（非纯对话/咨询）都必须走 superpowers 工作流，不允许跳过需求梳理与设计评审直接写代码：

1. `brainstorming`：探索需求，逐个澄清问题，与用户核对需求，提出方案并取得用户对设计的确认。
2. 撰写设计文档：保存到 `docs/superpowers/specs/YYYY-MM-DD-<功能名>-design.md`，完成后必须请用户评审该文档；用户批准前不得进入实现。
3. `writing-plans`：将已批准的设计拆解为实现计划，保存到 `docs/superpowers/plans/`。
4. `executing-plans` + `tdd`：按计划实现并用测试验证。
5. 交付记录：写 `docs/superpowers/notes/YYYY-MM-DD-<功能名>.md`（如适用）。

上述 superpowers 流程所需的 skill（`brainstorming`、`writing-plans`、`executing-plans`、`tdd`、`test-driven-development` 等）视为本项目默认启用且为必经环节，不要求用户逐次点名或提醒；`grilling`、`grill-me` 仍遵守下文"技能使用限制"。

## 技能使用限制

本节适用于本项目所有任务，包括前端和后端。

- 默认不使用 `shunan-sales-contract`、`wechat-intel-architect`、`grilling`、`grill-me` 这四个技能。
- 只有用户在当前任务中主动提及并要求使用对应技能时，才可加载并应用；不得仅因任务相关或文件中出现技能名称而自动使用。
