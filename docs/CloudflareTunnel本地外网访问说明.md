# Cloudflare Tunnel 本地外网访问说明

当前项目已支持通过本地脚本同时拉起：

- 本地 HTTPS 后端：`https://localhost:8016`
- Cloudflare Tunnel 外网入口：`https://speedforce.cycleforce.cc`

## 配置项

配置保存在项目根目录 `.env`：

- `EXTERNAL_API_BASE_URL`
- `CLOUDFLARED_TUNNEL_TOKEN`
- `CLOUDFLARED_PUBLIC_HOSTNAME`
- `CLOUDFLARED_TARGET_URL`
- `ENABLE_LOCAL_HTTPS`
- `LOCAL_HTTPS_CERT_FILE`
- `LOCAL_HTTPS_KEY_FILE`

## 启动

命令行：

```powershell
.\start_public_backend.ps1 -KillPortOwner
```

说明：当前你提供的 tunnel token 在 Cloudflare 远端配置里已将
`speedforce.cycleforce.cc` 指向 `https://localhost:8016`，
所以公网启动脚本会按 `8016` 拉起本地 HTTPS 后端。

双击：

- `一键启动外网后台.bat`
- `一键启动外网后台-热更新.bat`

说明：

- `一键启动外网后台.bat`：稳定运行版，不开启热更新。
- `一键启动外网后台-热更新.bat`：开发联调版，后端 Python 代码变更后自动重载。
- 修改 `.env` 配置后，仍建议手动重启。

## 停止

```powershell
.\stop_public_backend.ps1
```

双击：

- `一键停止外网后台.bat`

## 关键接口

- `https://speedforce.cycleforce.cc/health`
- `https://speedforce.cycleforce.cc/docs`
- `https://speedforce.cycleforce.cc/openapi.json`
- `https://speedforce.cycleforce.cc/api/system/config_check`
- `https://speedforce.cycleforce.cc/api/system/public_endpoints`
