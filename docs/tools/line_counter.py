#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Starscream code line counter (zero third-party dependencies).

Design contract (see design.md 2.4/2.5):
  * Input is a fixed snapshot root (produced by `git archive <master SHA>`),
    never the live working tree -- so the report/script themselves can never
    be counted.
  * One scan produces one line-level record per included file. Both the
    T1..T6 table and the business/test/docs-config summary are aggregated
    from that same record set, so "subtotals == total" holds by construction.
  * Built-in assertions enforce AC-4 / AC-5 / AC-6 and the file-count anchor.

Usage:
  python3 docs/tools/line_counter.py --root <snapshot-dir> [--sha <sha>] \
      [--exclude-default] [--format markdown|json] [--include-detail] \
      [--date YYYY-MM-DD]
"""

import argparse
import datetime
import hashlib
import json
import os
import platform
import sys

# --------------------------------------------------------------------------
# Constants: classification rules (design.md 2.4)
# --------------------------------------------------------------------------

CATEGORIES = ("T1", "T2", "T3", "T4", "T5", "T6")
CATEGORY_NAMES = {
    "T1": "Swift 业务源码",
    "T2": "C / ObjC 源码与头文件",
    "T3": "脚本",
    "T4": "构建与工程配置",
    "T5": "文档",
    "T6": "测试代码",
}
# Expected file-count anchor from design.md 5.1 (read-only pre-study, 48 files).
ANCHOR = {"T1": 11, "T2": 1, "T3": 4, "T4": 24, "T5": 5, "T6": 3}

# Rule 0 - directory names pruned entirely.
EXCLUDED_DIRS = {
    ".git", "Pods", "Carthage", "checkouts", "node_modules", "xcuserdata",
}
# Rule 0 - directory *suffix* pruned (Images.xcassets / Assets.xcassets ...).
EXCLUDED_DIR_SUFFIX = (".xcassets",)
# Rule 0 - individual filenames excluded.
EXCLUDED_FILES = {
    "IDEWorkspaceChecks.plist",
}
EXCLUDED_FILE_SUFFIX = (".xcuserstate", ".xccheckout", ".xib", ".storyboard",
                        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns",
                        ".pdf", ".ttf", ".otf", ".woff", ".woff2")
SOURCE_EXTS = (".swift", ".h", ".m", ".c", ".mm")
C_EXTS = (".h", ".m", ".c", ".mm")
SCRIPT_EXTS = (".sh", ".rb")
CONFIG_EXTS = (".podspec", ".xcscheme", ".xcconfig", ".plist", ".yml", ".yaml",
               ".lock", ".resolved", ".modulemap", ".pch", ".xcworkspacedata")
CONFIG_FILENAMES = {"Gemfile", "Podfile", "project.pbxproj"}
DOC_EXTS = (".md", ".txt", ".markdown")
NO_EXT_TEXT_FILES = {"LICENSE"}
# Large low-density text configs; reported separately as an optional reference.
BULKY_CONFIG_NAMES = {"Gemfile.lock", "Package.resolved", "Podfile.lock",
                      "Manifest.lock", "project.pbxproj"}

METRIC_KEYS = ("files", "total", "blank", "comment", "code")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def blank_metrics():
    return {"files": 0, "total": 0, "blank": 0, "comment": 0, "code": 0}


def add_metrics(dst, src):
    for key in METRIC_KEYS:
        dst[key] += src[key]


def classify(rel_path, exclude_default):
    """Return (category_or_None, exclusion_reason_or_None, is_bulky_config)."""
    parts = rel_path.split(os.sep)
    filename = parts[-1]
    ext = os.path.splitext(filename)[1].lower()

    if exclude_default:
        for part in parts[:-1]:
            if part in EXCLUDED_DIRS:
                return None, "excluded-dir:" + part, False
            if part.endswith(EXCLUDED_DIR_SUFFIX):
                return None, "excluded-dir-suffix:" + part, False
        if filename in EXCLUDED_FILES:
            return None, "excluded-file:" + filename, False
        if filename.endswith(EXCLUDED_FILE_SUFFIX):
            return None, "excluded-file-suffix:" + ext, False

    # Rule 1: T6 only applies to source files. Path segment 'Tests/' or a
    # *Tests.* / *Test.* source filename.
    is_source = ext in SOURCE_EXTS
    is_test = is_source and (
        "Tests" in parts[:-1]
        or filename.endswith("Tests" + ext)
        or filename.endswith("Test" + ext)
    )
    if is_test:
        return "T6", None, False

    # Rule 2: Package.swift is a manifest, never Swift business source.
    if filename == "Package.swift":
        return "T4", None, False

    # Rule 3: C / ObjC source & headers.
    if ext in C_EXTS:
        return "T2", None, False

    # Rule 4: all other Swift source (includes examples/** non-test source).
    if ext == ".swift":
        return "T1", None, False

    # Rule 5: shell / ruby DSL scripts (fastlane/Fastfile included).
    if filename == "Fastfile" or ext in SCRIPT_EXTS:
        return "T3", None, False

    # Rule 6: build & engineering configuration.
    if (ext in CONFIG_EXTS
            or filename in CONFIG_FILENAMES
            or (filename.startswith(".") and ext not in DOC_EXTS)):
        return "T4", None, filename in BULKY_CONFIG_NAMES

    # Rule 7: documents; no-extension text licence files.
    if ext in DOC_EXTS or (ext == "" and filename in NO_EXT_TEXT_FILES):
        return "T5", None, False

    # Rule 8: unclassified -- must stay empty for this repository.
    return None, None, False


def count_lines(text):
    """Four-layer line count with a nested-block-comment state machine.

    Returns (total, blank, comment, code). `总行 = 空白 + 注释 + 有效` holds
    line by line by construction.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    # A trailing newline yields a trailing empty element which is not a line.
    # Conversely, no trailing newline still leaves the final fragment as 1 line.
    if lines and lines[-1] == "":
        lines.pop()

    total = blank = comment = code = 0
    block_depth = 0
    for line in lines:
        total += 1
        has_code = False
        i = 0
        n = len(line)
        while i < n:
            if block_depth > 0:
                # Inside a (possibly nested) block comment.
                if line[i:i + 2] == "/*":
                    block_depth += 1
                    i += 2
                elif line[i:i + 2] == "*/":
                    block_depth -= 1
                    i += 2
                else:
                    i += 1
            else:
                if line[i:i + 2] == "//":
                    break                      # rest of line is a line comment
                if line[i:i + 2] == "/*":
                    block_depth += 1
                    i += 2
                    continue
                if line[i].isspace():
                    i += 1
                    continue
                has_code = True
                i += 1

        if line.strip() == "":
            blank += 1
        elif has_code:
            code += 1
        else:
            comment += 1

        assert total == blank + comment + code, "line-layer arithmetic failed"

    return total, blank, comment, code


def read_text(path):
    """Return decoded text, or None if binary/non-UTF-8 (excluded)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan(root, exclude_default, include_detail):
    by_cat = {c: blank_metrics() for c in CATEGORIES}
    total = blank_metrics()
    unclassified = []
    excluded = []
    details = []
    sources = blank_metrics()
    tests = blank_metrics()
    examples = blank_metrics()
    reference = blank_metrics()   # T4 minus bulky configs

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune directories in-place for efficiency & correctness.
        if exclude_default:
            kept = []
            for d in dirnames:
                if d in EXCLUDED_DIRS or d.endswith(EXCLUDED_DIR_SUFFIX):
                    excluded.append(os.path.relpath(os.path.join(dirpath, d), root))
                else:
                    kept.append(d)
            dirnames[:] = kept

        for filename in filenames:
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, root).replace(os.sep, "/")

            text = read_text(full)
            if text is None:
                excluded.append(rel + " (binary/non-UTF-8)")
                continue

            cat, reason, is_bulky = classify(rel, exclude_default)
            if reason is not None:
                excluded.append(rel + " (" + reason + ")")
                continue
            if cat is None:
                unclassified.append(rel)
                continue

            t, b, c, code = count_lines(text)
            rec = {"files": 1, "total": t, "blank": b, "comment": c, "code": code}
            add_metrics(by_cat[cat], rec)
            add_metrics(total, rec)

            # Cross-cutting sub-distributions (same line-level records).
            if "Tests" in rel.split("/")[:-1] or cat == "T6":
                add_metrics(tests, rec)
            elif rel.startswith("Sources/"):
                add_metrics(sources, rec)
            if rel.startswith("examples/"):
                add_metrics(examples, rec)
            if cat == "T4" and not is_bulky:
                add_metrics(reference, rec)

            if include_detail:
                entry = {"path": rel, "category": cat}
                entry.update(rec)
                details.append(entry)

    details.sort(key=lambda d: d["path"])
    excluded.sort()
    unclassified.sort()
    return {
        "by_cat": by_cat,
        "total": total,
        "unclassified": unclassified,
        "excluded": excluded,
        "details": details,
        "sources": sources,
        "tests": tests,
        "examples": examples,
        "reference_config": reference,
    }


def assert_invariants(data):
    """Enforce AC-4 / AC-5 / AC-6 and the file-count anchor."""
    total = data["total"]
    by_cat = data["by_cat"]

    # AC-4: every included file satisfied the per-line identity inside
    # count_lines(); verify the aggregates too.
    for c in CATEGORIES:
        m = by_cat[c]
        assert m["total"] == m["blank"] + m["comment"] + m["code"], \
            "AC-4 failed for " + c
    assert total["total"] == total["blank"] + total["comment"] + total["code"], \
        "AC-4 failed for total"

    # AC-5: sum(T1..T6) == total on all five columns.
    summed = blank_metrics()
    for c in CATEGORIES:
        add_metrics(summed, by_cat[c])
    for key in METRIC_KEYS:
        assert summed[key] == total[key], \
            "AC-5 failed on %s: %d != %d" % (key, summed[key], total[key])

    # AC-6: business(T1+T2) + test(T6) + docs_config(T3+T4+T5) == total.
    groups = [("T1", "T2"), ("T6",), ("T3", "T4", "T5")]
    group_sum = blank_metrics()
    for group in groups:
        gm = blank_metrics()
        for c in group:
            add_metrics(gm, by_cat[c])
        add_metrics(group_sum, gm)
    for key in METRIC_KEYS:
        assert group_sum[key] == total[key], \
            "AC-6 failed on %s: %d != %d" % (key, group_sum[key], total[key])

    # Anchor: file distribution must match the read-only design pre-study.
    for c in CATEGORIES:
        assert by_cat[c]["files"] == ANCHOR[c], \
            "file-count anchor failed for %s: %d != %d" % (
                c, by_cat[c]["files"], ANCHOR[c])
    assert not data["unclassified"], \
        "unclassified files present: " + ", ".join(data["unclassified"])


def pct(part, whole):
    return 0.0 if whole == 0 else round(100.0 * part / whole, 1)


def magnitude(n):
    if n >= 10000:
        return "万行级"
    if n >= 1000:
        return "千行级"
    if n >= 100:
        return "百行级"
    return "十行级以内"


def metric_row(label, m):
    return "| %s | %d | %d | %d | %d | %d |" % (
        label, m["files"], m["total"], m["blank"], m["comment"], m["code"])


def render_markdown(data, meta):
    by_cat = data["by_cat"]
    total = data["total"]

    business = blank_metrics()
    for c in ("T1", "T2"):
        add_metrics(business, by_cat[c])
    test = dict(by_cat["T6"])
    docs_config = blank_metrics()
    for c in ("T3", "T4", "T5"):
        add_metrics(docs_config, by_cat[c])

    groups = [
        ("业务代码", "T1 + T2", business),
        ("测试代码", "T6", test),
        ("文档/配置（含脚本与工具链）", "T3 + T4 + T5", docs_config),
    ]

    test_over_biz_code = pct(test["code"], business["code"])
    test_over_biz_total = pct(test["total"], business["total"])

    lines = []
    w = lines.append
    w("# Starscream 仓库代码行数统计报告")
    w("")
    w("> 本报告由 `docs/tools/line_counter.py` 自动生成；统计输入固定为 master 分支快照归档，")
    w("> 与工作分支无关。请勿手工编辑表格数字——改动脚本后重跑本报告即可。")
    w("")
    w("## 1. 元信息（统计快照 / 日期 / 工具版本）")
    w("")
    w("| 项 | 值 |")
    w("| --- | --- |")
    w("| 目标仓库 | `Magic-zs/Starscream`（`https://github.com/Magic-zs/Starscream.git`） |")
    w("| 统计对象 | master 分支当前代码快照（非工作分支） |")
    w("| 快照 commit SHA | `%s` |" % meta["sha"])
    w("| 统计日期 | %s |" % meta["date"])
    w("| 统计工具 | 本仓库 `docs/tools/line_counter.py`（自包含，零第三方依赖） |")
    w("| 脚本 SHA-256 | `%s` |" % meta["script_sha256"])
    w("| Python 版本 | %s |" % meta["python"])
    w("| 快照导出方式 | `git archive <SHA> \\| tar -x -C <SNAP>` |")
    w("")
    w("## 2. 统计口径与方法")
    w("")
    w("### 2.1 复现命令（原文，可直接执行）")
    w("")
    w("```bash")
    w("cd Starscream")
    w("SHA=$(git rev-parse master)          # 预期 a2ed45c0b2f996cb8c335c4f270ecc68c3bd4c0f")
    w("SNAP=$(mktemp -d)")
    w('git archive "$SHA" | tar -x -C "$SNAP"    # 统计输入 = master 快照')
    w('python3 docs/tools/line_counter.py --root "$SNAP" --sha "$SHA" \\')
    w("        --date %s --exclude-default --format markdown > /tmp/starscream-loc.md" % meta["date"])
    w("diff -u docs/code-line-statistics.md /tmp/starscream-loc.md && echo REPRODUCIBLE")
    w('python3 docs/tools/line_counter.py --root "$SNAP" --date %s --format json \\' % meta["date"])
    w("  | python3 -m json.tool                    # 算术自检 + 文件级明细")
    w("```")
    w("")
    w("脚本 CLI：`--root`（必填，快照根目录）、`--sha`（写入元信息）、")
    w("`--exclude-default`（启用内置排除，默认开启）、`--format markdown|json`、")
    w("`--include-detail`（输出文件级明细）、`--date`（统计日期，默认当天）。")
    w("仅使用 Python 标准库 `os / re / sys / argparse / json / hashlib / datetime / platform`；")
    w("不依赖 `cloc` / `tokei` 或任何 pip 包。")
    w("")
    w("### 2.2 排除规则清单")
    w("")
    w("- 版本控制元数据：`.git/` 及其中所有内容。")
    w("- 依赖目录：`Pods/`、`Carthage/`、`checkouts/`、`node_modules/` 整体剪枝；")
    w("  特别地 `examples/WebSocketsOrgEcho/Pods/` 全部排除。")
    w("- Xcode 用户态与状态：`xcuserdata/`、`*.xcuserstate`、`*.xccheckout`、`IDEWorkspaceChecks.plist`。")
    w("- 资源与二进制：以 `.xcassets` 结尾的目录整体剪枝（`Images.xcassets` / `Assets.xcassets` 等，")
    w("  故 `Contents.json` 不计入）；`.storyboard`、`.xib`、图片、字体等非文本文件。")
    w("- 非文本：含 NUL 字节或无法以 UTF-8 解码的文件。")
    w("- 自计数防护：报告与脚本仅存在于工作分支，统计输入恒为 master 快照，天然不含二者。")
    w("")
    w("本次扫描实际排除项共 %d 条（目录剪枝 + 文件过滤），明细可用 `--include-detail --format json` 复核。" %
      len(data["excluded"]))
    w("")
    w("### 2.3 分类规则（主分类 T1–T6，互斥且完备，按优先级短路）")
    w("")
    w("1. 源码扩展名（`.swift/.h/.m/.c/.mm`）且路径含 `Tests/` 段或文件名匹配 `*Tests.*` / `*Test.*` → **T6**（仅对源码生效）。")
    w("2. `Package.swift` → **T4**（不得计入 T1）。")
    w("3. `.h/.m/.c/.mm` → **T2**。")
    w("4. `.swift` → **T1**（含 `examples/**` 非测试源码）。")
    w("5. `fastlane/Fastfile` 或 `.sh/.rb` → **T3**。")
    w("6. `.podspec/.xcscheme/.xcconfig/.plist/.yml/.yaml/.lock/.resolved/.modulemap/.pch/.xcworkspacedata`")
    w("   或 `Gemfile`/`Podfile`/`project.pbxproj`/点开头配置文件 → **T4**。")
    w("7. `.md/.txt/.markdown` 或无扩展名文本许可文件（`LICENSE`）→ **T5**。")
    w("8. 其余文本 → 未分类清单（本次必须为空，否则视为实现缺陷）。")
    w("")
    w("### 2.4 行级四层口径")
    w("")
    w("- 总行数：按 UTF-8 解码后归一化 `CRLF/CR` 为 `LF`，`split('\\n')` 并丢弃末尾空元素；")
    w("  末行无换行符时仍计 1 行（脚本已显式实现该规则，纳入文件中有 4 个此类文件：")
    w("  `LICENSE`、两个 `.gitignore`、`examples/SimpleTest/README.md`）。")
    w("- 空白行：整行仅含空白字符或完全为空。")
    w("- 注释行：非空白且无代码；`//`、`///`、`//!`、`// MARK:`、块注释内正文行（含 `*` 前缀）均算注释。")
    w("- 有效代码行：`总行 − 空白 − 注释`；行尾注释与 `code /* ... */` 同行均算有效代码行。")
    w("- Swift 嵌套块注释由 `block_depth` 状态机支持。")
    w("")
    w("## 3. 可复现脚本")
    w("")
    w("脚本原文随 MR 提交于 `docs/tools/line_counter.py`（SHA-256 见第 1 节），")
    w("无需另行粘贴；按 2.1 节命令即可复现本报告全部数字。")
    w("")
    w("## 4. 分类型统计表（T1–T6）")
    w("")
    w("| 分类 | 文件数 | 总行数 | 空白行 | 注释行 | 有效代码行 |")
    w("| --- | ---: | ---: | ---: | ---: | ---: |")
    for c in CATEGORIES:
        w(metric_row("%s %s" % (c, CATEGORY_NAMES[c]), by_cat[c]))
    w("| **小计（合计）** | **%d** | **%d** | **%d** | **%d** | **%d** |" % (
        total["files"], total["total"], total["blank"], total["comment"], total["code"]))
    w("")
    w("算术自检：每一行均满足 `总行数 = 空白行 + 注释行 + 有效代码行`；")
    w("T1–T6 各列之和等于小计行（脚本内断言强制）。")
    w("")
    w("## 5. 总量汇总")
    w("")
    w("| 维度 | 数值 |")
    w("| --- | ---: |")
    w("| 纳入文件数 | %d |" % total["files"])
    w("| 总行数 | %d |" % total["total"])
    w("| 空白行 | %d |" % total["blank"])
    w("| 注释行 | %d |" % total["comment"])
    w("| 有效代码行 | %d |" % total["code"])
    w("")
    w("## 6. 三类汇总与占比")
    w("")
    w("| 汇总类 | 由哪些主分类构成 | 总行数 | 总行占比 | 有效代码行 | 有效代码行占比 |")
    w("| --- | --- | ---: | ---: | ---: | ---: |")
    for name, composition, m in groups:
        w("| %s | %s | %d | %.1f%% | %d | %.1f%% |" % (
            name, composition, m["total"], pct(m["total"], total["total"]),
            m["code"], pct(m["code"], total["code"])))
    w("| **合计** | T1–T6 | **%d** | **100.0%%** | **%d** | **100.0%%** |" % (
        total["total"], total["code"]))
    w("")
    w("**测试/业务代码占比（有效代码行口径为主）：**")
    w("测试代码有效代码行 %d，业务代码有效代码行 %d，" % (test["code"], business["code"]))
    w("测试 / 业务 = **%.1f%%**；以总行数计为 %.1f%%（%d / %d），两者并列供参照。" % (
        test_over_biz_code, test_over_biz_total, test["total"], business["total"]))
    w("")
    w("**三类总体量级（供改动成本评估）：**")
    w("")
    w("- 业务代码（T1+T2）：总行 %d（%s），有效代码行 %d（%s）。" % (
        business["total"], magnitude(business["total"]),
        business["code"], magnitude(business["code"])))
    w("- 测试代码（T6）：总行 %d（%s），有效代码行 %d（%s）。" % (
        test["total"], magnitude(test["total"]),
        test["code"], magnitude(test["code"])))
    w("- 文档/配置（T3+T4+T5，含脚本与工具链）：总行 %d（%s），有效代码行 %d（%s）。" % (
        docs_config["total"], magnitude(docs_config["total"]),
        docs_config["code"], magnitude(docs_config["code"])))
    w("")
    w("> 约定：脚本与构建配置归入「文档/配置」而非业务代码，因其改动成本更接近工具链/产品配置，")
    w("> 与产品逻辑不同。此三类之和严格等于总量（脚本断言保证）。")
    w("")
    w("## 7. 可选补充")
    w("")
    w("### 7.1 剔除大体积配置后的参考值")
    w("")
    w("锁文件（`Gemfile.lock` / `Package.resolved` / `Podfile.lock` / `Manifest.lock`）与")
    w("`*.pbxproj` 体量大、信息密度低。剔除这些文件后，T4 参考值：")
    w("")
    w("| 范围 | 文件数 | 总行数 | 空白行 | 注释行 | 有效代码行 |")
    w("| --- | ---: | ---: | ---: | ---: | ---: |")
    w(metric_row("T4 全额", by_cat["T4"]))
    w(metric_row("T4 剔除大体积配置后", data["reference_config"]))
    w("")
    w("### 7.2 Sources / Tests / examples 子分布")
    w("")
    w("| 子分布 | 文件数 | 总行数 | 空白行 | 注释行 | 有效代码行 |")
    w("| --- | ---: | ---: | ---: | ---: | ---: |")
    w(metric_row("Sources/", data["sources"]))
    w(metric_row("Tests/", data["tests"]))
    w(metric_row("examples/", data["examples"]))
    w("")
    w("> 子分布按**路径**划分，与 T1–T6 主分类是不同维度，可能重叠：例如 `Tests/Info.plist`")
    w("> 路径在 `Tests/` 下但归 T4 配置；`examples/AutobahnTest/AutobahnTests/AutobahnTests.swift`")
    w("> 路径在 `examples/` 下但归 T6 测试。此表仅用于定位模块，不参与三类对账。")
    w("> `examples/` 下的非测试 Swift 默认计入 T1 业务代码（需求定型第 6 节待确认项，")
    w("> 已有默认规则，不阻塞）；上表单列便于按需剔除后重估业务代码占比。")
    w("")
    w("## 8. 已知限制")
    w("")
    w("- 注释识别基于原始字符扫描，不做完整 Swift 词法分析：字符串字面量中的 `//` 或 `/* */`")
    w("  理论上可能误判。本仓库实测仅有 4 处 URL 字符串含 `//` 且均有前置代码，无字符串内 `/* */`、")
    w("  无多行字符串，实际影响为零；换仓库复用脚本时须重新评估。")
    w("- Swift 嵌套块注释已由 `block_depth` 支持；Objective-C 预处理条件编译按普通代码行计。")
    w("- `cloc` / `tokei` 不可用，无法与第三方工具交叉校验；本报告脚本为唯一权威口径，")
    w("  以「命令可复现 + 算术自洽」保证可信度。")
    w("- `examples/` 归属为默认规则（计入 T1 + 单独子分布），属可评审推翻的约定。")
    w("")
    return "\n".join(lines) + "\n"


def render_json(data, meta):
    by_cat = data["by_cat"]
    total = data["total"]
    business = blank_metrics()
    for c in ("T1", "T2"):
        add_metrics(business, by_cat[c])
    test = dict(by_cat["T6"])
    docs_config = blank_metrics()
    for c in ("T3", "T4", "T5"):
        add_metrics(docs_config, by_cat[c])
    payload = {
        "meta": meta,
        "categories": by_cat,
        "total": total,
        "summary": {
            "business": business,
            "test": test,
            "docs_config": docs_config,
        },
        "test_over_business_code_pct": pct(test["code"], business["code"]),
        "test_over_business_total_pct": pct(test["total"], business["total"]),
        "sub_distribution": {
            "Sources": data["sources"],
            "Tests": data["tests"],
            "examples": data["examples"],
        },
        "reference_config_without_bulky": data["reference_config"],
        "unclassified": data["unclassified"],
        "excluded": data["excluded"],
    }
    if data["details"]:
        payload["details"] = data["details"]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="snapshot root directory")
    parser.add_argument("--sha", default="(unspecified)", help="master commit SHA")
    parser.add_argument("--date", default=datetime.date.today().isoformat(),
                        help="statistics date YYYY-MM-DD")
    parser.add_argument("--exclude-default", action="store_true", default=True,
                        help="apply built-in exclusions (default: on)")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--include-detail", action="store_true",
                        help="include per-file detail records")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        parser.error("--root is not a directory: " + root)

    # Self-counting guard: warn loudly if the deliverables are inside root.
    for guard in ("docs/tools/line_counter.py", "docs/code-line-statistics.md"):
        if os.path.isfile(os.path.join(root, guard)):
            sys.stderr.write(
                "WARNING: %s found under --root; statistics input should be a "
                "master snapshot without working-branch files.\n" % guard)

    data = scan(root, exclude_default=args.exclude_default,
                include_detail=args.include_detail)
    assert_invariants(data)

    script_path = os.path.abspath(__file__)
    with open(script_path, "rb") as fh:
        script_sha256 = hashlib.sha256(fh.read()).hexdigest()
    meta = {
        "sha": args.sha,
        "date": args.date,
        "python": platform.python_version(),
        "root": root,
        "script_sha256": script_sha256,
        "excluded_count": len(data["excluded"]),
    }

    if args.format == "json":
        sys.stdout.write(render_json(data, meta))
    else:
        sys.stdout.write(render_markdown(data, meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
