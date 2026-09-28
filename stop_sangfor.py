# -*- coding: utf-8 -*-
# Licensed under the MIT License. Copyright (c) 2026 FlyingFishBall
"""
深信服/Sangfor/aTrust 一键清理脚本  v1.4
功能：检测安装 → 弹出卸载 → 停服 → 杀进程 → 删驱动 → 清注册表（含工作空间虚拟盘）
      → 清浏览器策略 → 扫残留（含 DriverStore） → 清除
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


# 注册表根键 → reg.exe 认识的 hive 前缀
HIVE_PREFIX = {
    winreg.HKEY_LOCAL_MACHINE: 'HKLM',
    winreg.HKEY_CURRENT_USER: 'HKCU',
}


def delete_registry_key(hkey_root, subkey_path, label):
    """删除整个注册表键树，返回是否成功。

    优先用 winreg 直接操作；若键下仍有子键导致 DeleteKey 失败，再回退到
    reg delete 并【校验返回码】。

    背景（v1.3 及更早版本的 bug）：
      1. 早期代码把路径拼成 'SOFTWARE\\...\\条目'，**丢了 HKLM/HKCU 根键前缀**。
         微软文档明确要求 reg delete 的 keyname 必须含有效根键，否则命令必然失败。
      2. 早期代码调用后不检查 `run()` 的返回码，无论成败都打印「已清除」，
         造成假成功 —— 用户以为清掉了，实际残留还在。
    """
    hive = HIVE_PREFIX.get(hkey_root)
    if hive is None:
        fail(f"{label}: 未知的注册表根键，已跳过")
        return False

    # 1) 优先 winreg.DeleteKey（键下无子键时可直接删除）
    try:
        winreg.DeleteKey(hkey_root, subkey_path)
        return True
    except FileNotFoundError:
        return True          # 已经不存在，等同于清理成功
    except OSError:
        pass                 # 键下可能还有子键，交给 reg.exe 递归删

    # 2) 回退 reg delete（带完整 hive 前缀 + 校验返回码）
    full = f'{hive}\\{subkey_path}'
    rc, out, err = run(f'reg delete "{full}" /f', timeout=10)
    if rc == 0:
        return True

    text = ((err or '') + (out or '')).lower()
    if 'unable to find' in text or '找不到' in text:
        return True          # 本来就不存在
    fail(f"{label}: 删除失败 — {(err or out or '未知错误').strip()}")
    return False


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

    found = []  # (DisplayName, UninstallString, QuietUninstallString, hkey_root, subkey_name)

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
                                          hkey_root, f'{subkey_path}\\{app_subkey_name}'))
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
    for i, (name, uninst, _, _, _) in enumerate(found, 1):
        print(f"    [{i}] {name}")

    print()
    print("  将依次弹出卸载程序，请在每个卸载窗口中完成操作。")
    print()

    for i, (name, uninst, quiet, hive_root, entry_sub) in enumerate(found, 1):
        print(f"  [{i}/{len(found)}] {name}")
        entry_label = f"{HIVE_PREFIX.get(hive_root, '?')}\\{entry_sub}"

        cmd = uninst or quiet
        if not cmd:
            skip("无法找到卸载命令，将直接删除注册表条目")
            print(f"  正在清除注册表: {entry_label}")
            if delete_registry_key(hive_root, entry_sub, f"注册表条目 {name}"):
                ok(f"已清除注册表条目: {name}")
            continue

        # 从卸载命令中提取exe路径
        exe_path = cmd.strip('"').split('"')[0] if cmd.startswith('"') else cmd.split()[0]
        exe_path = os.path.expandvars(exe_path)

        if not os.path.isfile(exe_path):
            print(f"  卸载程序已被删除: {exe_path}")
            print("  文件已不存在，将直接删除注册表条目")
            print(f"  正在清除注册表: {entry_label}")
            if delete_registry_key(hive_root, entry_sub, f"注册表条目 {name}"):
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

    for name in ['WinDivert', 'SdpVnic', 'aTrustXtun', 'SangforPWEx', 'SfRemoveCallback']:
        run(f'sc stop {name}')
        rc, _, err = run(f'sc delete {name}')
        if rc == 0 or '1060' in (err or ''):
            ok(f"{name} 驱动已删除")
        else:
            # 区分「真的不存在」与「存在但删除失败（占用/权限）」
            rc2, _, _ = run(f'sc qc {name}')
            if rc2 != 0:
                skip(f"{name} 驱动不存在")
            else:
                fail(f"{name} 驱动删除失败: {(err or '').strip()}")
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

    # 附加：工作空间虚拟盘残留（DOS Devices 持久化映射）
    clean_workspace_virtual_drives()

    print()


# ---- 步骤4 附加：工作空间虚拟盘残留 ----

DOS_DEVICES_SUBKEY = r'SYSTEM\CurrentControlSet\Control\Session Manager\DOS Devices'

# 判定虚拟盘是否属于深信服工作空间的路径关键字
WORKSPACE_PATH_HINTS = ('sangfor', 'atrust', 'ingress', 'sfremovecallback')

# DOS Devices 里盘符条目的值形如 \??\C:\path，需先剥掉这层前缀才能当路径用
_DOS_PREFIXES = ('\\??\\', '\\DosDevices\\')


def _strip_dos_prefix(text):
    """剥掉 \\??\\ 或 \\DosDevices\\ 前缀"""
    for prefix in _DOS_PREFIXES:
        if text.upper().startswith(prefix.upper()):
            return text[len(prefix):]
    return text


def classify_dos_entries(entries):
    """把 DOS Devices 条目分成 可疑残留 / 保留 / 需人工确认 三类。

    抽成纯函数是为了可以脱离注册表做单元测试。

    entries: [(name, value), ...]
    返回 (suspicious, kept, manual)
        suspicious: [(name, letter, target, reason), ...]  ← 会清理
        kept:       [(letter, target), ...]               ← 用户自己的合法映射
        manual:     [(letter, target), ...]               ← 指向物理设备，不自动判断
    """
    suspicious, kept, manual = [], [], []

    for name, value in entries:
        clean_name = _strip_dos_prefix(name)
        # 只关心盘符条目；AUX/CON/NUL/PRN/PIPE 等系统设备名一律跳过
        if not re.match(r'^[A-Za-z]:$', clean_name):
            continue

        letter = clean_name.upper()
        target = _strip_dos_prefix(value)

        # 指向物理设备而非文件夹的，不做自动判断
        if target.upper().startswith('\\DEVICE\\'):
            manual.append((letter, target))
            continue

        low = target.lower()
        if any(h in low for h in WORKSPACE_PATH_HINTS):
            suspicious.append((name, letter, target, "目标路径含 Sangfor/aTrust 关键字"))
        elif not os.path.exists(target):
            suspicious.append((name, letter, target, "目标路径已不存在"))
        else:
            kept.append((letter, target))

    return suspicious, kept, manual


def clean_workspace_virtual_drives():
    """清理 aTrust 工作空间遗留在 DOS Devices 下的持久化虚拟盘映射。

    背景：aTrust 的「工作空间」除创建盘符映射外，还会在
        HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\DOS Devices
    下写入形如   M:  ->  \\??\\C:\\...   的持久化条目。
    `subst M: /D` 只能解除【当前登录会话】的映射，删不掉这个注册表键，
    所以重启后 Windows 会照着它把虚拟盘重新造出来。
    必须删除该键下的对应条目才能根治。

    安全策略：只删「盘符格式」且命中以下任一条的条目
        · 目标路径含 Sangfor / aTrust / Ingress 关键字
        · 目标路径已不存在（指向已被清理的目录）
    Windows 自带的设备名条目（AUX / CON / NUL / PRN / PIPE 等）一律不碰，
    用户自己的合法 subst 映射（目标存在且无深信服特征）也一律保留。
    """
    print("  检查工作空间虚拟盘残留 (DOS Devices)...")

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DOS_DEVICES_SUBKEY) as k:
            entries = []
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                i += 1
                entries.append((name, str(value)))
    except FileNotFoundError:
        skip("DOS Devices 键不存在")
        return
    except OSError as e:
        fail(f"读取 DOS Devices 失败: {e}")
        return

    suspicious, kept, manual = classify_dos_entries(entries)
    for letter, target in manual:
        print(f"    {letter} -> {target}  (设备路径，需人工确认，跳过)")
    for letter, target in kept:
        print(f"    {letter} -> {target}  (目标存在且无深信服特征，保留)")

    if not suspicious:
        skip("无虚拟盘残留")
        return

    print(f"  发现 {len(suspicious)} 个疑似工作空间虚拟盘残留：")
    for _, letter, target, reason in suspicious:
        print(f"    {letter} -> {target}")
        print(f"        判据: {reason}")

    print("  正在清除...")
    cleared = 0
    for name, letter, target, _ in suspicious:
        # 先解除当前会话映射（失败不影响后续注册表删除）
        run(f'subst {letter} /D')
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DOS_DEVICES_SUBKEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
            ok(f"虚拟盘 {letter} 残留条目已清除")
            cleared += 1
        except FileNotFoundError:
            ok(f"虚拟盘 {letter} 条目已不存在")
            cleared += 1
        except OSError as e:
            fail(f"虚拟盘 {letter} 清除失败: {e}")

    if cleared:
        print("  提示: 重启后该虚拟盘不会再出现。")


# ============ 步骤5：清理浏览器组策略 ============

# ---- 浏览器策略的注册表位置 ----

# Windows 是 32/64 位双视图（32 位视图实际落在 WOW6432Node 下）。
# 如果 Python 进程是 32 位，访问 SOFTWARE\Policies 会被 WOW64 静默重定向到
# 32 位视图 —— 也就是「以为查的是 64 位视图，其实不是」。显式带上
# KEY_WOW64_64KEY / KEY_WOW64_32KEY 可以消除这种不确定性。
VIEW_64 = getattr(winreg, 'KEY_WOW64_64KEY', 0)
VIEW_32 = getattr(winreg, 'KEY_WOW64_32KEY', 0)

# 32 位 Windows 上没有双视图，WOW64 视图标志会被系统忽略（MSDN：ignored
# by 32-bit Windows），并非报错；此处显式退化为单视图，语义更清晰。
# 注：注册表视图的划分与 CPU 架构无关——x64 与 ARM64 的 Windows 都是
# "64 位原生视图 + WOW6432Node 32 位视图"两个视图，同一套逻辑通用。
_ARCH = (os.environ.get('PROCESSOR_ARCHITEW6432')
         or os.environ.get('PROCESSOR_ARCHITECTURE') or '').upper()
IS_WIN64 = _ARCH in ('AMD64', 'ARM64', 'IA64')

# 元组含义: (根键, 子键路径, 显示名, WOW64 视图标志)
# 浏览器读策略是 HKLM 与 HKCU 都读，因此两个 hive 都要覆盖。
BROWSER_POLICY_TARGETS = [
    (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Policies\Google\Chrome', 'Chrome'),
    (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Policies\Microsoft\Edge', 'Edge'),
    (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Policies\Chromium', 'Chromium'),
    (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Policies\Google\Chrome', 'Chrome（用户级）'),
    (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Policies\Microsoft\Edge', 'Edge（用户级）'),
]
if IS_WIN64:
    # 同一路径分别用 64/32 位视图各查一次
    BROWSER_POLICY_TARGETS = (
        [(h, p, lbl, VIEW_64) for h, p, lbl in BROWSER_POLICY_TARGETS if h == winreg.HKEY_LOCAL_MACHINE]
        + [(h, p, lbl + ' · 32位视图', VIEW_32) for h, p, lbl in BROWSER_POLICY_TARGETS
           if h == winreg.HKEY_LOCAL_MACHINE and 'Chromium' not in p]
        + [(h, p, lbl, 0) for h, p, lbl in BROWSER_POLICY_TARGETS if h == winreg.HKEY_CURRENT_USER]
    )
else:
    BROWSER_POLICY_TARGETS = [(h, p, lbl, 0) for h, p, lbl in BROWSER_POLICY_TARGETS]

# 备份用: (视图标志过滤, reg.exe 路径, 备份文件名)
# 只为「实际存在待清理目标」的根做备份，避免因不存在的键而整体中止
BROWSER_POLICY_BACKUP_ROOTS = [
    (winreg.HKEY_LOCAL_MACHINE, VIEW_64, r'HKLM\SOFTWARE\Policies',
     'browser_policy_backup_HKLM.reg'),
    (winreg.HKEY_CURRENT_USER, 0, r'HKCU\SOFTWARE\Policies',
     'browser_policy_backup_HKCU.reg'),
]
if IS_WIN64:
    BROWSER_POLICY_BACKUP_ROOTS.insert(
        1, (winreg.HKEY_LOCAL_MACHINE, VIEW_32, r'HKLM\SOFTWARE\WOW6432Node\Policies',
            'browser_policy_backup_HKLM32.reg'))

# 判定某个浏览器策略项是否属于深信服注入（匹配其值内容）
POLICY_SANGFOR_MARKERS = (
    'sangfor', 'atrust', 'ingress', 'eaio', 'nac_monitor',
    'sfremovecallback', 'sangforhelpertool', 'sdpvnic', 'eas(y)?connect',
)


def _reg_enum_children(root, path, view=0):
    """枚举注册表键的直接子值与非空子键。

    返回 (values, subkeys)；values 为 [(name, type, data), ...]。
    键不存在或无权限时返回 (None, None)。
    view 为 WOW64 视图标志（VIEW_64 / VIEW_32 / 0）。
    """
    values, subs = [], []
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | view) as k:
            i = 0
            while True:
                try:
                    n, v, t = winreg.EnumValue(k, i)
                except OSError:
                    break
                i += 1
                values.append((n, t, v))
            i = 0
            while True:
                try:
                    subs.append(winreg.EnumKey(k, i))
                except OSError:
                    break
                i += 1
    except OSError:
        return None, None
    return values, subs


def _collect_policy_values(root, path, out, view=0):
    """递归收集策略键下所有叶子值，out += [(key_path, value_name, data)]"""
    values, subs = _reg_enum_children(root, path, view)
    if values is None:
        return
    for n, _, d in values:
        out.append((path, n, d))
    for s in subs:
        _collect_policy_values(root, path + '\\' + s, out, view)


def _policy_value_is_sangfor(data):
    """判断某个策略值的内容是否含深信服特征"""
    if isinstance(data, (list, tuple)):
        text = ' '.join(str(x) for x in data)
    else:
        text = str(data)
    low = text.lower()
    return any(m in low for m in POLICY_SANGFOR_MARKERS)


def _reg_prune_empty(root, path, view=0):
    """自底向上删除空子键（值已被删光的策略项）"""
    values, subs = _reg_enum_children(root, path, view)
    if values is None:
        return
    for s in subs:
        _reg_prune_empty(root, path + '\\' + s, view)

    values, subs = _reg_enum_children(root, path, view)
    if values is not None and not values and not subs:
        try:
            if view:
                winreg.DeleteKeyEx(root, path, view, 0)
            else:
                winreg.DeleteKey(root, path)
        except OSError:
            pass


def clean_browser_policies():
    """清理深信服注入的 Chrome/Edge 组策略，解除「由组织管理」。

    注意：企业 IT 通过组策略下发的合法浏览器策略，与 aTrust 注入的策略
    位于同一个注册表键下（URLBlocklist / ExtensionInstallForcelist /
    ExtensionSettings / ProxySettings 等）。因此【不能整键删除】——
    那会把用户公司下发的合规策略一并抹掉。

    覆盖范围：HKLM 与 HKCU 两个 hive，且 HKLM 在 64 位系统上会分别检查
    64 位与 32 位注册表视图（浏览器两者都读）。

    处理顺序：
      1. 先为「确实存在待清理目标」的根导出 .reg 备份，并打印回滚命令；
         只要有一个必要的备份失败，本步整体跳过，避免删了无法恢复
      2. 只自动删除「值内容含深信服特征字符串」的策略项，并回收空子键
      3. 其余非深信服项列成清单，交由用户确认后才删（默认保留）
    """
    print("[5/8] 清理浏览器组策略")
    print("-" * 40)

    # ---- 0) 找出实际存在的策略键 ----
    present = []                      # (hive, subkey, label, view)
    for hive, sub, label, view in BROWSER_POLICY_TARGETS:
        values, _ = _reg_enum_children(hive, sub, view)
        if values is None:
            skip(f"不存在: {label}")
        else:
            present.append((hive, sub, label, view))

    if not present:
        skip("无需刷新组策略")
        print()
        return

    # ---- 1) 备份：只为实际要动的 hive+视图导出 ----
    needed = set((hive, view) for hive, _, _, view in present)
    backup_files = []
    for hive, view, reg_path, fname in BROWSER_POLICY_BACKUP_ROOTS:
        if (hive, view) not in needed:
            continue
        path = os.path.join(os.getcwd(), fname)
        rc, _, err = run(f'reg export "{reg_path}" "{path}" /y', timeout=30)
        if rc != 0:
            print("  [警告] 策略备份失败，本步整体跳过以免误删后无法恢复")
            print(f"         {reg_path} -> {(err or '').strip()}")
            print()
            return
        backup_files.append((fname, path))

    for fname, path in backup_files:
        ok(f"已备份浏览器策略到: {fname}")
    for fname, path in backup_files:
        print(f"        回滚命令: reg import \"{path}\"")

    # ---- 2) 分类：深信服特征项 vs 其它 ----
    sangfor_items, other_items = [], []   # (hive, key_path, val_name, label, view, preview)
    for hive, sub, label, view in present:
        leaves = []
        _collect_policy_values(hive, sub, leaves, view)
        for key_path, val_name, data in leaves:
            preview = str(data)
            if len(preview) > 60:
                preview = preview[:57] + '...'
            item = (hive, key_path, val_name, label, view, preview)
            if _policy_value_is_sangfor(data):
                sangfor_items.append(item)
            else:
                other_items.append(item)

    # ---- 3) 自动删除深信服特征项 ----
    if sangfor_items:
        print(f"  发现 {len(sangfor_items)} 项深信服注入策略，正在清除：")
        for hive, key_path, val_name, label, view, preview in sangfor_items:
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE | view) as k:
                    winreg.DeleteValue(k, val_name)
                ok(f"[{label}] 已删除 {val_name}  ({preview})")
            except FileNotFoundError:
                pass
            except OSError as e:
                fail(f"[{label}] 删除 {val_name} 失败: {e}")

        # 值删光后，把空掉的策略子键一并回收
        for hive, sub, _, view in present:
            _reg_prune_empty(hive, sub, view)
    else:
        skip("未发现深信服注入的浏览器策略")

    # ---- 4) 其余策略交由用户判断 ----
    if other_items:
        print()
        print(f"  另发现 {len(other_items)} 项【非深信服特征】的浏览器策略：")
        for hive, key_path, val_name, label, view, preview in other_items:
            short = key_path.split('Policies\\')[-1]
            print(f"    [{label}] {short}\\{val_name} = {preview}")
        print()
        print("  这些可能是贵单位 IT 通过组策略下发的合规要求，本脚本不会自动删除。")
        print("  可在浏览器地址栏访问 chrome://policy 或 edge://policy 查看它们的实际作用。")
        print("  确认是残留、希望一并清除的，才输入 y。")
        try:
            ans = input("  是否一并删除以上策略？(y=删除 / 其它=保留): ").strip().lower()
        except EOFError:
            ans = ''
        if ans == 'y':
            for hive, key_path, val_name, label, view, _ in other_items:
                try:
                    with winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE | view) as k:
                        winreg.DeleteValue(k, val_name)
                    ok(f"[{label}] 已删除 {val_name}")
                except FileNotFoundError:
                    pass
                except OSError as e:
                    fail(f"[{label}] 删除 {val_name} 失败: {e}")
            for hive, sub, _, view in present:
                _reg_prune_empty(hive, sub, view)
        else:
            skip("已保留以上策略（未做改动）")

    # ---- 5) 刷新策略 ----
    if sangfor_items or other_items:
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


def _firewall_delete_verdict(rc, out, err):
    """判断 netsh advfirewall firewall delete rule 的结果。

    返回 'ok'（删了规则）/ 'skip'（本无匹配规则，机器已干净）/ 'fail'（真错误）。

    背景：netsh 在【没有匹配规则】时打印 "No rules match the specified
    criteria."（中文系统为"没有与指定条件匹配的规则"）并返回退出码 1 ——
    这不是错误，恰恰是干净状态。此前只认 rc==0，导致干净机器反而报
    [失败]。（v1.3 PR #1 审查时已指出，此处正式修复）
    """
    text = f"{out}\n{err}".lower()
    if "no rules" in text or "没有" in text or "不匹配" in text:
        return "skip"
    if rc == 0:
        return "ok"
    return "fail"


def clean_stale_firewall_rules():
    """Remove firewall rules that reference deleted Sangfor executables."""
    print("  清理 Sangfor 残留防火墙规则...")
    for program in STALE_FIREWALL_PROGRAMS:
        # netsh matches the exact application path and leaves unrelated rules intact.
        rc, out, err = run(
            f'netsh advfirewall firewall delete rule name=all program="{program}"',
            timeout=15,
        )
        verdict = _firewall_delete_verdict(rc, out, err)
        if verdict == "skip":
            skip(f"无残留防火墙规则: {program}")
        elif verdict == "ok":
            ok(f"已清理防火墙规则: {program}")
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
