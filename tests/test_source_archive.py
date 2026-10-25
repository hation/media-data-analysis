# -*- coding: utf-8 -*-
"""
源数据归档 · 黑盒测试（TDD）
==============================
合成数据 + 子进程运行 analyze.py，验证「7. 源数据归档」：
跑完分析后，把本次读取的一对源 CSV 复制一份到批次目录 源数据/，
并从 input/ 移动到项目根 archive/（与 input 平级）。

约束：
- 纯标准库（unittest + subprocess + tempfile + shutil），无第三方依赖；
- 不 import analyze.py（其 import 即执行全流程），以子进程方式在临时沙箱中运行；
- 沙箱：复制仓库根 analyze.py 与 config/品类规则.json，写入合成 input CSV。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONTENTS_HEADER = ["aweme_id", "aweme_type", "title", "desc", "create_time", "creator_hash",
                   "nickname", "liked_count", "collected_count", "comment_count", "share_count",
                   "last_modify_ts", "aweme_url", "cover_url", "video_download_url",
                   "music_download_url", "note_download_url", "source_keyword"]
COMMENTS_HEADER = ["comment_id", "create_time", "aweme_id", "content", "creator_hash", "nickname",
                   "user_homepage", "sub_comment_count", "like_count", "last_modify_ts",
                   "parent_comment_id", "pictures"]

CONTENTS_NAME = "search_contents_2026-10-21-17-47_硬盘_douyin.csv"
COMMENTS_NAME = "search_comments_2026-10-21-17-47_硬盘_douyin.csv"


class SourceArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="source_archive_")
        shutil.copy(os.path.join(REPO_ROOT, "analyze.py"), self.tmp)
        config_dir = os.path.join(self.tmp, "config")
        os.makedirs(config_dir)
        shutil.copy(os.path.join(REPO_ROOT, "config", "品类规则.json"), config_dir)
        self.input_dir = os.path.join(self.tmp, "input")
        os.makedirs(self.input_dir)

        # 视频表：1 条（表头与 MediaCrawler 一致，aweme_url 等可空）
        self.contents_path = os.path.join(self.input_dir, CONTENTS_NAME)
        with open(self.contents_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write("aweme_id,aweme_type,title,desc,create_time,creator_hash,nickname,"
                    "liked_count,collected_count,comment_count,share_count,last_modify_ts,"
                    "aweme_url,cover_url,video_download_url,music_download_url,"
                    "note_download_url,source_keyword\n")
            f.write("111,0,测试,测试,100,hash1,创1,1,1,1,1,1,,,,,,硬盘\n")

        # 评论表：1 条
        self.comments_path = os.path.join(self.input_dir, COMMENTS_NAME)
        with open(self.comments_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write("comment_id,create_time,aweme_id,content,creator_hash,nickname,"
                    "user_homepage,sub_comment_count,like_count,last_modify_ts,"
                    "parent_comment_id,pictures\n")
            f.write("1,100,111,想买,hash1,评1,,0,0,1,0,\n")

        # 记录写入原文，用于与 archive/ 副本做文本相等比较
        for name in (CONTENTS_NAME, COMMENTS_NAME):
            with open(os.path.join(self.input_dir, name), encoding="utf-8-sig") as fh:
                setattr(self, "expected_" + name, fh.read())

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

    def test_source_archive(self):
        proc = self.run_analyze()
        # 1. 子进程 exit code == 0
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

        # 2. 批次目录 源数据/ 含两个副本
        src_backup = os.path.join(self.batch_dir(), "源数据")
        for name in (CONTENTS_NAME, COMMENTS_NAME):
            self.assertTrue(os.path.exists(os.path.join(src_backup, name)),
                            f"批次源数据/ 未找到副本 {name}")

        # 3. input/ 顶层不再存在这两个文件（无 .csv 残留）
        self.assertFalse([f for f in os.listdir(self.input_dir) if f.endswith(".csv")],
                         f"input/ 仍残留 CSV: {os.listdir(self.input_dir)}")

        # 4. archive/ 存在且含这两个文件，内容与写入原文完全一致
        archive_dir = os.path.join(self.tmp, "archive")
        self.assertTrue(os.path.isdir(archive_dir), "项目根 archive/ 不存在")
        for name in (CONTENTS_NAME, COMMENTS_NAME):
            target = os.path.join(archive_dir, name)
            self.assertTrue(os.path.exists(target), f"archive/ 未找到 {name}")
            with open(target, encoding="utf-8-sig") as fh:
                self.assertEqual(fh.read(), getattr(self, "expected_" + name),
                                 f"archive/{name} 内容与原文不一致")

        # 5. 运行摘要末尾含归档说明行
        with open(os.path.join(self.batch_dir(), "运行摘要.txt"), encoding="utf-8") as f:
            summary = f.read()
        self.assertTrue(
            summary.rstrip().endswith("源数据归档: 2 个文件已复制至批次源数据/ 并移出 input 至 archive/"),
            f"运行摘要缺少归档说明:\n{summary}")

        # 6. 分析本身仍正常产出（潜在客户名单.csv 存在）
        self.assertTrue(os.path.exists(os.path.join(self.batch_dir(), "潜在客户名单.csv")),
                        "未找到潜在客户名单.csv")


if __name__ == "__main__":
    unittest.main()
