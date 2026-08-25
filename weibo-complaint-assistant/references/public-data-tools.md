# 微博公开信息读取与降级策略

## 目的

在不要求用户登录、不配置微博 API 且不接收用户 Cookie 的前提下，尽力读取单条微博的公开信息。该能力只是投诉函撰写的辅助环节，平台限制或字段缺失不得阻断后续工作。

## 脚本用法

### 读取单条微博

```bash
python scripts/weibo_public.py collect "https://weibo.com/<uid>/<bid>" --pretty
python scripts/weibo_public.py collect "https://m.weibo.cn/detail/<mid>" --pretty
python scripts/weibo_public.py collect "<mid或bid>" --pretty
```

返回状态：

- `ok`：取得主要公开字段。
- `partial`：只能解析链接、ID 或部分内容。继续使用已取得字段。
- `unavailable`：公开端点暂时不可用、内容已删除、超出公开访问范围或触发平台风控。不要要求用户登录；改用截图、原文与用户说明。

不将 `unavailable` 直接解释为“内容不存在”。平台风控、区域限制或匿名访问限制也可能导致同样结果。

## 链接与 ID 处理

脚本支持：

- `https://weibo.com/<uid>/<bid>`
- `https://www.weibo.com/<uid>/<bid>`
- `https://m.weibo.cn/detail/<mid>`
- `https://m.weibo.cn/status/<mid-or-bid>`
- 数字 `mid`
- 微博 Base62 `bid`
- `t.cn` 短链接，但短链接解析失败时只保留原链接并降级处理

不得用该脚本访问非微博域名。

## 结果整理

优先使用以下字段：

| 字段 | 用途 | 缺失时 |
| --- | --- | --- |
| `canonical_url` | 投诉对象与投诉函原始链接 | 使用 `input_url` 或写待补充 |
| `id` / `bid` | 定位具体微博 | 写未获取 |
| `user.screen_name` / `user.id` | 定位账号 | 使用截图所见，并标注来源 |
| `text` | 投诉事实与类型判断 | 使用用户复制原文或截图 |
| `created_at` | 定位时间 | 写未获取 |
| `reposts_count` / `comments_count` / `attitudes_count` | 说明当前公开互动数据 | 写未获取，不影响后续 |
| `media` | 识别是否需要用户补充图像或视频证据 | 不推断“无媒体” |

## 降级顺序

1. 公开 JSON 端点。
2. 公开微博详情页可解析数据。
3. 用户提供的页面截图或录屏。
4. 用户复制的微博原文和账号信息。
5. 仍有字段缺失时，使用“未获取／待补充”继续生成投诉内容。

不在这个流程中安装或强制使用 `jackwener/weibo-cli`，因其完整功能依赖浏览器 Cookie 或扫码登录，不符合本 Skill 的零配置目标。
