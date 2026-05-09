# Cloudflare Tunnel 本地外网访问说明

当前项目已支持通过本地脚本同时拉起：

- 本地 HTTPS 后端：`https://localhost:8016`
- Cloudflare Tunnel 外网入口：按 `.env` 中 `EXTERNAL_API_BASE_URL` / `CLOUDFLARED_PUBLIC_HOSTNAME` 决定

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

说明：当前脚本仍支持 Tunnel，但旧的 `speedforce.cycleforce.cc` 配置已建议停用。
后续如果要在服务器上启用，请把 `.env` 中公网域名改为 `https://api.speedasia.net`，
并配置对应的 Tunnel / 反向代理，再让它指向 `https://localhost:8016`。

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

- `https://api.speedasia.net/health`
- `https://api.speedasia.net/docs`
- `https://api.speedasia.net/openapi.json`
- `https://api.speedasia.net/api/system/config_check`
- `https://api.speedasia.net/api/system/public_endpoints`
