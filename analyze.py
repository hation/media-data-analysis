# -*- coding: utf-8 -*-
"""
抖音搜索数据 · 离线销售分析脚本
================================
纯 Python 标准库实现（csv / re / collections），无需大模型、无需联网、无需第三方依赖。

数据源 : input/ 目录下的两份 MediaCrawler 导出 CSV
         search_contents_*.csv  视频信息（点赞/收藏/评论/转发等）
         search_comments_*.csv  一级评论（含评论者 ID、主页链接）
产出    : output/关键词_平台_yyyymmddhhmm/ 下的多个 CSV
         （每次运行新建一个批次目录，旧结果不会被覆盖）

用法    : python analyze.py [数据目录]  （缺省使用脚本同级 input/ 目录）
"""

import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

# ---------------------------------------------------------------- 路径与目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, "input")
OUT_DIR = os.path.join(BASE_DIR, "output")   # 所有分析结果统一放在 output/
os.makedirs(OUT_DIR, exist_ok=True)

# Windows 控制台中文输出兼容
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 规范文档强制提醒：每次运行都先亮出文档路径，规则/口径以此为准
DOC_PATH = os.path.join(BASE_DIR, "抖音数据销售分析说明.md")
if os.path.exists(DOC_PATH):
    print(f"分析规范文档: {DOC_PATH}")
    print(f"（规则、口径、产出定义以此为准；需要变更规则时，改脚本并同步更新该文档）\n")
else:
    print(f"【警告】未找到规范文档 {DOC_PATH}，请先阅读规范再使用本脚本结果\n")


def find_csv(keyword):
    """按关键词在数据目录中找到最新一个 CSV 文件。"""
    files = [f for f in os.listdir(DATA_DIR) if keyword in f and f.endswith(".csv")]
    if not files:
        raise FileNotFoundError(f"数据目录 {DATA_DIR} 下未找到含 '{keyword}' 的 CSV")
    return os.path.join(DATA_DIR, sorted(files)[-1])


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def dedup(rows, key):
    """按主键去重，保留首次出现的记录。"""
    seen, out = set(), []
    for r in rows:
        k = r.get(key)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def ts_to_str(ts):
    """Unix 时间戳 -> 本地时间字符串；无效则原样返回。"""
    try:
        ts = int(float(ts))
    except (TypeError, ValueError):
        return str(ts)
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- 文件读取与去重
CONTENTS = dedup(read_csv(find_csv("search_contents")), "aweme_id")
COMMENTS = dedup(read_csv(find_csv("search_comments")), "comment_id")
print(f"读取数据: 视频 {len(CONTENTS)} 条 / 评论 {len(COMMENTS)} 条（已按主键去重）\n")

# 批次目录：output/关键词_平台_yyyymmddhhmm（关键词/平台从文件名解析）
_contents_path = find_csv("search_contents")
_name_match = re.search(r"_([^_]+)_([^_]+)\.csv$", os.path.basename(_contents_path))
keyword = _name_match.group(1) if _name_match else CONTENTS[0].get("source_keyword") or "关键词"
platform = _name_match.group(2) if _name_match else "douyin"
BATCH_DIR = os.path.join(OUT_DIR, f"{keyword}_{platform}_{datetime.now().strftime('%Y%m%d%H%M')}")
os.makedirs(BATCH_DIR, exist_ok=True)
print(f"产出批次目录: {BATCH_DIR}\n")

# ---------------------------------------------------------------- 品类规则加载
# 意图词典分两层：
#   通用意图词（购买/询价/已购/咨询/选型/价格敏感）—— 所有品类共用
#   品类专属词（需求词/规格词/统计词）—— 按关键词从 config/品类规则.json 匹配
# 未配置品类的关键词 → 退化为通用词 + 明确警告（避免用错词典而不自知）
CONFIG_PATH = os.path.join(BASE_DIR, "config", "品类规则.json")
with open(CONFIG_PATH, encoding="utf-8") as _f:
    RULES = json.load(_f)
CAT = RULES["品类"].get(keyword)
if CAT is None:
    print(f"【警告】关键词「{keyword}」暂无专属品类规则，将退化为通用意图词（品类规格/品牌词典为空）。")
    print(f"        建议在 {CONFIG_PATH} 的「品类」下补充「{keyword}」的 需求词/规格词/统计词\n")
    CAT = {"需求词": "", "规格词": "", "统计词": []}
INTENT_RULES = [(r["标签"], r["权重"], r["正则"]) for r in RULES["通用意图规则"]] + [
    ("弱-需求", 1, "|".join(x for x in (RULES["通用需求词"], CAT["需求词"]) if x)),
    ("弱-规格", 1, "|".join(x for x in (RULES["通用规格词"], CAT["规格词"]) if x)),
]
BRAND_WORDS = CAT["统计词"]   # 选题清单的品牌/规格词频统计词（品类专属）
print(f"品类规则: {keyword}（意图 {len(INTENT_RULES)} 条 / 统计词 {len(BRAND_WORDS)} 个）\n")


# ================================================================
# 1. 爆款视频识别（互动总量 + 互动结构占比）
#    收藏率/转发率/评论率 = 该互动 / 互动总量 —— 不依赖播放量，
#    用于区分「实用型(高收藏) / 传播型(高转发) / 讨论型(高评论)」爆款。
# ================================================================
def engagement(v):
    return to_int(v["liked_count"]) + to_int(v["collected_count"]) + to_int(v["comment_count"]) + to_int(v["share_count"])


def ratio(v, key):
    e = engagement(v)
    return round(to_int(v[key]) / e, 3) if e > 0 else 0


viral_rows = []
for v in CONTENTS:
    e = engagement(v)
    collect_r, share_r, comment_r = ratio(v, "collected_count"), ratio(v, "share_count"), ratio(v, "comment_count")
    tags = []
    if collect_r >= 0.3:
        tags.append("实用型")
    if share_r >= 0.1:
        tags.append("传播型")
    if comment_r >= 0.1:
        tags.append("讨论型")
    viral_rows.append({
        "aweme_id": v["aweme_id"],
        "标题": v["title"],
        "创作者": v["nickname"],
        "点赞": to_int(v["liked_count"]),
        "收藏": to_int(v["collected_count"]),
        "评论": to_int(v["comment_count"]),
        "转发": to_int(v["share_count"]),
        "互动总量": e,
        "收藏率": collect_r,
        "转发率": share_r,
        "评论率": comment_r,
        "爆款类型": "/".join(tags) if tags else "普通",
        "发布时间": ts_to_str(v["create_time"]),
        "视频链接": v["aweme_url"],
    })
viral_rows.sort(key=lambda r: r["互动总量"], reverse=True)
write_viral = os.path.join(BATCH_DIR, "爆款视频学习清单.csv")
with open(write_viral, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(viral_rows[0].keys()))
    w.writeheader()
    w.writerows(viral_rows)
print(f"[1] 爆款视频学习清单已写出: {write_viral}（{len(viral_rows)} 条，按互动总量降序）")
print(f"    实用型(收藏率>=0.3) {sum(1 for r in viral_rows if '实用型' in r['爆款类型'])} 条 / "
      f"传播型(转发率>=0.1) {sum(1 for r in viral_rows if '传播型' in r['爆款类型'])} 条 / "
      f"讨论型(评论率>=0.1) {sum(1 for r in viral_rows if '讨论型' in r['爆款类型'])} 条")

# 互动结构均值（整体画像）
avg = {k: round(sum(r[k] for r in viral_rows) / len(viral_rows), 3) for k in ["收藏率", "转发率", "评论率"]}
print(f"    整体均值: 收藏率 {avg['收藏率']} / 转发率 {avg['转发率']} / 评论率 {avg['评论率']}\n")


# ================================================================
# 2. 潜在客户识别（正则分层打分 + 按评论者 ID 去重 + 新鲜度排序）
#    意图规则表：命中即累加权重；score>=2 判定为意向用户。
#    去重键优先 creator_hash（评论者 ID），其次 user_homepage，最后昵称。
# ================================================================
# 意图规则表由上方「品类规则加载」从 config/品类规则.json 生成：
# 通用行为意图 + 品类需求词 + 品类规格词，权重与命中判定见说明文档 3.3
INTENT_PATTERNS = [(label, weight, re.compile(pattern, re.IGNORECASE)) for label, weight, pattern in INTENT_RULES]

# 逐评论打分
by_user = defaultdict(lambda: {"score": 0, "labels": [], "likes": 0, "count": 0,
                               "last_ts": 0, "last_content": "", "homepage": "", "videos": []})
for c in COMMENTS:
    content = c["content"] or ""
    score, hits = 0, []
    for label, weight, pattern in INTENT_PATTERNS:
        if pattern.search(content):
            score += weight
            hits.append(label)
    if score < 2:   # 意向判定：至少一个强意图，或两个弱意图
        continue
    key = c["creator_hash"] or c["user_homepage"] or c["nickname"] or "unknown"
    u = by_user[key]
    u["score"] = max(u["score"], score)          # 保留最高分
    u["labels"] = list(dict.fromkeys(u["labels"] + hits))   # 合并去重的意图标签
    u["likes"] += to_int(c["like_count"])        # 评论获赞合计
    u["count"] += 1                              # 意向评论条数
    u["homepage"] = c["user_homepage"] or u["homepage"]
    try:
        ts = int(float(c["create_time"]))
    except (TypeError, ValueError):
        ts = 0
    if ts > u["last_ts"]:                        # 最新意向评论时间（新鲜度）
        u["last_ts"] = ts
        u["last_content"] = content
    if c["aweme_id"] not in u["videos"]:
        u["videos"].append(c["aweme_id"])

leads = []
for key, u in by_user.items():
    leads.append({
        "用户ID": key,
        "意图标签": ",".join(u["labels"]),
        "score": u["score"],
        "评论获赞": u["likes"],
        "意向评论数": u["count"],
        "最新意向评论": ts_to_str(u["last_ts"]),
        "意向评论内容": u["last_content"],
        "用户主页": u["homepage"],
        "所属视频数": len(u["videos"]),
    })

# 分层：>=6 强意向；>=4 中意向；>=2 弱意向
for lead in leads:
    lead["意向层级"] = "强意向" if lead["score"] >= 6 else ("中意向" if lead["score"] >= 4 else "弱意向")
# 新鲜度排序：最新意向评论时间倒序（先跟进刚评论的用户）
leads.sort(key=lambda r: r["最新意向评论"], reverse=True)

# 回填昵称列（同一用户多条评论昵称一致，取首条即可）
nickname_by_key = {}
likes_by_key = defaultdict(int)
for c in COMMENTS:
    key = c["creator_hash"] or c["user_homepage"] or c["nickname"]
    nickname_by_key.setdefault(key, c["nickname"])
    likes_by_key[key] += to_int(c["like_count"])
for lead in leads:
    lead["昵称"] = nickname_by_key.get(lead["用户ID"], "")

fields_leads = ["昵称", "用户ID", "意向层级", "意图标签", "score", "评论获赞", "意向评论数",
                "最新意向评论", "意向评论内容", "用户主页", "所属视频数"]
write_leads = os.path.join(BATCH_DIR, "潜在客户名单.csv")
with open(write_leads, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields_leads)
    w.writeheader()
    for lead in leads:
        w.writerow({k: lead[k] for k in fields_leads})
print(f"[2] 潜在客户名单已写出: {write_leads}（去重后 {len(leads)} 人）")
print(f"    强意向 {sum(1 for l in leads if l['意向层级']=='强意向')} / "
      f"中意向 {sum(1 for l in leads if l['意向层级']=='中意向')} / "
      f"弱意向 {sum(1 for l in leads if l['意向层级']=='弱意向')}\n")


# ================================================================
# 7. 意向评论明细（每条命中意向判定的评论一行，携带所在视频标题/创作者/链接，
#    与名单同口径 score>=2，按评论时间倒序）
# ================================================================
# 构建视频索引：aweme_id -> {标题, 视频创作者, 视频链接}
video_map = {}
for v in CONTENTS:
    video_map[v["aweme_id"]] = {
        "标题": v["title"] or "",
        "视频创作者": v["nickname"] or "",
        "视频链接": v["aweme_url"] or f"https://www.douyin.com/video/{v['aweme_id']}",
    }

# 遍历去重评论，score >= 2 输出一行明细（与名单同口径），按 create_time 数值降序
detail_rows = []
for c in COMMENTS:
    content = c["content"] or ""
    score, hits = 0, []
    for label, weight, pattern in INTENT_PATTERNS:
        if pattern.search(content):
            score += weight
            hits.append(label)
    if score < 2:
        continue
    try:
        ctime = int(float(c["create_time"]))
    except (TypeError, ValueError):
        ctime = 0
    vm = video_map.get(c["aweme_id"], {})
    detail_rows.append({
        "_ts": ctime,
        "昵称": c["nickname"] or "",
        "用户ID": c["creator_hash"] or c["user_homepage"] or c["nickname"] or "",
        "用户主页": c["user_homepage"] or "",
        "得分": score,
        "命中意图标签": ",".join(dict.fromkeys(hits)),
        "评论内容": content,
        "评论获赞": to_int(c["like_count"]),
        "评论时间": ts_to_str(c["create_time"]),
        "视频标题": vm.get("标题", ""),
        "视频创作者": vm.get("视频创作者", ""),
        "视频链接": vm.get("视频链接", ""),
    })
detail_rows.sort(key=lambda r: r["_ts"], reverse=True)
for r in detail_rows:
    r.pop("_ts")

fields_detail = ["昵称", "用户ID", "用户主页", "得分", "命中意图标签", "评论内容", "评论获赞",
                 "评论时间", "视频标题", "视频创作者", "视频链接"]
write_detail = os.path.join(BATCH_DIR, "意向评论明细.csv")
with open(write_detail, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields_detail)
    w.writeheader()
    for r in detail_rows:
        w.writerow({k: r[k] for k in fields_detail})
print(f"[7] 意向评论明细已写出: {write_detail}（{len(detail_rows)} 条，按评论时间倒序）")


# ================================================================
# 3. KOC / 种子客户（全量评论按获赞排序，高影响力用户优先建联，
#    不受意向关键词限制，并标注是否同时是意向用户）
# ================================================================
all_home = {}
for c in COMMENTS:
    key = c["creator_hash"] or c["user_homepage"] or c["nickname"]
    all_home.setdefault(key, c["user_homepage"] or "")

koc_rows = [{
    "昵称": nickname_by_key.get(key, ""),
    "用户ID": key,
    "评论获赞合计": likes_by_key[key],
    "是否意向用户": "是" if key in by_user else "否",
    "用户主页": all_home.get(key, ""),
} for key in sorted(likes_by_key, key=lambda k: likes_by_key[k], reverse=True)[:30]]
write_koc = os.path.join(BATCH_DIR, "KOC种子客户.csv")
with open(write_koc, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(koc_rows[0].keys()))
    w.writeheader()
    w.writerows(koc_rows)
print(f"[3] KOC种子客户已写出: {write_koc}（评论获赞 top {len(koc_rows)}）\n")


# ================================================================
# 4. 选题清单（话题标签 + 品牌/规格词频，纯统计离线可算）
# ================================================================
def tags_in(text):
    return re.findall(r"#([^\s#，。,.!！?？]+)", text or "")


tag_counter = Counter()
for v in CONTENTS:
    for t in tags_in(v["title"]) + tags_in(v["desc"]):
        tag_counter[t.lower()] += 1

# BRAND_WORDS 已由「品类规则加载」从 config/品类规则.json 的品类「统计词」生成
word_counter = Counter()
for v in CONTENTS:
    text = (v["title"] or "").lower()
    for w in BRAND_WORDS:
        if w in text:
            word_counter[w] += 1

topic_rows = [{"话题标签": t, "出现视频数": n} for t, n in tag_counter.most_common(30)]
write_topic = os.path.join(BATCH_DIR, "选题清单.csv")
with open(write_topic, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["话题标签", "出现视频数"])
    w.writeheader()
    w.writerows(topic_rows)
print(f"[4] 选题清单已写出: {write_topic}（话题标签 top {len(topic_rows)}）")
print(f"    标题品牌/规格词频 TOP10: " + ", ".join(f"{k}x{n}" for k, n in word_counter.most_common(10)) + "\n")


# ================================================================
# 5. 视频发布时间分布（星期 / 小时，辅助内容排期）
# ================================================================
weekday_counter = Counter("一二三四五六日"[datetime.fromtimestamp(to_int(v["create_time"])).weekday()] for v in CONTENTS if to_int(v["create_time"]) > 0)
hour_counter = Counter(datetime.fromtimestamp(to_int(v["create_time"])).hour for v in CONTENTS if to_int(v["create_time"]) > 0)
write_time = os.path.join(BATCH_DIR, "发布时间分布.csv")
with open(write_time, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["类型", "值", "视频数"])
    for k, n in weekday_counter.most_common():
        w.writerow(["星期", k, n])
    for k in sorted(hour_counter):
        w.writerow(["小时", k, hour_counter[k]])
print(f"[5] 发布时间分布已写出: {write_time}")
print(f"    星期分布: " + ", ".join(f"{k}→{n}" for k, n in weekday_counter.most_common()))
top_hour = hour_counter.most_common(3)
print(f"    高峰发布时段: " + ", ".join(f"{k}时({n}条)" for k, n in top_hour) + "\n")


# ================================================================
# 6. 运行摘要（可追溯：记录输入与关键指标，下次运行可直接对比）
# ================================================================
summary_lines = [
    f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    f"输入视频文件: {os.path.basename(_contents_path)}",
    f"输入评论文件: {os.path.basename(find_csv('search_comments'))}",
    f"品类规则: {keyword}（来自 config/品类规则.json）",
    f"去重后数据: 视频 {len(CONTENTS)} 条 / 评论 {len(COMMENTS)} 条",
    f"爆款类型: 实用型 {sum(1 for r in viral_rows if '实用型' in r['爆款类型'])} / "
    f"传播型 {sum(1 for r in viral_rows if '传播型' in r['爆款类型'])} / "
    f"讨论型 {sum(1 for r in viral_rows if '讨论型' in r['爆款类型'])}",
    f"互动结构均值: 收藏率 {avg['收藏率']} / 转发率 {avg['转发率']} / 评论率 {avg['评论率']}",
    f"意向用户: 共 {len(leads)} 人（强 {sum(1 for l in leads if l['意向层级'] == '强意向')} / "
    f"中 {sum(1 for l in leads if l['意向层级'] == '中意向')} / 弱 {sum(1 for l in leads if l['意向层级'] == '弱意向')}）",
    f"KOC 名单: {len(koc_rows)} 人 / 选题标签: {len(topic_rows)} 个",
    f"意向评论明细: {len(detail_rows)} 条",
]
write_summary = os.path.join(BATCH_DIR, "运行摘要.txt")
with open(write_summary, "w", encoding="utf-8") as f:
    f.write("\n".join(summary_lines) + "\n")
print(f"[6] 运行摘要已写出: {write_summary}")

print("全部完成。产出批次目录:", BATCH_DIR)
