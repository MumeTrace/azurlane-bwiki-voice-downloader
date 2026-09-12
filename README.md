# azurlane-bwiki-voice-downloader

碧蓝航线 BWiki 舰船语音批量下载与结构化归档工具。

程序从 BWiki 的真实静态 HTML 中解析舰娘本体和全部皮肤，以单个 `.ship_word_block` 为最小边界严格绑定中文台词与 MP3。它不会把全页文字和链接分别收集后 `zip`，也不需要 Selenium 或 Playwright。

数据来源：<https://wiki.biligame.com/blhx/>

## 当前状态

- 当前版本：`v3.0.0`。第三版兼容初月等页面中的空可选模板行，并防止含特殊符号的皮肤名导致 Windows 控制台退出；同时保留第二版的展示名查找与 BWiki `567` 自动重试。
- 交互式指定舰娘和全部舰娘模式均已实现。
- 全量舰娘名单来自 MediaWiki `Category:舰娘` API，运行时动态分页获取。
- 页面并发默认为 4，音频并发默认为 8。
- 支持重试、SKIP、TXT 补写、`.part` 文件续传、任务恢复和 Ctrl+C 安全中断。
- 2026-09-11 已真实下载并校验欧根亲王：114 个 MP3、114 个 TXT、0 个失败。
- 自动化测试：26 项通过。

## 快速开始

需要 Python 3.11 或更高版本。推荐使用 Conda：

```powershell
cd E:\python\pachong\azurlane-bwiki-voice-downloader
conda create -n azurlane-voices python=3.11 -y
conda activate azurlane-voices
python -m pip install -e .
python main.py
```

本机已经验证的直接启动方式：

```powershell
cd E:\python\pachong\azurlane-bwiki-voice-downloader
D:\anaconda3\python.exe main.py
```

启动后统一显示：

```text
========================================
     碧蓝航线 BWiki 语音下载工具
========================================

[1] 下载指定舰娘
[2] 下载全部舰娘
[0] 退出
```

详细操作、恢复方法和常见问题见 [用户使用手册](docs/USAGE.md)。

## 下载结果

```text
voices/
└── 欧根亲王/
    ├── metadata.json
    ├── 本体/
    │   ├── 这点程度就满足了吗？.mp3
    │   └── 这点程度就满足了吗？.txt
    ├── 永不褪色的笑容/
    └── 【誓约】命运交响曲/
```

MP3 和 TXT 的主体名称优先使用台词原文。category 仅保存在 metadata 中，不会替代正常文件名。没有 MP3 的台词会进入 metadata，但不会创建假 MP3 或 TXT。

所有输出目录都固定在项目根目录下，与启动命令当前所在目录无关：

- `voices/`：MP3、TXT 和每名舰娘的 metadata。
- `state/state.json`：批量任务进度索引。
- `state/failed.json`：当前仍未解决的失败项目。
- `logs/app.log`：详细日志，默认滚动保存。

## 文档导航

- [用户使用手册](docs/USAGE.md)：安装、菜单、下载、恢复、日志和故障处理。
- [架构与解析设计](docs/ARCHITECTURE.md)：模块职责、真实 DOM 合同、并发和恢复数据流。
- [Metadata 与状态格式](docs/METADATA_SCHEMA.md)：所有 JSON 字段、状态值和路径规则。

## 测试

```powershell
D:\anaconda3\python.exe -m pytest -q
```

测试完全使用本地 fixture，不会在每次测试时访问 BWiki。当前真实样本包括欧根亲王、标枪、曾克海军上将和初月，覆盖多皮肤、少皮肤、无音频条目、彩蛋嵌套标签、展示别名、空可选模板行和没有“皮肤描述”的誓约皮肤。

需要重新调查在线 DOM 时，可以运行：

```powershell
D:\anaconda3\python.exe inspect_bwiki_dom.py --save-fixture tests\fixtures\latest_page.html
```

更新 fixture 前应先保留旧文件并确认结构变化；不要为了让测试通过而放宽严格配对规则。

## 网络与使用边界

本工具只面向公开 Wiki 页面和公开语音资源的本地归档，不包含登录绕过、验证码绕过、代理池或限流规避。全站下载会消耗较多时间、带宽和磁盘空间；请使用默认保守并发，并遵守站点规则及资源权利人的要求。
