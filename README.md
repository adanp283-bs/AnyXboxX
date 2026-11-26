# AnyXboxX 自动同步

| 用途 | 位置 |
|---|---|
| 上游 | [LooperSalty/AnyXboxX](https://github.com/LooperSalty/AnyXboxX)，`main` |
| 我们的代码 | [adanp283-bs/AnyXboxX 的 main](https://github.com/adanp283-bs/AnyXboxX/tree/main) |
| 中文项目说明 | [README.zh-CN.md](https://github.com/adanp283-bs/AnyXboxX/blob/main/docs/i18n/README.zh-CN.md) |
| 同步配置 | 本分支 `sync-control` 的 `.github/workflows/sync-anyxboxx.yml` |

2026-11-26 已创建独立 fork，并在所有者授权后配置了仓库专用写入凭据及仅限 `sync-control` 的环境策略。默认分支现为 `sync-control`。北京时间 11:00:45，[首次运行 #1](https://github.com/adanp283-bs/AnyXboxX/actions/runs/45746115351)的同步步骤成功，上游与本仓库 `main` 均为 `c4c93bdc413191a9dc909998d2d53080a3f0c880`；随后进入 5 分钟等待。下一轮自动续跑正在验证。每 12 小时的项目进度监控单独运行。

## 已准备的行为

工作流固定源仓库 ID `1466028817`，只允许在 `adanp283-bs/AnyXboxX` 的 `sync-control` 分支执行。首次同步可创建目标分支，此后只快进 `main`；遇到独立提交或并发分歧就停止，不强制覆盖。不检出或执行上游代码。

同步后，独立的 `queue_next` 任务经 GitHub environment 等待 5 分钟，再自动派发下一轮。每小时第 7、37 分钟的 cron 是恢复入口；GitHub 排队可能造成额外延迟。

## 仓库专用凭据与环境

**adanp283-bs/AnyXboxX** 使用独立的允许写入的 SSH deploy key。公钥登记在该仓库，私钥仅保存为受限 environment 中的 `ANYXBOXX_SYNC_KEY`，不放进代码、仓库级 secret、日志或聊天。临时本地私钥已删除；旧仓库的凭据没有复制到这里。

当前配置和恢复后的验证顺序：

1. 创建 `anyxboxx-sync` environment，只允许 `sync-control` 分支，不允许标签或其他分支；先设置限制，再保存 secret。
2. 创建 `anyxboxx-sync-interval` environment，也只允许 `sync-control`，设置 5 分钟等待，不设置人工审批，不保存私钥。
3. 创建本仓库专用可写 deploy key，将私钥存入 `anyxboxx-sync` 的 `ANYXBOXX_SYNC_KEY`；登记成功后删除本地临时私钥。
4. 将仓库默认分支改为 `sync-control`，从该分支启动 `Sync AnyXboxX`。
5. 核对首次同步成功，再等待由 `github-actions[bot]` 自动发起的下一轮同步成功，并核对该轮实际抓取的上游 SHA 与本仓库 `main` 一致。

同步任务的内置 `GITHUB_TOKEN` 只有 `contents: read`；推送使用上述仓库专用 key。续跑任务只有 `actions: write`，不使用同步私钥。

## 本地验证

安装 PyYAML 后，执行 `python -m unittest discover -s tests -v`。测试在临时本地 Git 仓库运行实际工作流 shell，覆盖首次导入、快进、无更新、源身份错误、分支查询失败、缺少 key、分歧及并发更新，同时验证控制分支和旁支保留。它们不代表 GitHub 上的自动运行已启用。

## 暂停与恢复

暂停时禁用 `Sync AnyXboxX` 并取消正在等待的运行。恢复时重新启用工作流，再从 `sync-control` 启动一次。仅取消一次运行不会关闭 cron 恢复入口。
