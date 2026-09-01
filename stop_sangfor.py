# -*- coding: utf-8 -*-
# Licensed under the MIT License. Copyright (c) 2026 FlyingFishBall
"""
深信服/Sangfor/aTrust 一键清理脚本
功能：检测安装 → 弹出卸载 → 停服 → 杀进程 → 删驱动 → 清注册表 → 清浏览器策略 → 扫残留（含 DriverStore） → 清除
需以管理员身份运行
"""
import subprocess
import os
import sys
import shutil
import tempfile
import re
import ctypes
import time
import winreg

# 确保控制台 UTF-8 输出，兼容非中文 Windows
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ============ 工具函数 ============

def run(cmd, timeout=15):
    r = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=timeout,
                       encoding='utf-8', errors='replace')
    return r.returncode, r.stdout, r.stderr

def is_admin():
    try:
        return subprocess.run('net session', capture_output=True, shell=True, timeout=5).returncode == 0
    except:
        return False

def ok(msg):
    print(f"  [OK]   {msg}")

def fail(msg):
    print(f"  [失败] {msg}")

def skip(msg):
    print(f"  [跳过] {msg}")


# ============ 步骤0：检测并弹出卸载 ============

SANGFOR_UNINSTALL_KW = re.compile(
    r'sangfor|深信服|\batrust\b|ingress|eas(y)?connect|eaio',
    re.I,
)

# 卸载注册表根路径: (hkey_root, subkey_path)
UNINSTALL_REG_ROOTS = [
    (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
    (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'),
    (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
]


def auto_uninstall():
    """扫描卸载注册表，发现深信服相关程序则自动弹出卸载"""
    print("[0/8] 检测已安装的深信服/Ingress/aTrust 程序")
    print("-" * 40)

    found = []  # (DisplayName, UninstallString, QuietUninstallString, subkey_path)

    for hkey_root, subkey_path in UNINSTALL_REG_ROOTS:
        try:
            with winreg.OpenKey(hkey_root, subkey_path) as root_key:
                i = 0
                while True:
                    try:
                        app_subkey_name = winreg.EnumKey(root_key, i)
                    except OSError:
                        break

                    try:
                        with winreg.OpenKey(root_key, app_subkey_name) as app_key:
                            try:
                                display_name = winreg.QueryValueEx(app_key, 'DisplayName')[0]
                            except FileNotFoundError:
                                i += 1
                                continue

                            if not display_name or not SANGFOR_UNINSTALL_KW.search(display_name):
                                i += 1
                                continue

                            uninstall_str = ''
                            quiet_str = ''
                            try:
                                uninstall_str = winreg.QueryValueEx(app_key, 'UninstallString')[0]
                            except FileNotFoundError:
                                pass
                            try:
                                quiet_str = winreg.QueryValueEx(app_key, 'QuietUninstallString')[0]
                            except FileNotFoundError:
                                pass

                            found.append((display_name, uninstall_str, quiet_str,
                                          f'{subkey_path}\\{app_subkey_name}'))
                    except FileNotFoundError:
                        pass

                    i += 1
        except FileNotFoundError:
            continue

    if not found:
        skip("未检测到已安装的深信服/Ingress/aTrust 程序")
        print()
        return

    print(f"  发现 {len(found)} 个相关程序：")
    for i, (name, uninst, _, _) in enumerate(found, 1):
        print(f"    [{i}] {name}")

    print()
    print("  将依次弹出卸载程序，请在每个卸载窗口中完成操作。")
    print()

    for i, (name, uninst, quiet, key) in enumerate(found, 1):
        print(f"  [{i}/{len(found)}] {name}")

        cmd = uninst or quiet
        if not cmd:
            skip(f"无法找到卸载命令，将直接删除注册表条目")
            print(f"  正在清除注册表: {key}")
            run(f'reg delete "{key}" /f', timeout=5)
            ok(f"已清除注册表条目: {name}")
            continue

        # 从卸载命令中提取exe路径
        exe_path = cmd.strip('"').split('"')[0] if cmd.startswith('"') else cmd.split()[0]
        exe_path = os.path.expandvars(exe_path)

        if not os.path.isfile(exe_path):
            print(f"  卸载程序已被删除: {exe_path}")
            print(f"  文件已不存在，将直接删除注册表条目")
            run(f'reg delete "{key}" /f', timeout=5)
            ok(f"已清除注册表条目: {name}")
            continue

        print(f"  正在启动卸载程序...")
        # 使用 Popen 不捕获输出，让 GUI 正常显示
        work_dir = os.path.dirname(exe_path)
        subprocess.Popen(cmd, shell=True, cwd=work_dir)

        # 等待用户完成
        if i < len(found):
            input(f"  完成 '{name}' 的卸载后按 Enter 继续下一个...")
        else:
            input(f"  完成 '{name}' 的卸载后按 Enter 继续清理...")

    print()


# ============ 步骤1：停服 & 删服务 ============

KNOWN_SERVICES = [
    "eaio_service",
    "nac_monitor",
    "IngressMgr",
    # EasyConnect/aTrust helper and protection components
    "SangforSP",
    "SangforPWEx",
    "SfRemoveCallback",
]

def stop_and_delete_services():
    print("[1/8] 停止并删除已知服务")
    print("-" * 40)
    for name in KNOWN_SERVICES:
        run(f'sc stop {name}')
        rc, out, err = run(f'sc delete {name}')
        if rc == 0 or '1060' in (err or ''):
            ok(f"服务 {name} 已删除")
        else:
            rc2, _, _ = run(f'sc qc {name}')
            if rc2 != 0:
                ok(f"服务 {name} 不存在/已删除")
            else:
                fail(f"服务 {name}: {err.strip()}")
    print()


# ============ 步骤2：杀残留进程 ============

KNOWN_PROCS = [
    "eaio_service.exe", "eaio_agent.exe",
    "nac_monitor.exe", "nac_agent.exe",
    "IngressMgr.exe", "Ingress.exe",
    "SangforCSClient.exe", "SangforPromote.exe",
    "SangforPromoteService.exe", "SangforServiceClient.exe",
]

def kill_known_processes():
    print("[2/8] 终止已知进程")
    print("-" * 40)
    for name in KNOWN_PROCS:
        rc, out, _ = run(f'taskkill /f /im {name}')
        if rc == 0:
            ok(f"终止 {name}")
    print()


# ============ 步骤3：清理关键驱动 ============

def clean_critical_drivers():
    print("[3/8] 清理内核驱动")
    print("-" * 40)

    # WinDivert
    run('sc stop WinDivert')
    rc, _, _ = run('sc delete WinDivert')
    if rc == 0:
        ok("WinDivert 驱动已删除")
    else:
        skip("WinDivert 驱动不存在")

    # SdpVnic + aTrustXtun
    for name in ['SdpVnic', 'aTrustXtun', 'SangforPWEx', 'SfRemoveCallback']:
        run(f'sc stop {name}')
        rc, _, _ = run(f'sc delete {name}')
        if rc == 0:
            ok(f"{name} 驱动已删除")
        else:
            skip(f"{name} 驱动不存在")
    print()


# ============ 步骤4：清理注册表 ============

SANGFOR_REGISTRY_KEYS = [
    # Ingress / aTrust 安装配置
    r'HKLM\SOFTWARE\WOW6432Node\Sangfor',
    r'HKLM\SOFTWARE\Sangfor',
    r'HKCU\SOFTWARE\Sangfor',
    # Ingress Manager 事件日志
    r'HKLM\SYSTEM\CurrentControlSet\Services\EventLog\Application\Ingress Manager',
]


def clean_sangfor_registry():
    """删除深信服/Ingress/aTrust 注册表残留"""
    print("[4/8] 清理注册表")
    print("-" * 40)

    # 先递归列出子键备用
    for key in SANGFOR_REGISTRY_KEYS:
        # 先查子键
        rc, out, _ = run(f'reg query "{key}" /s', timeout=5)
        if rc != 0:
            skip(f"不存在: {key}")
            continue

        # 删除整个键树
        rc_del, _, err_del = run(f'reg delete "{key}" /f', timeout=10)
        if rc_del == 0 or 'unable to find' in (err_del or '').lower():
            ok(f"已删除: {key}")
        else:
            fail(f"删除失败: {key} — {err_del.strip() if err_del else '未知错误'}")

    # 额外扫描 HKLM\SYSTEM\CurrentControlSet\Services 中残留的深信服子键（EventLog 等）
    print("  扫描 Services 注册表残留...")
    rc, out, _ = run(
        r'reg query HKLM\SYSTEM\CurrentControlSet\Services /s /f Sangfor /k',
        timeout=10,
    )
    if rc == 0 and out:
        found_keys = []
        for l in out.splitlines():
            l = l.strip()
            if l and not l.startswith('HKEY_LOCAL_MACHINE') and not l.startswith('搜索结束'):
                # reg query /s /f 的输出格式包含完整路径
                if 'HKEY_LOCAL_MACHINE\\' in l:
                    found_keys.append(l)
                elif l.startswith('HKEY_'):
                    found_keys.append(l)
        
        # Also try get the exact matches
        for l in out.splitlines():
            m = re.search(
                r'(HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services\\[^\n]+)',
                l,
            )
            if m:
                k = m.group(1).strip()
                if k not in found_keys:
                    found_keys.append(k)

        for fk in found_keys:
            if fk in SANGFOR_REGISTRY_KEYS:
                continue
            print(f"  发现残留注册表: {fk}")
            rc_del, _, err_del = run(f'reg delete "{fk}" /f', timeout=5)
            if rc_del == 0:
                ok(f"已删除: {fk}")
            else:
                fail(f"删除失败: {fk}")
    else:
        skip("Services 下无 Sangfor 残留")

    print()


# ============ 步骤5：清理浏览器组策略 ============

def clean_browser_policies():
    """删除深信服注入的 Chrome/Edge 组策略，解除「由组织管理」"""
    print("[5/8] 清理浏览器组策略")
    print("-" * 40)

    browser_policy_keys = [
        r'HKLM\SOFTWARE\Policies\Google\Chrome',
        r'HKLM\SOFTWARE\Policies\Microsoft\Edge',
        r'HKLM\SOFTWARE\Policies\Chromium',
    ]

    deleted_any = False
    for key in browser_policy_keys:
        rc, _, err = run(f'reg delete "{key}" /f', timeout=5)
        if rc == 0:
            ok(f"已删除: {key}")
            deleted_any = True
        elif 'unable to find' in (err or '').lower() or rc == 1:
            skip(f"不存在: {key}")
        else:
            fail(f"删除失败: {key}")

    if deleted_any:
        print("  正在刷新组策略...")
        rc, _, _ = run('gpupdate /force', timeout=30)
        if rc == 0:
            ok("组策略已刷新，Chrome/Edge 重启后'由组织管理'将消失")
        else:
            fail("组策略刷新失败，请手动执行: gpupdate /force")
    else:
        skip("无需刷新组策略")

    print()


# ============ 步骤6：搜索残留 ============

KW = re.compile(
    r'sangfor|深信服|\batrust|ingress|eas(y)?connect|'
    r'eaio|nac_monitor|nac_agent|sdpvnic|'
    r'\b(a|X)trust.*xtun|windivert|sfremove|sangforhelpertool',
    re.I,
)

# Rules left behind by Sangfor's service client after an incomplete uninstall.
# They are removed only when they point to this exact, known stale executable.
STALE_FIREWALL_PROGRAMS = [
    r'C:\Program Files (x86)\Sangfor\SSL\SangforServiceClient\SangforServiceClient.exe',
]


def scan_all():
    """动态扫描所有残留，返回分类列表"""
    print("[6/8] 扫描残留...")
    print("-" * 40)
    results = {
        'services': [],
        'drivers': [],
        'driver_files': [],
        'driver_packages': [],
        'files': [],
    }

    # --- 5a. 扫描服务 ---
    _, out, _ = run('sc query type= all state= all')
    for name in KNOWN_SERVICES + ['WinDivert', 'SdpVnic', 'aTrustXtun']:
        if f'SERVICE_NAME: {name}' in out:
            results['services'].append(name)
            print(f"  发现服务: {name}")

    # 额外扫描注册表中可能遗留的深信服服务
    _, out, _ = run(
        r'reg query HKLM\SYSTEM\CurrentControlSet\Services /s /f Sangfor /k',
        timeout=10,
    )
    for l in out.splitlines():
        m = re.search(r'Services\\([^\\]+)', l)
        if m and m.group(1) not in results['services']:
            name = m.group(1)
            _, s, _ = run(f'sc qc {name} 2>&1')
            if KW.search(s):
                results['services'].append(name)
                print(f"  发现服务: {name}")

    # --- 5b. 扫描驱动文件 ---
    sysroot = os.environ.get('SystemRoot', r'C:\Windows')
    for d in [
        os.path.join(sysroot, r'System32\drivers'),
        os.path.join(sysroot, r'SysWOW64\drivers'),
    ]:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if KW.search(f):
                results['driver_files'].append(os.path.join(d, f))
                print(f"  发现驱动: {os.path.join(d, f)}")

    # --- 5c. 扫描驱动包 (DriverStore) ---
    repo = os.path.join(sysroot, r'System32\DriverStore\FileRepository')
    if os.path.isdir(repo):
        for d in os.listdir(repo):
            if KW.search(d):
                dp = os.path.join(repo, d)
                if os.path.isdir(dp):
                    for f in os.listdir(dp):
                        if f.lower().endswith('.inf') and KW.search(f):
                            inf_path = os.path.join(dp, f)
                            results['driver_packages'].append(inf_path)
                            print(f"  发现驱动包: {inf_path}")

    # --- 5d. 扫描文件残留 ---
    search_roots = [
        os.environ.get('ProgramFiles', r'C:\Program Files'),
        os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
        os.environ.get('ProgramData', r'C:\ProgramData'),
        tempfile.gettempdir(),
        os.path.expandvars(r'%LOCALAPPDATA%'),
        os.path.expandvars(r'%APPDATA%'),
        # SYSTEM 账户残留 & 预取缓存
        os.path.join(sysroot, r'System32\config\systemprofile'),
        os.path.join(sysroot, r'SysWOW64\config\systemprofile'),
        os.path.join(sysroot, r'prefetch'),
    ]
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                depth = dirpath[len(root):].count(os.sep)
                if depth > 3:
                    dirnames.clear()
                    continue
                for name in filenames + dirnames:
                    if KW.search(name):
                        fp = os.path.join(dirpath, name)
                        # 排除 Revo 备份
                        if 'revo' in dirpath.lower():
                            continue
                        results['files'].append(fp)
                        print(f"  发现文件: {fp}")
        except PermissionError:
            continue

    # 去重
    results['files'] = list(set(results['files']))
    total = (
        len(results['services'])
        + len(results['driver_files'])
        + len(results['driver_packages'])
        + len(results['files'])
    )
    print(f"\n  扫描完毕，共发现 {total} 项残留")
    return results


# ============ 步骤7：清除残留 ============

def delete_service(name):
    run(f'sc stop {name}')
    rc, _, err = run(f'sc delete {name}')
    return rc == 0 or '1060' in (err or '')


def delete_path(path):
    if not os.path.exists(path):
        return True
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        else:
            shutil.rmtree(path)
        return True
    except:
        # 文件被占用，尝试标记为重启后删除
        try:
            MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
            if os.name == 'nt' and ctypes.windll.kernel32.MoveFileExW(
                path, None, MOVEFILE_DELAY_UNTIL_REBOOT
            ):
                return 'reboot'
        except:
            pass
        return False


def clean_stale_firewall_rules():
    """Remove firewall rules that reference deleted Sangfor executables."""
    print("  清理 Sangfor 残留防火墙规则...")
    for program in STALE_FIREWALL_PROGRAMS:
        # netsh matches the exact application path and leaves unrelated rules intact.
        rc, out, err = run(
            f'netsh advfirewall firewall delete rule name=all program="{program}"',
            timeout=15,
        )
        text = f"{out}\n{err}".lower()
        if rc == 0 and ("deleted" in text or "删除" in text or "no rules" in text or "没有" in text):
            ok(f"已清理防火墙规则: {program}")
        elif rc == 0:
            ok(f"已处理防火墙规则: {program}")
        else:
            fail(f"防火墙规则清理失败: {program} — {err.strip() or out.strip()}")


def clean_all(results):
    print("[7/8] 清理残留")
    print("-" * 40)

    total = 0
    ok_count = 0

    clean_stale_firewall_rules()

    for name in results['services']:
        total += 1
        if delete_service(name):
            ok(f"删除服务 {name}")
            ok_count += 1
        else:
            fail(f"删除服务 {name}")

    for path in results['driver_files']:
        total += 1
        result = delete_path(path)
        if result == True:
            ok(f"删除 {os.path.basename(path)}")
            ok_count += 1
        elif result == 'reboot':
            ok(f"已标记重启后删除: {os.path.basename(path)}")
            ok_count += 1
        else:
            fail(f"删除 {os.path.basename(path)}")

    for inf_path in results['driver_packages']:
        total += 1
        print(f"  卸载驱动包: {os.path.basename(inf_path)} ...")
        rc, out, _ = run(
            f'pnputil /delete-driver "{inf_path}" /uninstall /force',
            timeout=30,
        )
        if rc == 0:
            ok(f"卸载驱动包 {os.path.basename(inf_path)}")
            ok_count += 1
        else:
            fail(f"卸载驱动包 {os.path.basename(inf_path)}")
            if out:
                print(f"      输出: {out.strip()}")

    for path in results['files']:
        total += 1
        result = delete_path(path)
        if result == True:
            ok(f"删除 {path}")
            ok_count += 1
        elif result == 'reboot':
            ok(f"已标记重启后删除: {path}")
            ok_count += 1
        else:
            fail(f"删除 {path}")

    print(f"\n  结果: {ok_count}/{total} 项成功删除")
    if ok_count < total:
        print("  提示: 失败项可能需要重启后手动删除或已被占用")


# ============ 小彩蛋 ============

def fireworks():
    """小烟花庆祝动画 — 3发连射"""
    colors = [
        '\033[91m',  # 红
        '\033[93m',  # 黄
        '\033[95m',  # 紫
        '\033[96m',  # 青
        '\033[92m',  # 绿
        '\033[94m',  # 蓝
    ]
    reset = '\033[0m'
    rng = __import__('random')

    # 3 组烟花图案
    bursts = [
        ['  ✨  ', ' ✨✨ ', '✨✨✨', ' ✨✨ ', '  ✨  '],
        ['   🎆   ', '  🎆🎆  ', ' 🎆🎆🎆 ', '🎆🎆🎆🎆🎆', ' 🎆🎆🎆 ', '  🎆🎆  ', '   🎆   '],
        ['   🌟   ', '  🌟🌟  ', ' 🌟🌟🌟 ', '🌟🌟🌟🌟🌟', ' 🌟🌟🌟 ', '  🌟🌟  ', '   🌟   '],
        ['  💥  ', ' 💥💥 ', '💥💥💥', ' 💥💥 ', '  💥  '],
        ['   🎉   ', '  🎉🎉  ', ' 🎉🎉🎉 ', '🎉🎉🎉🎉🎉', ' 🎉🎉🎉 ', '  🎉🎉  ', '   🎉   '],
    ]

    for i in range(3):
        pattern = rng.choice(bursts)
        color = rng.choice(colors)
        pad = ' ' * rng.randint(10, 35)

        for line in pattern:
            print(f'{pad}{color}{line}{reset}')
            time.sleep(0.06)

        if i < 2:
            time.sleep(0.15)

    print()


# ============ 入口 ============

def main():
    print("=" * 55)
    print("  深信服 / Sangfor / aTrust 一键清理脚本")
    print("=" * 55)
    print()

    if not is_admin():
        print("[错误] 请以管理员身份运行此脚本！")
        input("按 Enter 退出...")
        sys.exit(1)

    auto_uninstall()
    stop_and_delete_services()
    kill_known_processes()
    clean_critical_drivers()
    clean_sangfor_registry()
    clean_browser_policies()
    results = scan_all()
    print()
    clean_all(results)

    print()
    print("  全部完成。")
    print()
    print("  ꒰ঌ(🎀 ᗜ` ˰ ´ᗜ 🌸)໒꒱💈❌")
    print()
    # fireworks()  — ANSI 颜色终端兼容性不佳，暂时关闭

    # 重建 Windows 搜索索引选项
    print()
    choice = input("是否重建 Windows 搜索索引？(y=重建, 其他=退出): ").strip().lower()
    if choice == 'y':
        progdata = os.environ.get('ProgramData', r'C:\ProgramData')
        idx_path = os.path.join(
            progdata,
            r'Microsoft\Search\Data\Applications\Windows\Windows.edb',
        )

        # 确保服务启动类型为自动（防止被禁用后 start 失败）
        run('sc config WSearch start= auto')

        # 停止服务
        print("正在停止搜索服务...")
        rc, _, _ = run('sc stop WSearch', timeout=30)
        if rc == 0:
            time.sleep(2)  # 等待服务完全停止

        # 删除索引数据库
        if os.path.isfile(idx_path):
            try:
                os.remove(idx_path)
                print(f"  已删除索引数据库")
            except PermissionError:
                print("  索引数据库被占用，未能删除（请重启后重试）")
            except Exception as e:
                print(f"  删除失败: {e}")
        else:
            print("  索引数据库不存在，跳过")

        # 启动服务
        print("正在启动搜索服务...")
        rc2, _, _ = run('sc start WSearch', timeout=10)
        if rc2 == 0:
            print("索引重建已触发，系统将在后台自动完成。")
        else:
            print(f"  搜索服务启动失败 (错误码: {rc2})，请手动执行: sc start WSearch")



if __name__ == '__main__':
    main()
