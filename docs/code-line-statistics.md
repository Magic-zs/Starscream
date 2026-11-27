# Starscream 仓库代码行数统计报告

> 本报告由 `docs/tools/line_counter.py` 自动生成；统计输入固定为 master 分支快照归档，
> 与工作分支无关。请勿手工编辑表格数字——改动脚本后重跑本报告即可。

## 1. 元信息（统计快照 / 日期 / 工具版本）

| 项 | 值 |
| --- | --- |
| 目标仓库 | `Magic-zs/Starscream`（`https://github.com/Magic-zs/Starscream.git`） |
| 统计对象 | master 分支当前代码快照（非工作分支） |
| 快照 commit SHA | `a2ed45c0b2f996cb8c335c4f270ecc68c3bd4c0f` |
| 统计日期 | 2026-11-27 |
| 统计工具 | 本仓库 `docs/tools/line_counter.py`（自包含，零第三方依赖） |
| 脚本 SHA-256 | `fc14ab8b4547ec8712eeb75cc2033ec8a69b8f4e05e2462cd460b64b419a037f` |
| Python 版本 | 3.11.6 |
| 快照导出方式 | `git archive <SHA> \| tar -x -C <SNAP>` |

## 2. 统计口径与方法

### 2.1 复现命令（原文，可直接执行）

```bash
cd Starscream
SHA=$(git rev-parse master)          # 预期 a2ed45c0b2f996cb8c335c4f270ecc68c3bd4c0f
SNAP=$(mktemp -d)
git archive "$SHA" | tar -x -C "$SNAP"    # 统计输入 = master 快照
python3 docs/tools/line_counter.py --root "$SNAP" --sha "$SHA" \
        --date 2026-11-27 --exclude-default --format markdown > /tmp/starscream-loc.md
diff -u docs/code-line-statistics.md /tmp/starscream-loc.md && echo REPRODUCIBLE
python3 docs/tools/line_counter.py --root "$SNAP" --date 2026-11-27 --format json \
  | python3 -m json.tool                    # 算术自检 + 文件级明细
```

脚本 CLI：`--root`（必填，快照根目录）、`--sha`（写入元信息）、
`--exclude-default`（启用内置排除，默认开启）、`--format markdown|json`、
`--include-detail`（输出文件级明细）、`--date`（统计日期，默认当天）。
仅使用 Python 标准库 `os / re / sys / argparse / json / hashlib / datetime / platform`；
不依赖 `cloc` / `tokei` 或任何 pip 包。

### 2.2 排除规则清单

- 版本控制元数据：`.git/` 及其中所有内容。
- 依赖目录：`Pods/`、`Carthage/`、`checkouts/`、`node_modules/` 整体剪枝；
  特别地 `examples/WebSocketsOrgEcho/Pods/` 全部排除。
- Xcode 用户态与状态：`xcuserdata/`、`*.xcuserstate`、`*.xccheckout`、`IDEWorkspaceChecks.plist`。
- 资源与二进制：以 `.xcassets` 结尾的目录整体剪枝（`Images.xcassets` / `Assets.xcassets` 等，
  故 `Contents.json` 不计入）；`.storyboard`、`.xib`、图片、字体等非文本文件。
- 非文本：含 NUL 字节或无法以 UTF-8 解码的文件。
- 自计数防护：报告与脚本仅存在于工作分支，统计输入恒为 master 快照，天然不含二者。

本次扫描实际排除项共 13 条（目录剪枝 + 文件过滤），明细可用 `--include-detail --format json` 复核。

### 2.3 分类规则（主分类 T1–T6，互斥且完备，按优先级短路）

1. 源码扩展名（`.swift/.h/.m/.c/.mm`）且路径含 `Tests/` 段或文件名匹配 `*Tests.*` / `*Test.*` → **T6**（仅对源码生效）。
2. `Package.swift` → **T4**（不得计入 T1）。
3. `.h/.m/.c/.mm` → **T2**。
4. `.swift` → **T1**（含 `examples/**` 非测试源码）。
5. `fastlane/Fastfile` 或 `.sh/.rb` → **T3**。
6. `.podspec/.xcscheme/.xcconfig/.plist/.yml/.yaml/.lock/.resolved/.modulemap/.pch/.xcworkspacedata`
   或 `Gemfile`/`Podfile`/`project.pbxproj`/点开头配置文件 → **T4**。
7. `.md/.txt/.markdown` 或无扩展名文本许可文件（`LICENSE`）→ **T5**。
8. 其余文本 → 未分类清单（本次必须为空，否则视为实现缺陷）。

### 2.4 行级四层口径

- 总行数：按 UTF-8 解码后归一化 `CRLF/CR` 为 `LF`，`split('\n')` 并丢弃末尾空元素；
  末行无换行符时仍计 1 行（脚本已显式实现该规则，纳入文件中有 4 个此类文件：
  `LICENSE`、两个 `.gitignore`、`examples/SimpleTest/README.md`）。
- 空白行：整行仅含空白字符或完全为空。
- 注释行：非空白且无代码；`//`、`///`、`//!`、`// MARK:`、块注释内正文行（含 `*` 前缀）均算注释。
- 有效代码行：`总行 − 空白 − 注释`；行尾注释与 `code /* ... */` 同行均算有效代码行。
- Swift 嵌套块注释由 `block_depth` 状态机支持。

## 3. 可复现脚本

脚本原文随 MR 提交于 `docs/tools/line_counter.py`（SHA-256 见第 1 节），
无需另行粘贴；按 2.1 节命令即可复现本报告全部数字。

## 4. 分类型统计表（T1–T6）

| 分类 | 文件数 | 总行数 | 空白行 | 注释行 | 有效代码行 |
| --- | ---: | ---: | ---: | ---: | ---: |
| T1 Swift 业务源码 | 11 | 2298 | 285 | 357 | 1656 |
| T2 C / ObjC 源码与头文件 | 1 | 19 | 6 | 10 | 3 |
| T3 脚本 | 4 | 63 | 11 | 0 | 52 |
| T4 构建与工程配置 | 24 | 2324 | 77 | 175 | 2072 |
| T5 文档 | 5 | 890 | 243 | 11 | 636 |
| T6 测试代码 | 3 | 138 | 27 | 48 | 63 |
| **小计（合计）** | **48** | **5732** | **649** | **601** | **4482** |

算术自检：每一行均满足 `总行数 = 空白行 + 注释行 + 有效代码行`；
T1–T6 各列之和等于小计行（脚本内断言强制）。

## 5. 总量汇总

| 维度 | 数值 |
| --- | ---: |
| 纳入文件数 | 48 |
| 总行数 | 5732 |
| 空白行 | 649 |
| 注释行 | 601 |
| 有效代码行 | 4482 |

## 6. 三类汇总与占比

| 汇总类 | 由哪些主分类构成 | 总行数 | 总行占比 | 有效代码行 | 有效代码行占比 |
| --- | --- | ---: | ---: | ---: | ---: |
| 业务代码 | T1 + T2 | 2317 | 40.4% | 1659 | 37.0% |
| 测试代码 | T6 | 138 | 2.4% | 63 | 1.4% |
| 文档/配置（含脚本与工具链） | T3 + T4 + T5 | 3277 | 57.2% | 2760 | 61.6% |
| **合计** | T1–T6 | **5732** | **100.0%** | **4482** | **100.0%** |

**测试/业务代码占比（有效代码行口径为主）：**
测试代码有效代码行 63，业务代码有效代码行 1659，
测试 / 业务 = **3.8%**；以总行数计为 6.0%（138 / 2317），两者并列供参照。

**三类总体量级（供改动成本评估）：**

- 业务代码（T1+T2）：总行 2317（千行级），有效代码行 1659（千行级）。
- 测试代码（T6）：总行 138（百行级），有效代码行 63（十行级以内）。
- 文档/配置（T3+T4+T5，含脚本与工具链）：总行 3277（千行级），有效代码行 2760（千行级）。

> 约定：脚本与构建配置归入「文档/配置」而非业务代码，因其改动成本更接近工具链/产品配置，
> 与产品逻辑不同。此三类之和严格等于总量（脚本断言保证）。

## 7. 可选补充

### 7.1 剔除大体积配置后的参考值

锁文件（`Gemfile.lock` / `Package.resolved` / `Podfile.lock` / `Manifest.lock`）与
`*.pbxproj` 体量大、信息密度低。剔除这些文件后，T4 参考值：

| 范围 | 文件数 | 总行数 | 空白行 | 注释行 | 有效代码行 |
| --- | ---: | ---: | ---: | ---: | ---: |
| T4 全额 | 24 | 2324 | 77 | 175 | 2072 |
| T4 剔除大体积配置后 | 18 | 585 | 29 | 92 | 464 |

### 7.2 Sources / Tests / examples 子分布

| 子分布 | 文件数 | 总行数 | 空白行 | 注释行 | 有效代码行 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sources/ | 6 | 1936 | 214 | 281 | 1441 |
| Tests/ | 4 | 162 | 27 | 48 | 87 |
| examples/ | 23 | 1768 | 135 | 158 | 1475 |

> 子分布按**路径**划分，与 T1–T6 主分类是不同维度，可能重叠：例如 `Tests/Info.plist`
> 路径在 `Tests/` 下但归 T4 配置；`examples/AutobahnTest/AutobahnTests/AutobahnTests.swift`
> 路径在 `examples/` 下但归 T6 测试。此表仅用于定位模块，不参与三类对账。
> `examples/` 下的非测试 Swift 默认计入 T1 业务代码（需求定型第 6 节待确认项，
> 已有默认规则，不阻塞）；上表单列便于按需剔除后重估业务代码占比。

## 8. 已知限制

- 注释识别基于原始字符扫描，不做完整 Swift 词法分析：字符串字面量中的 `//` 或 `/* */`
  理论上可能误判。本仓库实测仅有 4 处 URL 字符串含 `//` 且均有前置代码，无字符串内 `/* */`、
  无多行字符串，实际影响为零；换仓库复用脚本时须重新评估。
- Swift 嵌套块注释已由 `block_depth` 支持；Objective-C 预处理条件编译按普通代码行计。
- `cloc` / `tokei` 不可用，无法与第三方工具交叉校验；本报告脚本为唯一权威口径，
  以「命令可复现 + 算术自洽」保证可信度。
- `examples/` 归属为默认规则（计入 T1 + 单独子分布），属可评审推翻的约定。

