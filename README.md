# ppanel

## 部署

- [Cloudflare Pages：用户端与管理端](deploy/cloudflare/README.md) — 部署配置与工作流位于父仓库，不修改前端子模块。
- [后端 GHCR 镜像版本发布](deploy/backend/README.md) — 发布多架构容器镜像，复用后端 Dockerfile，不修改后端子模块。
- [节点版本发布与一键安装](deploy/node/README.md) — 由父仓库发布 Linux 多架构二进制，校验下载并安装 systemd 服务，不修改节点子模块。

### 节点一键安装

父仓库首次成功发布正式 `node-v*` 版本后，在 Linux/systemd 节点上以 root 执行（需要 curl、python3 和 sha256sum）：

```bash
curl -fSL https://raw.githubusercontent.com/jaoau0803/ppanel/HEAD/deploy/node/install.sh -o /tmp/ppanel-node-install.sh && bash /tmp/ppanel-node-install.sh
```

首次安装会提示输入面板 API 地址、服务器 ID 和通讯密钥；再次运行保留配置并升级至最近发布的正式节点版本。详细发布配置、指定版本及无人值守参数见[节点部署文档](deploy/node/README.md)。
