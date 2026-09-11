# Metadata 与状态格式

本文描述当前 `version: 1` 的 JSON 格式。路径均使用相对于舰娘目录的 `/` 分隔形式，方便跨 Windows/Linux 读取。

## 1. `metadata.json`

每名舰娘有独立 metadata：

```text
voices/<舰娘规范名>/metadata.json
```

简化示例：

```json
{
  "version": 1,
  "ship": "欧根亲王",
  "display_name": "萨沃伊亲王",
  "source": "https://wiki.biligame.com/blhx/%E6%AC%A7%E6%A0%B9%E4%BA%B2%E7%8E%8B",
  "fetched_at": "2026-09-11T15:04:24.000000+00:00",
  "updated_at": "2026-09-11T15:04:27.000000+00:00",
  "complete": true,
  "voice_set_directories": {
    "本体": "本体",
    "【誓约】命运交响曲": "【誓约】命运交响曲"
  },
  "voice_sets": {
    "本体": [
      {
        "category": "触摸台词",
        "text": "这点程度就满足了吗？",
        "source_key": "touch:1",
        "data_key": "touch",
        "data_key_index": "1",
        "source_url": "https://patchwiki.biligame.com/images/blhx/...mp3",
        "mp3": "本体/这点程度就满足了吗？.mp3",
        "txt": "本体/这点程度就满足了吗？.txt",
        "download_status": "skipped",
        "size": 34316,
        "error": null
      },
      {
        "category": "礼物台词",
        "text": "谢啦~（飞吻）",
        "source_key": "gift:1",
        "data_key": "gift",
        "data_key_index": "1",
        "source_url": null,
        "mp3": null,
        "txt": null,
        "download_status": "no_audio",
        "size": null,
        "error": null
      }
    ]
  },
  "stats": {
    "success": 0,
    "skipped": 114,
    "failed": 0,
    "no_audio": 4,
    "pending": 0
  }
}
```

## 2. 顶层字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `version` | integer | metadata 格式版本，当前为 1 |
| `ship` | string | MediaWiki 规范页名，也是默认顶层目录名 |
| `display_name` | string/null | 当前页面 `<title>` 提取的展示名或和谐名 |
| `source` | string | 本次解析使用的最终 BWiki 页面 URL |
| `fetched_at` | ISO 8601 string | 页面解析时间，UTC |
| `updated_at` | ISO 8601 string | 最近一次 metadata 原子写入时间，UTC |
| `complete` | boolean | 当前已知有音频条目是否全部成功或有效跳过 |
| `voice_set_directories` | object | 真实语音集名称到安全目录组件的映射 |
| `voice_sets` | object | 本体和各皮肤的语音记录数组 |
| `stats` | object | 最近一次处理后的状态计数，不是终身累计下载量 |

`display_name` 不能覆盖 `ship`。例如欧根亲王页面的规范页名仍是“欧根亲王”，即使页面当前展示“萨沃伊亲王”。

## 3. 语音记录字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `category` | string | BWiki 表格行的台词类别 |
| `text` | string | 从单个 DOM 语音块提取的完整渲染台词 |
| `source_key` | string | `data_key:data_key_index` 形式的页面内稳定标识 |
| `data_key` | string/null | `.ship_word_block` 的原始 `data-key` |
| `data_key_index` | string/null | `.ship_word_block` 的原始 `data-key-i` |
| `source_url` | string/null | 同一语音块内的原始 MP3 URL |
| `mp3` | string/null | 相对舰娘目录的本地 MP3 路径 |
| `txt` | string/null | 相对舰娘目录的本地 TXT 路径 |
| `download_status` | string | 当前处理状态 |
| `size` | integer/null | 成功或跳过后的本地 MP3 字节数 |
| `error` | string/null | 最后一次失败原因 |

`category` 不参与正常文件名生成。文件名优先来自 `text`，因此一个“主界面”类别下的三条语音会生成三个不同的台词文件。

## 4. `download_status`

| 值 | 含义 |
| --- | --- |
| `pending` | 已解析并分配路径，尚未完成下载 |
| `success` | 本次运行成功下载 MP3 并写入 TXT |
| `skipped` | 本地 MP3 已有效，已确认或补写 TXT |
| `failed` | MP3 下载或 TXT 写入最终失败 |
| `no_audio` | 页面有台词但同一语音块没有 MP3 |
| `interrupted` | 当前任务被取消，可在下次运行恢复 |

`success` 和 `skipped` 描述最近一次处理结果。例如首次运行可能显示 `success: 114`；第二次验证时相同文件会变为 `skipped: 114`。这不会丢失文件，实际文件系统才是已下载内容的最终证据。

`no_audio` 记录必须满足：

```json
{
  "source_url": null,
  "mp3": null,
  "txt": null,
  "download_status": "no_audio"
}
```

程序不会为它创建空 MP3。

## 5. `stats`

| 字段 | 含义 |
| --- | --- |
| `success` | 本次实际完成的新下载数 |
| `skipped` | 已存在且验证有效的 MP3 数 |
| `failed` | 最终失败的有音频记录数 |
| `no_audio` | 页面中没有 MP3 的文本记录数 |
| `pending` | 尚未完成或中断的有音频记录数 |

`complete` 的计算条件是 `failed == 0` 且 `pending == 0`。全量模式整舰 SKIP 前还会重新检查实际 MP3 和 TXT，因此仅手工把 `complete` 改成 `true` 不会绕过文件验证。

## 6. `state/state.json`

这是任务进度索引，不是唯一恢复依据。简化示例：

```json
{
  "version": 1,
  "mode": "all",
  "total": 691,
  "updated_at": "2026-09-11T15:04:27.000000+00:00",
  "ships": {
    "欧根亲王": {
      "status": "complete",
      "updated_at": "2026-09-11T15:04:27.000000+00:00",
      "page_url": "https://wiki.biligame.com/blhx/...",
      "summary": {
        "success": 0,
        "skipped": 114,
        "failed": 0,
        "no_audio": 4
      }
    }
  }
}
```

舰娘级状态可能为：

- `parsing`
- `downloading`
- `complete`
- `partial`
- `failed`
- `interrupted`

文件缺失、JSON 损坏或字段不可识别时，程序会从舰娘 metadata 和实际文件重新判断，不要求用户手工修复 `state.json`。

## 7. `state/failed.json`

简化示例：

```json
{
  "version": 1,
  "updated_at": "2026-09-11T15:04:27.000000+00:00",
  "ships": {
    "示例舰娘": {
      "updated_at": "2026-09-11T15:04:27.000000+00:00",
      "items": [
        {
          "stage": "audio",
          "voice_set": "本体",
          "category": "登录台词",
          "text": "示例台词",
          "url": "https://patchwiki.biligame.com/images/blhx/...mp3",
          "error": "HTTP 404"
        }
      ]
    }
  }
}
```

页面请求或解析失败使用 `stage: "page_or_parse"`；单条音频或 TXT 失败使用 `stage: "audio"`。某名舰娘重新运行后全部成功，其旧失败条目会从 `ships` 中移除。

## 8. `.part.meta.json`

断点 sidecar 示例：

```json
{
  "url": "https://patchwiki.biligame.com/images/blhx/...mp3",
  "etag": "\"example-etag\"",
  "last_modified": "Mon, 26 Oct 2020 06:26:25 GMT"
}
```

它与 `name.mp3.part` 同时存在，只用于证明局部文件对应的远端实体。最终 MP3 完成后，两者都会消失并由 `name.mp3` 取代。

## 9. 兼容性约定

- JSON 文件统一 UTF-8、缩进 2 空格、`ensure_ascii=False`。
- 时间统一使用带时区的 ISO 8601 UTC 字符串。
- 相对路径统一写 `/`，读取时通过 `pathlib.Path` 转换。
- metadata 的相对路径必须留在本舰娘目录内，越界路径会被拒绝。
- 新增字段时应保持旧字段含义；破坏性格式变化必须提升 `version` 并提供迁移逻辑。
