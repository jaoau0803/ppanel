# 节点发布与一键安装

由父仓库 `.github/workflows/release-node.yml` 发布，不修改 `ppanel-node` 子模块。构建父仓库提交中记录的节点版本，不追踪子模块分支最新提交。

## 首次配置与发布

1. 提交并推送父仓库改动到默认分支。
2. 在父仓库 Settings → Environments 创建 `node-release`，建议配置审批及可信分支/标签限制。工作流会执行检出的节点代码。
3. 如果节点子模块是私有仓库，在该 Environment 添加 `NODE_READ_TOKEN`（fine-grained PAT，仅节点仓库 Contents: Read）。公开仓库通常不需要。GitHub Release 使用自动的 `GITHUB_TOKEN`，需允许 Actions 写 Contents。
4. 父仓库 Actions → **Release Node** → Run workflow，选择父仓库分支，输入 `1.2.3`、`1.2.3-beta.1` 或 `1.2.3-rc.1`（也接受 `v` / `node-v` 前缀）。或在父仓库推送 `node-v1.2.3` 标签。

手动发布会在所选父仓库提交创建 `node-v*` 标签；标签触发则使用该标签记录的子模块提交。在已有标签手动运行时，输入版本必须匹配标签。已存在的 Release 不覆盖，发布新版本请使用新版本号。失败留下的 draft 需先人工检查并删除后重跑；不要删除已经公开的版本。

工作流先运行父仓库部署测试及节点根模块、Nowhere 模块的 race 测试，再交叉构建 Linux `amd64`、`arm64`、`s390x`。全部成功后创建 draft 并上传全部附件，再公开 Release；预发布会标记 prerelease。不会修改父仓库全局 latest，避免与其他组件混用。

附件包括：

- `ppanel-node-linux-{amd64,arm64,s390x}.tar.gz`：二进制、GeoIP/GeoSite 和许可证。
- `install.sh`、`SHA256SUMS`：安装脚本与 SHA-256 校验值。
- `SOURCE.txt`：父仓库和节点源码提交。GeoIP/GeoSite 来自 Loyalsoldier/v2ray-rules-dat 的 release 分支，构建时下载；不是完全可复现构建。

## 一键安装

**需要父仓库和 Release 公开可下载，且至少已成功发布一个正式 `node-v*` 版本。** 私有仓库的匿名命令不可用。支持 Linux/systemd，不支持 Alpine/OpenRC、macOS 或 Windows。脚本需要 root；不会自动安装依赖。先准备 `bash`、`curl`、`python3`、`sha256sum`、systemd 和基本系统工具。

root 用户执行（首次安装交互输入面板地址、服务器 ID 和通讯密钥）：

```bash
curl -fSL https://raw.githubusercontent.com/jaoau0803/ppanel/HEAD/deploy/node/install.sh -o /tmp/ppanel-node-install.sh && bash /tmp/ppanel-node-install.sh
```

`HEAD` 跟随父仓库默认分支。建议先检查下载脚本再以 root 运行。安装脚本从 GitHub releases API 分页查找**最近发布的正式节点版本**，跳过后端等其他组件、draft 和预发布，不依赖仓库全局 latest。下载归档后校验 SHA-256 再安装；校验值与附件来自同一 GitHub Release，不是独立签名验证。

指定版本及无人值守安装：

```bash
bash /tmp/ppanel-node-install.sh \
  --version node-v1.2.3 \
  --api-host https://api.example.com \
  --server-id 1 \
  --secret-key '替换成通讯密钥'
```

密钥作为命令参数可能出现在 shell 历史和进程列表，交互输入更安全。预发布需显式指定 `--version node-v1.2.3-rc.1`。fork 用户通过 `--repo OWNER/REPO` 选择自己的发布仓库，并替换脚本下载 URL。

也可从指定 Release 下载与版本配套的脚本：

```bash
curl -fSL https://github.com/jaoau0803/ppanel/releases/download/node-v1.2.3/install.sh -o /tmp/ppanel-node-install.sh && bash /tmp/ppanel-node-install.sh --version node-v1.2.3
```

## 配置、升级与管理

- 安装目录：`/usr/local/PPanel-node`；配置：`/etc/PPanel-node/config.yml`，首次生成权限为 `0600`。
- 重跑脚本即可升级；指定旧版本可降级。**已有配置始终保留**，传入的新 API 参数不会覆盖它。升级前建议备份配置和现有二进制。
- 下载、校验和暂存失败不会修改已有安装；安装后的启动失败不会自动回滚，请检查日志或重新安装旧版。
- 与旧版脚本沿用相同服务名及配置路径，会替换 systemd unit。`/usr/local/bin/ppnode` 是二进制软链，**不提供旧版交互管理菜单**；旧版 `/usr/bin/ppnode` 管理脚本不会被删除，不要用它升级（它仍指向上游）。
- 安装成功表示 systemd 重启命令成功，不代表与面板连接和协议监听已经通过生产验收。

```bash
systemctl status PPanel-node
systemctl restart PPanel-node
journalctl -u PPanel-node -f
/usr/local/bin/ppnode version
```

## 本地验证

```bash
bash -n deploy/node/install.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s deploy/node -p 'test_*.py' -v
```

本地测试不访问网络、不需要 root、不改写系统目录。实际构建、公开 Release 下载、systemd 安装及面板联通仍需在 GitHub Actions / Linux 节点上验证。
