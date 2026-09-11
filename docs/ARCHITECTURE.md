# 架构与解析设计

## 1. 设计目标

项目的首要约束是“台词和 MP3 严格一一对应”。解析器遇到无法证明的结构关系时必须失败并记录，不能用全页顺序、数量相等或 `zip(texts, mp3s)` 猜测。

项目是本地 CLI，不包含数据库服务器、Web 后台、Redis、Celery 或浏览器自动化。

## 2. 数据流

```text
MediaWiki Category API
        │
        ▼
  ShipReference 列表
        │
        ▼
 BWiki 静态 HTML ──► ShipParser ──► VoiceParser
                                      │
                                      ▼
                         Ship / VoiceSet / VoiceLine
                                      │
                                      ▼
                            DownloadManager
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
                    MP3 + TXT   metadata.json   state/failed
```

HTML parser 只产生 Python 数据对象，不负责创建目录或写文件。下载管理器不再分析 DOM，只消费解析后的模型。

## 3. 模块职责

| 文件 | 职责 |
| --- | --- |
| `main.py` | 交互菜单、输入校验、业务调度、批量分组、Ctrl+C 顶层处理 |
| `bwiki/client.py` | 异步 HTTP、页面并发限制、超时、重试和 JSON 响应 |
| `bwiki/ship_index.py` | 分页读取 `Category:舰娘`、精确查找、模糊候选 |
| `bwiki/ship_parser.py` | 锚定舰船台词 section，识别本体面板和皮肤 Tab/Pane |
| `bwiki/voice_parser.py` | 在单个语音块内提取 category、中文台词和 MP3 |
| `bwiki/selectors.py` | 集中保存真实页面 selector |
| `bwiki/models.py` | 不依赖存储层的 dataclass 数据模型 |
| `downloader/audio.py` | MP3 校验、并发下载、重试、`.part` 和 Range |
| `downloader/resume.py` | `Content-Range` 与 `.part.meta.json` |
| `downloader/manager.py` | 路径分配、TXT、metadata、单舰并发任务和失败汇总 |
| `storage/paths.py` | 输出根目录、安全相对路径和路径逃逸防护 |
| `storage/metadata.py` | UTF-8 文本/JSON 原子写入与容错读取 |
| `storage/state.py` | 全量任务状态和失败记录 |
| `utils/filename.py` | 跨平台文件名清理、截断哈希、重复名称 |
| `utils/retry.py` | 统一退避和 `Retry-After` 解析 |
| `utils/logger.py` | CLI 报告与滚动日志 |
| `inspect_bwiki_dom.py` | 独立 Phase 1 调查脚本，不参与正式下载流程 |

## 4. 数据模型

```text
Ship
├── name                 MediaWiki 规范页名
├── display_name         当前页面展示名/和谐名
├── page_url
└── voice_sets
    ├── VoiceSet(name="本体", kind="base")
    └── VoiceSet(name=<真实皮肤名>, kind="skin")
        └── VoiceLine
            ├── category
            ├── text
            ├── audio_url | None
            ├── data_key
            ├── data_key_index
            └── ordinal
```

模型不包含 HTTP Client、文件句柄或 BeautifulSoup 节点，因此解析结果可以独立测试并交给不同存储实现。

## 5. 真实 DOM 合同

### 5.1 Section 边界

标题使用限定 selector：

```css
h2 > span.mw-headline#舰船台词
```

BWiki 页面存在重复 `id="舰船台词"`，所以不能使用裸 `#舰船台词`。解析范围只包括该 h2 与下一个 h2 之间的兄弟节点。

全页面的 `.table-ShipWordsTable` 不全是语音表；欧根亲王页面还有一张情人节礼物表。section 边界防止误收。

### 5.2 本体

本体位于 section 内唯一“不含直接 `ul.nav-tabs`”的 `div.panel.panel-shiptable`。它不是皮肤 Tab 的一部分，固定转换为：

```python
VoiceSet(name="本体", kind="base", voices=...)
```

### 5.3 皮肤

皮肤面板直接包含：

```css
ul.nav.nav-tabs
div.panel-body.tab-content
```

标题节点的 `data-target="#TbPn-..."` 必须精确命中同一面板内 `div.tab-pane#TbPn-...`。哈希式 id 逐页动态读取，禁止硬编码。

解析器校验：

- Tab 数量等于含语音表的 Pane 数量。
- 每个 `data-target` 非空且不重复。
- 每个目标 Pane 存在。
- 每个 Pane 恰好包含一张语音表。
- 同一舰娘的语音集名称不重复，避免 metadata 静默覆盖。

### 5.4 单条语音

表格一行的直接 `th` 是 category。一个 category 可以包含多个兄弟语音块：

```html
<div class="ship_word_block" data-key="main" data-key-i="1">
  <p class="ship_word_line" data-lang="zh">台词 A</p>
  <div class="sm-audio-src"><a href="...A.mp3">...</a></div>
</div>
```

解析器对每个 `.ship_word_block` 独立执行：

1. 从所在行的直接 `th` 读取 category。
2. 从同一块的 `.ship_word_line[data-lang="zh"]` 读取台词。
3. 从同一块的 `.sm-audio-src a[href]` 读取最多一个音频 URL。
4. 没有链接时产生 `audio_url=None`。
5. 一个块出现多个链接时抛出结构错误，不猜测。

台词提取遍历原始文本节点：内联 `<span>/<a>` 之间不会人为插入空格，真实 `<br>` 转换为换行。最外层模板排版空白会去除；保存的是页面渲染台词，不是 MediaWiki wikitext 模板源码。

## 6. 舰娘索引

索引使用：

```text
api.php?action=query
       &list=categorymembers
       &cmtitle=Category:舰娘
       &cmnamespace=0
       &cmlimit=max
```

接口单页有数量上限，`ship_index.py` 会持续使用 `cmcontinue` 直到没有 continuation。每项转换为规范标题、pageid 和 URL 编码后的页面地址。

精确匹配先做 NFC Unicode 规范化、去除输入首尾空白和 `casefold`。模糊建议优先“以查询词开头”的名称，再考虑包含关系和字符串相似度；候选只供用户选择，不会自动执行。

## 7. 并发模型

```text
全部舰娘
└── 每批 4 个舰娘任务
    ├── 页面请求共享 Semaphore(4)
    └── 所有 MP3 共享 Semaphore(8)
```

程序不会一次创建全部舰娘的页面任务。每批舰娘完成后再进入下一批；单舰内的所有音频可以并发，但仍受全局音频信号量限制。

页面和音频分别使用 AsyncClient。音频流的磁盘打开、写入、flush、fsync、关闭，以及单个 MP3 的完整性检查通过 `asyncio.to_thread` 执行，避免大文件操作阻塞事件循环。

## 8. 重试策略

可重试条件：

- HTTP 429、500、502、503、504。
- httpx 网络、连接、读取、协议和超时错误。
- 流结束后长度不完整。
- Range 响应不符合预期。
- 下载内容没有通过 MP3 文件头检查。

默认最多尝试 4 次。前三次失败后的基础等待为 1、2、4 秒；存在 `Retry-After` 时取更保守的等待值，单次最多按 60 秒处理。

404 等永久 HTTP 错误不会反复重试，直接进入失败记录。

## 9. 文件名与路径分配

文件名处理顺序：

1. Unicode NFC 规范化。
2. ASCII 非法字符替换为全角字符。
3. 控制字符替换为全角下划线。
4. 去除末尾空格和点。
5. Windows 保留名添加前导下划线。
6. 超过 100 字符时截断并添加 `_` 加 8 位 SHA-256。
7. 同目录重复名称添加 `_2`、`_3`，比较时使用 `casefold`。

舰娘和皮肤目录组件最长 80 字符。metadata 中的相对路径再次解析时必须仍位于对应舰娘目录，防止损坏 JSON 造成路径逃逸。

## 10. 下载与 Range 恢复

最终文件不会直接写入。下载目标是：

```text
name.mp3.part
name.mp3.part.meta.json
```

恢复时读取 `.part` 大小和 sidecar：

- 请求 `Range: bytes=<size>-`。
- 优先使用 ETag，其次 Last-Modified 作为 `If-Range`。
- 206 必须包含正确的 `Content-Range` 起点和总长度。
- 200 以写模式重新开始，不能追加旧 `.part`。
- 416 只在本地已经完整且 MP3 合法时完成，否则清空后重试。

流数据按底层 transport chunk 写入，因此 Ctrl+C 时尽量保留已经收到的数据。下载结束后依次校验长度和 MP3 头，再原子替换最终文件。

## 11. 状态与一致性

恢复的真实依据优先级：

```text
实际 MP3/TXT
        +
每舰娘 metadata.json
        +
state/state.json（辅助进度）
```

`state.json` 不是唯一真相。它缺失或 JSON 损坏时，程序仍会重新解析页面并检查文件系统。

同一舰娘每完成一个音频任务就更新 metadata。并发任务对同一个 metadata 文件使用异步锁；所有 JSON 和 TXT 先写同目录 `.tmp`、flush、fsync，再 replace。

整舰被视为完成必须满足：

- `metadata.complete == true`。
- 至少存在一个语音集和一条记录。
- 每条有 `source_url` 的记录都有安全的 `.mp3`/`.txt` 相对路径。
- MP3 通过文件头检查。
- TXT 内容与 metadata 的完整 `text` 一致。

## 12. 严格失败原则

以下情况不会自动降级为顺序猜测：

- 找不到舰船台词标题。
- 本体面板不唯一。
- 皮肤面板超过一个。
- Tab/Pane 数量不一致。
- `data-target` 缺失、重复或找不到 Pane。
- 一个语音容器内表格数量不为一。
- 行缺少 category。
- 语音块缺少台词。
- 单个语音块包含多个音频链接。

页面级失败由全量调度器记录在 `failed.json` 后继续下一个舰娘。这一策略优先保护台词和声音的对应正确性。

## 13. 测试策略

真实 fixture：

- `prinz_eugen.html`：本体、多皮肤、誓约无皮肤描述、多彩蛋、无音频；解析为 9 个语音集、118 条台词、114 条音频。
- `javelin.html`：大量皮肤、扩展语音、皮肤内无音频；解析为 11 个语音集、142 条台词、130 条音频。
- `admiral_zenker.html`：新角色、少皮肤、规范名/展示名不同；解析为 2 个语音集、52 条台词、50 条音频。

MockTransport 测试覆盖页面重试、404、正确 Range、服务器忽略 Range 和取消保留 `.part`。临时目录测试覆盖文件名、重复台词、metadata、TXT 和损坏状态恢复。

2026-09-11 的发布验收基线：26 项自动化测试全部通过；真实下载欧根亲王得到 114 个 MP3 和 114 个 TXT，总计 26,501,675 字节，重复运行全部安全跳过，失败记录和断点残留均为 0。MediaWiki 分类 API 当日分页返回 691 个不重复的规范页名；全量音频下载因流量和磁盘规模未在发布验收中自动执行。
