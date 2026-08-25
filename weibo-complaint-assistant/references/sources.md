# 资料来源与时效说明

## 投诉方法来源

- 《微博投诉手册（2023年）》：用户提供的培训材料，用于页面投诉类型、具体原因和行为判定的基础整理。
- 《如何投诉和撤稿函》、《自媒体平台投诉路径简介（外部培训版）》以及用户提供的既有投诉函样本：用于投诉函结构、事实证据对应、处理请求与附件清单的归纳。

上述原始文档不作为 Skill 运行依赖，GitHub 版不包含其中的姓名、身份证号、联系方式等个人信息。

## 微博官方页面

- [涉企侵权投诉专区](https://service.account.weibo.com/h5/roles/zone)：本 Skill 对用户展示的唯一官方入口。页面包含涉企侵权治理内容、电脑端与手机端投诉指引。
- [微博社区公约](https://service.account.weibo.com/h5/roles/gongyue)：第一条明确微博由“北京微梦创科网络技术有限公司”创建、运营；第六十三条明确该公司是微博平台的合法运营主体。因此正式微博投诉函默认以“致：北京微梦创科网络技术有限公司”作为收函称呼。
- [北京市药品监督管理局平台备案](https://xxcx.yjj.beijing.gov.cn/eportal/ui?id=faca5796deed46c98239904b70eee825&pageId=723920)：公开备案显示，企业名称为“北京微梦创科网络技术有限公司”，对应网站名称“微博平台”、域名 `weibo.com/weibo.cn` 及客户端“微博”，作为运营主体的交叉核验。

## 公开信息读取技术参考

- [jackwener/weibo-cli](https://github.com/jackwener/weibo-cli)：提供微博详情、用户与互动数据等功能，但依赖浏览器 Cookie 或扫码登录。本 Skill 不将其作为必装依赖。
- [tamnd/weibo-cli](https://github.com/tamnd/weibo-cli)：说明单条公开微博详情可通过 `m.weibo.cn` 公开 JSON 端点以移动端请求头读取，用户信息与时间线等部分表面需要 Cookie。
- [WeiboCollectionCategorizer_2.0 微博数据格式参考](https://github.com/AlanZ-Git/WeiboCollectionCategorizer_2.0/blob/main/reference/01_weibo_data_format.md)：提供单条微博、媒体与互动字段的公开格式参考。

`scripts/weibo_public.py` 为本 Skill 的独立实现，未内置或复制上述 CLI 的代码，不使用用户登录态。

## 时效说明

- 投诉类型主要来自 2023 年手册，微博后续可能调整分类、按钮名称、证明材料或提交条件。
- 微博运营主体的核验结论更新于 2026 年 8 月 25 日。正式寄送或用于诉讼前，如微博服务协议、社区公约或政府备案已更新，应以当时最新公示主体为准。
- 公开数据端点不是对外承诺的稳定 API，可能随时失效、返回不完整数据或要求登录。
- 因此本 Skill 以“当前页面实际显示”为最终操作依据，并且将信息采集设为可失败的辅助步骤。
