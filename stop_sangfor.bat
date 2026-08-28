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
echo [提示] 未检测到 Python 环境，正在扫描本地安装目录...

:: ========== 本地目录兜底扫描 ==========
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%d\python.exe" (
        set "PYTHON=%%d\python.exe"
        echo   [检测] 找到: !PYTHON!
        goto :check_local_python
    )
)
for /d %%d in ("%ProgramFiles%\Python3*") do (
    if exist "%%d\python.exe" (
        set "PYTHON=%%d\python.exe"
        echo   [检测] 找到: !PYTHON!
        goto :check_local_python
    )
)
for /d %%d in ("C:\Python3*") do (
    if exist "%%d\python.exe" (
        set "PYTHON=%%d\python.exe"
        echo   [检测] 找到: !PYTHON!
        goto :check_local_python
    )
)
echo   未在常见目录找到 Python。

:ask_download
echo.
echo 未检测到可用的 Python 环境，请手动安装 Python 3.13.2（地址任选其一）：
echo.
echo   清华源: https://mirrors.tuna.tsinghua.edu.cn/python/3.13.2/python-3.13.2-amd64.exe
echo   官方源: https://www.python.org/ftp/python/3.13.2/python-3.13.2-amd64.exe
echo.
echo 安装时请勾选 "Add python.exe to PATH"，完成后重新运行本脚本。
echo.
choice /c yns /n /m "  [Y] 打开下载页  [N] 退出  [S] 跳过继续（可能无法运行）: "
if !errorlevel! equ 3 (
    echo.
    echo [警告] 跳过 Python 环境检测，若后续报错请先安装 Python 3.7+。
    echo.
    set "PYTHON=python"
    goto :run_script
)
if !errorlevel! equ 2 goto :exit
:: Y → 浏览器打开清华源下载直链
start "" "https://mirrors.tuna.tsinghua.edu.cn/python/3.13.2/python-3.13.2-amd64.exe"
echo.
echo 已在浏览器打开清华源下载地址；若未弹出，请复制上方链接手动下载。
echo 安装完成后重新运行本脚本。
pause
exit /b 0

:check_local_python
"!PYTHON!" -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if !errorlevel! equ 0 goto :run_script
echo   版本低于 3.7，需要安装新版。
set "PYTHON="
goto :ask_download

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

:exit
echo 已取消。
pause >nul
exit /b 0
