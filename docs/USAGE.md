# 用户使用手册

本文面向直接运行下载工具的用户。内部解析原理见 `ARCHITECTURE.md`，JSON 字段见 `METADATA_SCHEMA.md`。

## 1. 环境准备

最低要求：

- Python 3.11 或更高版本。
- 能访问 `wiki.biligame.com` 和 `patchwiki.biligame.com`。
- Windows 或 Linux 文件系统。

推荐使用独立 Conda 环境：

```powershell
cd E:\python\pachong\azurlane-bwiki-voice-downloader
conda create -n azurlane-voices python=3.11 -y
conda activate azurlane-voices
python -m pip install -e .
```

如果暂时使用本机已有的 Conda base：

```powershell
cd E:\python\pachong\azurlane-bwiki-voice-downloader
D:\anaconda3\python.exe -m pip install -e .
```

## 2. 启动程序

激活环境后运行：

```powershell
python main.py
```

或直接指定本机 Conda Python：

```powershell
D:\anaconda3\python.exe main.py
```

程序只有一个入口，不需要记忆 `ship`、`all` 等命令行子命令。

## 3. 下载指定舰娘

在主菜单输入 `1`，然后输入规范舰娘名称，例如：

```text
请输入舰娘名称（输入 0 返回）：欧根亲王
```

程序会依次：

1. 从动态舰娘索引中查找精确名称。
2. 下载并解析该舰娘的当前 BWiki HTML。
3. 显示本体、皮肤数量、每个语音集的文本和 MP3 数量。
4. 下载所有可用 MP3，并为成功或已存在的 MP3 写入同名 TXT。
5. 原子更新 `metadata.json`、任务状态和失败记录。
6. 完成后返回主菜单。

如果名称不精确，例如输入“欧根”，程序只会列出候选：

```text
未找到准确角色“欧根”。

是否是：

1. 欧根亲王
2. 小欧根
0. 返回
```

只有明确选择候选后才会下载。程序不会自动把相似名称当成目标。

输入空名称会继续提示；输入 `0` 返回主菜单。

## 4. 下载全部舰娘

在主菜单输入 `2`。程序会调用 MediaWiki `Category:舰娘` API，分页获取运行时的完整舰娘列表，不使用源码内固定数组。

全量任务行为：

- 每批最多同时处理 4 名舰娘页面。
- 所有舰娘共享最多 8 个并发音频下载。
- metadata、MP3 和 TXT 都完整的舰娘直接 SKIP。
- 未完成舰娘从实际文件和 metadata 恢复。
- 单个页面或 MP3 失败不会终止整个批量任务。

全站资源很多。第一次运行前请确认磁盘空间和网络环境。程序不会要求第二次确认，选择 `2` 后会直接开始。

如果 BWiki 后来为一个已经完成的舰娘增加了新皮肤，可以通过菜单 `1` 再次指定该舰娘；指定舰娘模式会重新解析最新页面，同时跳过仍有效的旧 MP3，只下载新增或变化的资源。

## 5. 文件和目录

无论从哪个工作目录启动，输出都位于项目根目录：

```text
azurlane-bwiki-voice-downloader/
├── voices/
│   └── 舰娘规范名/
│       ├── metadata.json
│       ├── 本体/
│       └── 真实皮肤名称/
├── state/
│   ├── state.json
│   └── failed.json
└── logs/
    └── app.log
```

每条存在 MP3 的语音对应：

```text
台词原文.mp3
台词原文.txt
```

TXT 保存从页面渲染 DOM 提取的完整中文台词。为了跨 Windows/Linux 使用，文件名会做安全转换，但 TXT 和 metadata 中的 `text` 不会跟着改变。

例如：

```text
原文：指挥官？你在做什么/呢？
文件：指挥官？你在做什么／呢？.mp3
TXT： 指挥官？你在做什么/呢？
```

当前文件名主体最长 100 个字符；超过后会截断并添加 8 位短哈希。相同台词依次添加 `_2`、`_3`。

## 6. 重复运行与自动修复

程序不会只凭“文件存在”判断成功。已有 MP3 必须：

- 大小大于最小文件头长度。
- 不是 HTML/JSON 错误页。
- 包含 ID3 标记或合理的 MPEG 音频帧同步头。

如果 MP3 合法：

- MP3 与 TXT 都存在且 TXT 正确：SKIP。
- MP3 存在但 TXT 缺失：SKIP MP3，并重新写入 TXT。
- metadata 缺失或损坏：重新解析页面并结合实际文件重建。

如果 metadata 记录的源 URL 发生变化，程序会重新下载该文件，不会把旧资源直接当成最新资源。

## 7. 断点续传

下载过程先写入：

```text
台词.mp3.part
台词.mp3.part.meta.json
```

sidecar 保存当前 URL、ETag 和 Last-Modified。下次运行时：

- 有 `.part` 时发送 `Range: bytes=<本地大小>-`。
- 有校验器时同时发送 `If-Range`。
- 正确的 `206 Content-Range` 才会追加。
- 服务器返回 `200` 表示不接受本次续传，程序从头覆盖 `.part`。
- `416` 只有在远端长度等于本地完整 `.part` 且文件头有效时才会直接完成，否则重新请求。

完成后 `.part` 原子替换为最终 `.mp3`，sidecar 自动删除。

## 8. Ctrl+C

主菜单按 Ctrl+C 会正常退出。

下载过程中按 Ctrl+C：

- 不再开始下一批舰娘。
- 取消尚未完成的当前下载。
- 已收到的传输块保留在 `.part`。
- 当前 metadata 写入 `interrupted` 状态。
- 已完成 MP3/TXT 不受影响。

重新运行并选择原任务即可恢复。不要手动删除 `.part`，除非确认不再需要继续。

## 9. 日志和失败记录

默认 CLI 只显示解析、下载、完成、跳过、重试和失败等关键信息。更详细记录在：

```text
logs/app.log
```

日志文件最大约 2 MB，并保留 3 个轮换备份。

当前未解决失败位于：

```text
state/failed.json
```

失败记录包含阶段、舰娘、皮肤、category、完整台词、URL 和错误。重新运行后如果失败已经解决，对应记录会自动移除。

## 10. 常见问题

### 提示“未找到舰娘”

程序会先查 BWiki 规范页名，再解析 MediaWiki 重定向；例如输入展示名“萨沃伊亲王”可以直接定位到规范页“欧根亲王”。没有重定向页的展示名会进入站内搜索，结果只保留 `Category:舰娘` 中的页面并要求人工选择，例如输入“泽特”时可选择“曾克海军上将”。如果依然没有候选，请检查名称中的异体字、全角符号和罗马数字。

### 页面解析失败

BWiki 可能修改了模板。先运行 DOM 检查脚本并保存新 HTML：

```powershell
D:\anaconda3\python.exe inspect_bwiki_dom.py --save-fixture tests\fixtures\new-page.html
```

不要通过全局抓取或按纯文本顺序配对来绕过错误。应比较 [架构文档中的 DOM 合同](ARCHITECTURE.md#5-dom-解析合同) 后更新 selector 和测试。

程序允许语音表中出现数据单元格完全为空的可选模板行；例如初月页面的空“舰船型号”行不会被当成语音，也不会阻止后续台词下载。非空的未知结构仍会记录为解析失败，避免台词与 MP3 错配。

### 有 MP3，但程序仍重新下载

常见原因是文件为 0 字节、下载到错误页、没有可识别的 MP3 头，或 metadata 中源 URL 已改变。检查 `logs/app.log` 和对应 metadata 条目。

### 全部模式为什么跳过某个舰娘

只有 metadata 标记完整，并且每条有音频记录都能找到有效 MP3 和内容匹配的 TXT 时才会整舰 SKIP。需要强制刷新页面时，使用菜单 `1` 单独选择该舰娘。

## 11. 运行测试

```powershell
cd E:\python\pachong\azurlane-bwiki-voice-downloader
D:\anaconda3\python.exe -m pytest -q
```

测试使用保存的真实 HTML fixture 和本地 MockTransport，不会批量访问线上 BWiki，也不会写入正式 `voices/`。
