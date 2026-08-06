# CMP 170HX 维基

一份针对 NVIDIA CMP 170HX（GA100）的全面技术参考：硅片、固件、社区解锁、操作流程、以及开放前沿。

55 个页面、约 27.8 万词。截至 **2026-07-31** 最新。

## 两种阅读方式

- **[维基标签页](https://github.com/Consensus-Protocol/cmp170hx/wiki)** 用于浏览、带侧边栏。
  那里的页面从 `docs/` 生成、除链接风格外完全相同。
- **本仓库里的 `docs/`** 是唯一真相源。它可审查、接受拉取请求、
  并通过 MkDocs 构建带搜索的完整主题化站点。

让两者保持同步。`to_github_wiki.py` 把 `docs/` 发布到维基；如果编辑在维基上进行、
请先把它同步回来再继续、让两棵树永不分叉。

## 阅读它

页面是普通 Markdown、在 GitHub 上或任何编辑器里都能直接读。标注写成 GitHub alert 块引用
（`> [!NOTE]`）、GitHub 原生渲染它们；MkDocs 除非启用一个 callout 扩展、否则把它们渲染成
普通块引用。要获得搜索和导航：

```bash
pip install mkdocs mkdocs-material
mkdocs serve          # http://127.0.0.1:8000
mkdocs build          # 静态站点到 ../site
```

## 覆盖内容

| 章节 | 内容 |
|---|---|
| `start/` | 入门、卡识别、快速上手、风险、术语表 |
| `hardware/` | GA100 硅片、板卡变体、显存子系统、熔丝与 OTP、PCIe、NVLink、供电、散热、VBIOS |
| `unlock/` | 端到端机制：Falcon 与 Booter、ROP 链、权限级别掩码、显存几何布局、算力节流、驱动补丁、PCIe Gen2、完整寄存器参考 |
| `procedures/` | 安装、验证、排障、恢复、多卡、驱动版本、卸载 |
| `operations/` | 散热、供电与 PSU、物理改装、性能、LLM 推理、调优 |
| `frontier/` | 状态板与未解问题：PCIe Gen3/Gen4、NVLink、ECC、80 GB、P2P |
| `history/` | 时间线、净室与来源溯源问题、死路、工具谱系 |
| `appendix/` | 寄存器索引、保留工件、外部来源、方法论 |

## 本维基坚持的两点

**容量按 SKU 固定、且不可互换。** 8 GB 卡（`10de:20c2`）解锁到 **64 GB**。
10 GB 卡（`10de:2082`）解锁到 **40 GB**。10 GB 卡的 80 GB 配置被构建、测试、
并被判定不稳定而否决。

**PCIe 链路速度和链路位宽是独立问题。** Gen1 到 Gen2 是一个软件解锁、
自 2026-07-29 起合入 cmpunlocker `master`、所以任何装了解锁的卡都跑 Gen2。
超越 x4 位宽需要手工焊接 24 颗交流耦合电容。两者互不替代。

## 约定

普通正文是已确认事实。实验性、危险和未解决的材料用 alert 标注。立足单一观测的声称
在句子里说明。证据真正冲突且无物定案时、本维基如实说明、而非悄悄选择。

任何地方都不点名个人。发现按日期和渠道而非按人归属。见 `docs/appendix/methodology.md`
了解底层声称如何被收集、裁决和验证、以及对局限性的诚实交代。
