@echo off
:: Licensed under the MIT License. Copyright (c) 2026 FlyingFishBall
setlocal enabledelayedexpansion
:: 切换到 UTF-8 代码页，兼容 Windows Terminal / GBK 双环境
chcp 65001 >nul 2>&1
title 深信服/aTrust 一键清理工具
cd /d "%~dp0"

:: ========== 管理员检测与自动提权 ==========
net session >nul 2>&1
if !errorlevel! neq 0 (
    echo [提示] 需要管理员权限，正在请求提权...
    powershell -Command "Start-Process '%~f0' -Verb RunAs -Wait"
    exit /b
)

:: ========== Python 环境检测 ==========
set "PYTHON="

where python >nul 2>&1
if !errorlevel! equ 0 (
    python --version >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON=python"
)

if "!PYTHON!"=="" (
    where py >nul 2>&1
    if !errorlevel! equ 0 (
        py --version >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON=py"
    )
)

if "!PYTHON!"=="" (
    where python3 >nul 2>&1
    if !errorlevel! equ 0 (
        python3 --version >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON=python3"
    )
)

:: ========== 版本验证 ==========
if not "!PYTHON!"=="" (
    echo [检测] Python: !PYTHON!
    "!PYTHON!" -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
    if !errorlevel! equ 0 goto :run_script
    :: 有但太旧，不清除变量，仅提示
    echo [提示] 已检测到 Python 但版本低于 3.7，需要安装新版
    goto :ask_download
)

:: 完全没有 Python
echo [提示] 未检测到 Python 环境，需要 Python 3.7+

:ask_download
echo.
echo 是否下载并安装 Python 3.12.9？
echo.
choice /c yn /n /m "  [Y] 下载安装  [N] 退出: "
if !errorlevel! equ 2 goto :exit

:: ========== 镜像选择 ==========
echo.
echo 请选择下载源：
echo   [1] 清华 TUNA      (推荐 - 教育网/公网)
echo   [2] 上海交大 SJTUG  (华东地区)
echo   [3] 中科大 USTC
echo   [4] 华为云          (公网通用)
echo   [5] Python 官方     (海外，速度较慢)
echo   [6] 退出
echo.

choice /c 123456 /n /m "请输入选项 [1-6]: "

if !errorlevel! equ 6 goto :exit
if !errorlevel! equ 5 (
    set "MIRROR_URL=https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"
    set "MIRROR_NAME=Python 官方"
)
if !errorlevel! equ 4 (
    set "MIRROR_URL=https://mirrors.huaweicloud.com/python/3.12.9/python-3.12.9-amd64.exe"
    set "MIRROR_NAME=华为云"
)
if !errorlevel! equ 3 (
    set "MIRROR_URL=https://mirrors.ustc.edu.cn/python/3.12.9/python-3.12.9-amd64.exe"
    set "MIRROR_NAME=中科大 USTC"
)
if !errorlevel! equ 2 (
    set "MIRROR_URL=https://mirrors.sjtug.sjtu.edu.cn/python/3.12.9/python-3.12.9-amd64.exe"
    set "MIRROR_NAME=上海交大 SJTUG"
)
if !errorlevel! equ 1 (
    set "MIRROR_URL=https://mirrors.tuna.tsinghua.edu.cn/python/3.12.9/python-3.12.9-amd64.exe"
    set "MIRROR_NAME=清华 TUNA"
)

set "INSTALLER=%TEMP%\python-3.12.9-amd64.exe"

echo.
echo ============================================
echo  下载源: !MIRROR_NAME!
echo ============================================

:: 尝试 curl 下载 (Win10+ 自带，有进度条)
where curl >nul 2>&1
if !errorlevel! equ 0 (
    echo 正在下载 Python 3.12.9 (~28MB) ...
    curl -L -o "!INSTALLER!" "!MIRROR_URL!" --progress-bar
    if !errorlevel! equ 0 (
        echo 下载完成。
        goto :install_python
    )
    echo curl 下载失败，尝试 PowerShell ...
)

:: PowerShell 下载 (带进度条)
echo 正在下载 Python 3.12.9 (~28MB) ...
powershell -Command "$ProgressPreference='Continue'; Invoke-WebRequest -Uri '!MIRROR_URL!' -OutFile '!INSTALLER!' -UseBasicParsing"
if !errorlevel! neq 0 (
    echo.
    echo [错误] 下载失败，请检查网络连接后重试。
    del "!INSTALLER!" >nul 2>&1
    pause
    exit /b 1
)

:install_python
echo.
echo 正在安装 Python 3.12.9 (显示进度条，约需 1-2 分钟)...
"!INSTALLER!" /passive InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=1
if !errorlevel! equ 0 (
    del "!INSTALLER!" >nul 2>&1
    echo.
    echo [OK] Python 安装完成
) else (
    del "!INSTALLER!" >nul 2>&1
    echo.
    echo [警告] 安装程序返回异常代码: !errorlevel!
    echo 请尝试手动安装: https://mirrors.tuna.tsinghua.edu.cn/python/
    pause
    exit /b 1
)

:: 刷新环境变量 PATH
call :refresh_env

:: 重新检测 Python
set "PYTHON="
where python >nul 2>&1 && set "PYTHON=python"
if "!PYTHON!"=="" where py >nul 2>&1 && set "PYTHON=py"
if "!PYTHON!"=="" where python3 >nul 2>&1 && set "PYTHON=python3"

if "!PYTHON!"=="" (
    echo.
    echo [提示] 安装完成但 PATH 暂未生效，可能需要重启计算机。
    echo 重启后重新运行此脚本即可。
    pause
    exit /b 0
)

echo [检测] Python: !PYTHON!

:run_script
echo.
echo ============================================
echo   免责声明
echo ============================================
echo 本脚本素材由 FlyingFishBall 提供，经由 DeepSeek V4 编写，
echo 不排除存在错误与风险，请问是否继续？
echo.
set "CONFIRM="
set /p "CONFIRM=  按回车继续，其他任意键退出..."
if not "!CONFIRM!"=="" goto :exit
echo.
echo ============================================
echo   aTrust 是否已通过自带程序卸载？
echo ============================================
echo 请确保 aTrust 已在"控制面板 - 程序与功能"中正常卸载。
echo 本脚本仅清理卸载后残留的组件，
echo 不可替代官方卸载程序。
echo.
set "CONFIRM2="
set /p "CONFIRM2=  确认已卸载？(y/N): "
if /i not "!CONFIRM2!"=="y" goto :exit
echo.
echo ============================================
echo   启动深信服/aTrust 清理脚本...
echo ============================================
"!PYTHON!" "%~dp0stop_sangfor.py"
if !errorlevel! neq 0 (
    echo.
    echo [错误] 脚本执行异常 (错误码: !errorlevel!)
)
echo.
echo 按任意键退出...
pause >nul
exit /b 0

:refresh_env
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set "SysPath=%%b"
if defined SysPath set "PATH=!SysPath!;!PATH!"
goto :eof

:exit
echo 已取消。
pause >nul
exit /b 0
