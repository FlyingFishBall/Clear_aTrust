# 深信服 / aTrust 卸载残留一键清理脚本

> 当前版本：v1.2

批处理与 Python 组合脚本，深度清理深信服 aTrust 客户端在本机留下的残留，并修复残留文件导致的异常（包括但不限于未被完整卸载的残留进程、托盘无法退出的幽灵图标、浏览器中的无用策略、注册表残留、卸载残留文件等）。支持在清理前自动检测已安装程序并引导官方卸载。本脚本主要针对 aTrust，对 Sangfor / EasyConnect 部分重叠组件同样有效。

## 系统要求

- **操作系统**：Windows（x86 / x64 / ARM64 均可）
- **Python**：3.7+
- **权限**：管理员权限
- **前提**：aTrust 已通过控制面板正常卸载（本脚本仅清理卸载后的残留）

## 清理范围（8 步）

| 步骤 | 内容 | 说明 |
| --- | --- | --- |
| 0 | 检测并弹出官方卸载 | 扫描已安装的深信服/aTrust/Ingress 程序，引导官方卸载 |
| 1 | 停止并删除已知服务 | eaio_service、nac_monitor、IngressMgr |
| 2 | 终止残留进程 | eaio_service.exe、nac_monitor.exe、IngressMgr.exe 等 |
| 3 | 清理内核驱动 | WinDivert、SdpVnic、aTrustXtun |
| 4 | 清理注册表 | Sangfor/Ingress 安装配置、事件日志、Services 子键残留 |
| 5 | 清理浏览器组策略 | 解除由 aTrust 导致的 Chrome/Edge「您的浏览器由所属组织管理」 |
| 6 | 全盘扫描残留 | 服务、驱动文件、DriverStore 驱动包、程序目录 |
| 7 | 清除所有扫描到的残留 | 含标记重启后删除处理 |

### 第 4 步详情：注册表清理

深信服/aTrust 在注册表中留下多处配置，正常卸载后可能仍有残留：

- `HKLM\SOFTWARE\Sangfor` 及 `WOW6432Node` 分支（安装配置）
- `HKCU\SOFTWARE\Sangfor`（用户级配置）
- `HKLM\SYSTEM\CurrentControlSet\Services\EventLog\Application\Ingress Manager`（事件日志）
- 额外扫描 `Services` 分支下含 Sangfor 关键词的残留子键

### 第 5 步详情：浏览器组策略修复

深信服 aTrust 会向注册表注入策略，导致 Chrome/Edge 被"组织管理"，且在卸载后可能未被卸载程序正确清理：

- 删除 `HKLM\SOFTWARE\Policies\Google\Chrome`（Chrome）
- 删除 `HKLM\SOFTWARE\Policies\Microsoft\Edge`（Edge）
- 删除 `HKLM\SOFTWARE\Policies\Chromium`（Chromium 内核浏览器）
- 执行 `gpupdate /force` 刷新策略

执行后，`chrome://policy`以及 `edge://policy` 中残留的深信服策略项消失，浏览器恢复自主管理。

## 使用方法

0. 从 [Releases](https://github.com/FlyingFishBall/Clear_aTrust/releases) 下载最新版 `Source code (zip)`，解压到任意文件夹
1. 以管理员身份运行 `stop_sangfor.bat`
2. 脚本自动检测 Python 环境（含本地目录兜底扫描），若无则给出清华源/官方源下载地址，引导手动安装（3.13.2，需勾选 Add python.exe to PATH）
3. 脚本先检测是否残留已安装程序，若有则弹出官方卸载程序引导完成
4. 逐步执行清理，过程中显示进度
5. 完成后可选重建 Windows 搜索索引

## 注意事项

- 需要管理员权限
- 部分驱动可能在下次重启后才彻底删除
- 脚本不会修改网络配置、不会删除用户数据

## 免责声明

本脚本操作注册表、系统服务和内核驱动。使用前请确认已通过控制面板正常卸载 aTrust。本脚本仅限用于清理已通过官方途径正常卸载后的残留文件与配置。不可被用于绕过安全策略、干扰正常运行中的软件或未经授权的系统修改。作者不对因使用本工具造成的任何损失或不当使用承担责任。

## 致谢

脚本编写：DeepSeek V4

## 反馈与贡献

有问题或建议？欢迎提交 [Issue](https://github.com/FlyingFishBall/Clear_aTrust/issues)。

## 版本历史

| 版本 | 更新内容 |
| --- | --- |
| v1.2（2026-08-28） | 优化无 Python 环境时的下载逻辑：移除自动下载安装，改为提供清华源/官方源直链（Python 3.13.2）并打开浏览器，引导手动安装 |
| v1.1.1 | 新增安装检测与注册表清理；Python 本地目录兜底扫描；新增跳过继续选项；修复编码与 PermissionError 等问题 |
| v1.0.0 | 首个版本：aTrust 卸载残留一键清理 |

## 许可证

MIT License · Copyright (c) 2026 FlyingFishBall
