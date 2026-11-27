# Starscream 技术栈分析

> 平台工作项：issue-1795781505161468105
> 分析基线：`master` @ `a2ed45c0b2f996cb8c335c4f270ecc68c3bd4c0f`
> 仓库：`Magic-zs/Starscream`（fork 自 `daltoniam/Starscream`）
> 本文档记录基于仓库内清单、锁文件、源码与配置的静态盘点结果，不改动任何业务逻辑。

## 1. 项目定位

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 类型 | 符合 RFC 6455 的 Swift **WebSocket 客户端库**，不是后端服务、数据库或服务端 API | `Starscream.podspec:4`、`README.md:3` |
| 版本 | `3.1.0` | `Starscream.podspec:3` |
| 许可 | Apache License 2.0 | `Starscream.podspec:6`、`LICENSE` |

## 2. 语言与平台

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 主语言 | Swift 5.0 | `Starscream.podspec:15`、`Starscream.xcodeproj/project.pbxproj`（`SWIFT_VERSION = 5.0`） |
| SwiftPM tools 版本 | `swift-tools-version:4.2` | `Package.swift:1` |
| 部署目标 | iOS 8.0 / macOS 10.10 / tvOS 9.0 / watchOS 2.0 | `Starscream.podspec:10-13`、`project.pbxproj` |
| Xcode 版本 | `LastUpgradeCheck = 1020`（Xcode 10.2） | `project.pbxproj` |

系统框架与库依赖：`Foundation`、`CoreFoundation`、`Security`、`CommonCrypto`、`zlib`；Xcode 工程链接 `usr/lib/libz.tbd`。证据见 `Sources/Starscream/*.swift` 的 import 段与 `project.pbxproj`。

## 3. 依赖管理

- **SwiftPM**：唯一外部依赖 `apple/swift-nio-zlib-support` `1.0.0`，revision `37760e9a52030bb9011972c5213c3350fa9d41fd`（`Package.swift:31`、`Package.resolved:5-11`）。
- **CocoaPods**：`Starscream.podspec` 定义 pod；Ruby 工具链由 `Gemfile` / `Gemfile.lock` 固定。
- **Ruby 依赖**：cocoapods `1.6.1`、fastlane `2.122.0`、xcpretty `0.3.0`、bundler `1.17.2`、xcodeproj `1.9.0`（`Gemfile.lock`）。
- **多分发渠道**：CocoaPods、Carthage、SwiftPM、Accio、Rogue、git submodule / 手动集成（`README.md:279-363` 及各包清单）。

## 4. 构建、CI 与发布

| 环节 | 实现 | 证据 |
| --- | --- | --- |
| 本地构建链 | `xcodebuild + xcpretty` → `swift build` → `pod repo update` → `pod lib lint` | `build.sh:3-6` |
| CI | Travis CI，macOS 镜像 `xcode10.2`，入口 `./build.sh` | `.travis.yml:1-7` |
| 发布 | fastlane `release` lane：GitHub Release + `pod_push`，使用 `GITHUB_TOKEN` | `release.sh:3-4`、`fastlane/Fastfile:7-27` |

## 5. 测试与已知限制

- 测试框架为 **XCTest**；`Tests/CompressionTests.swift` 有压缩往返用例，`Tests/StarscreamTests/StarscreamTests.swift` 为模板用例。
- 核心 WebSocket 行为与 Autobahn 协议一致性缺少本地服务端驱动的自动化回归（`README.md:415-422` 仍为 TODO）。
- 当前分析环境为 Linux，缺少 Swift / xcodebuild / CocoaPods / Ruby 工具链，`./build.sh`、`swift build`、`pod lib lint` 与 XCTest 实际运行**未验证**；README KNOWN ISSUES 亦声明 Linux 缺少 Security framework，`SSL Pinning` / `SSLCiphers` 无法在 Linux 验证。
- README 中历史版本要求（iOS 7 / macOS 10.9）与清单文件（iOS 8 / macOS 10.10）不一致；示例 `Podfile.lock` 锁定 `3.0.6`，存在版本漂移。
- fork 远端 `Magic-zs/Starscream` 与 podspec / fastlane 中的 `daltoniam/Starscream` URL 不一致。

## 6. 结论

Starscream 是一个以 Swift 5.0 编写、面向 Apple 全平台（并尝试 Linux）的 RFC 6455 WebSocket 客户端库；依赖极简（SwiftPM 仅一个 zlib 支持包），构建与发布围绕 Xcode / CocoaPods / fastlane / Travis 展开。以上结论均来自静态证据盘点，构建与运行类验证需在 macOS + Xcode 10.2 环境补跑。
