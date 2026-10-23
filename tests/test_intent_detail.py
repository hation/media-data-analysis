# -*- coding: utf-8 -*-
"""
意向评论明细 · 黑盒测试（TDD）
==============================
合成数据 + 子进程运行 analyze.py，验证新增产出「意向评论明细.csv」：
每条命中意向判定（score >= 2）的评论一行，携带所在视频标题/创作者/链接，按评论时间倒序。

约束：
- 纯标准库（unittest + subprocess），无第三方依赖；
- 不 import analyze.py（其 import 即执行全流程），以子进程方式在临时沙箱中运行；
- 沙箱：复制仓库根 analyze.py 与 config/品类规则.json，写入合成 input CSV；
- 产出 CSV 用 utf-8-sig 读取。
"""
import csv
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONTENTS_HEADER = ["aweme_id", "aweme_type", "title", "desc", "create_time", "creator_hash",
                   "nickname", "liked_count", "collected_count", "comment_count", "share_count",
                   "last_modify_ts", "aweme_url", "cover_url", "video_download_url",
                   "music_download_url", "note_download_url", "source_keyword"]
COMMENTS_HEADER = ["comment_id", "create_time", "aweme_id", "content", "creator_hash", "nickname",
                   "user_homepage", "sub_comment_count", "like_count", "last_modify_ts",
                   "parent_comment_id", "pictures"]


def fmt_ts(ts):
    """与 analyze.ts_to_str 一致的本地时间字符串（同一台机器时区相同，可作预期）。"""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


class IntentDetailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="intent_detail_")
        shutil.copy(os.path.join(REPO_ROOT, "analyze.py"), self.tmp)
        config_dir = os.path.join(self.tmp, "config")
        os.makedirs(config_dir)
        shutil.copy(os.path.join(REPO_ROOT, "config", "品类规则.json"), config_dir)
        self.input_dir = os.path.join(self.tmp, "input")
        os.makedirs(self.input_dir)

        contents_path = os.path.join(self.input_dir,
                                     "search_contents_2026-10-21-17-47_硬盘_douyin.csv")
        comments_path = os.path.join(self.input_dir,
                                     "search_comments_2026-10-21-17-47_硬盘_douyin.csv")

        # 视频表：111 有链接；222 无链接（触发回退）
        with open(contents_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CONTENTS_HEADER)
            w.writeheader()
            w.writerow({"aweme_id": "111", "title": "固态硬盘推荐", "nickname": "创者甲",
                        "aweme_url": "https://www.douyin.com/video/111"})
            w.writerow({"aweme_id": "222", "title": "机械硬盘避雷", "nickname": "创者乙",
                        "aweme_url": ""})

        # 评论表：c1~c3/c5 意向（score>=2）；c4 无意图（不收）；c5 无效时间戳
        with open(comments_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COMMENTS_HEADER)
            w.writeheader()
            for row in [
                {"comment_id": "1", "create_time": "100", "aweme_id": "111",
                 "content": "想买固态硬盘求链接", "creator_hash": "u1", "nickname": "甲",
                 "user_homepage": "https://www.douyin.com/user/u1", "like_count": "5"},
                {"comment_id": "2", "create_time": "200", "aweme_id": "222",
                 "content": "这个硬盘多少钱", "creator_hash": "u2", "nickname": "乙",
                 "user_homepage": "https://www.douyin.com/user/u2", "like_count": "0"},
                {"comment_id": "3", "create_time": "300", "aweme_id": "999",
                 "content": "太贵了求推荐", "creator_hash": "u3", "nickname": "丙",
                 "user_homepage": "https://www.douyin.com/user/u3", "like_count": "1"},
                {"comment_id": "4", "create_time": "400", "aweme_id": "111",
                 "content": "路过看看", "creator_hash": "u4", "nickname": "丁",
                 "user_homepage": "https://www.douyin.com/user/u4", "like_count": "0"},
                {"comment_id": "5", "create_time": "not-a-number", "aweme_id": "111",
                 "content": "准备买一个试试", "creator_hash": "u1", "nickname": "甲",
                 "user_homepage": "https://www.douyin.com/user/u1", "like_count": "0"},
            ]:
                w.writerow(row)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_analyze(self):
        return subprocess.run(
            [sys.executable, "analyze.py", self.input_dir],
            cwd=self.tmp, capture_output=True, text=True, encoding="utf-8", timeout=120)

    def batch_dir(self):
        out_root = os.path.join(self.tmp, "output")
        dirs = [os.path.join(out_root, d) for d in os.listdir(out_root)
                if os.path.isdir(os.path.join(out_root, d))]
        self.assertTrue(dirs, "未生成 output 批次目录")
        return sorted(dirs)[-1]

    def read_output_csv(self, name):
        p = os.path.join(self.batch_dir(), name)
        self.assertTrue(os.path.exists(p), f"未找到产出 {name}: {p}")
        with open(p, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def test_intent_detail(self):
        proc = self.run_analyze()
        # 1. 子进程 exit code == 0
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

        rows = self.read_output_csv("意向评论明细.csv")
        # 2. 明细共 4 行（c4 不收）
        self.assertEqual(len(rows), 4)

        # 3. 行序按「评论时间」倒序：c3(300) → c2(200) → c1(100) → c5(无效值)
        self.assertEqual([r["评论内容"] for r in rows],
                         ["太贵了求推荐", "这个硬盘多少钱", "想买固态硬盘求链接", "准备买一个试试"])
        self.assertEqual([r["评论时间"] for r in rows],
                         [fmt_ts(300), fmt_ts(200), fmt_ts(100), "not-a-number"])

        by_content = {r["评论内容"]: r for r in rows}
        c1, c2, c3 = (by_content[k] for k in
                      ("想买固态硬盘求链接", "这个硬盘多少钱", "太贵了求推荐"))

        # 4. 视频链接：命中取 aweme_url；空回退 /video/<aweme_id>；关联不到留空
        self.assertEqual(c1["视频链接"], "https://www.douyin.com/video/111")
        self.assertEqual(c2["视频链接"], "https://www.douyin.com/video/222")  # 回退
        self.assertEqual(c3["视频标题"], "")
        self.assertEqual(c3["视频创作者"], "")
        self.assertEqual(c3["视频链接"], "")

        # 5. c5 的评论时间列为原始值 not-a-number（无效时间戳不编造/不归一）
        self.assertEqual(by_content["准备买一个试试"]["评论时间"], "not-a-number")

        # 6. 同用户 u1 出现两次（c1/c5）；名单人数（u1/u2/u3=3）≤ 明细行数（4）
        users = [r["用户ID"] for r in rows]
        self.assertEqual(users.count("u1"), 2)
        leads = self.read_output_csv("潜在客户名单.csv")
        lead_ids = {r["用户ID"] for r in leads}
        self.assertEqual(lead_ids, {"u1", "u2", "u3"})
        self.assertLessEqual(len(lead_ids), len(rows))

        # 7. 运行摘要含明细行数
        with open(os.path.join(self.batch_dir(), "运行摘要.txt"), encoding="utf-8") as f:
            summary = f.read()
        self.assertIn("意向评论明细: 4 条", summary)


if __name__ == "__main__":
    unittest.main()
