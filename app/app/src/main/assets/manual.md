# Shark User Manual

Shark uses Stellar or Shizuku as shell to drive the device-side 98260 exploit and load the manager LKM. Complete authorization first, then one-tap jailbreak.

> Shark currently supports OnePlus/OPPO/Realme/iQOO devices with kernels 6.18.21, 6.12.69, 6.12.38, 6.12.58, 6.12.23 and 6.6.118, matched by exact `uname -r`. Unsupported devices will be prompted.

## Quick Start

1. Install the selected ROOT manager (KernelSU / FinaSU / KernelSU Next / BakaSU / SukiSU Ultra). CI versions of KernelSU Next are not supported yet.
2. Start and activate **Stellar (recommended)** or **Shizuku** via wireless debugging or adb, and grant Shark permission.
3. Return to Shark home and tap "One-Tap Jailbreak". Wait for success logs: `DONE`, `SU_ID_RC=0` and `uid=0(root)`.
4. After success the manager is launched automatically. When corresponding switches are on, security popups are disabled, **SUSFS** (6.18/6.12; 6.12 uses `libsusfs_guard_lkm_612.so`) or **VFS** (6.18.21 only) is loaded.
5. If the log shows **MODULE NOT LOADED**, no reboot is needed — just retry the jailbreak.
6. The app checks for updates on every launch (Gitee first, GitHub fallback). New versions show a dialog; you can download and hand to the system installer. Manual check is available on the About page.

## Permissions & Preparation

- **Stellar preferred, Shizuku fallback**: Stellar is used when both are available.
- **Manager must be installed first**: ksud is not bundled; it is executed in-place from the manager APK's `lib/arm64`.
- **Recommended after a clean boot**. Each kernel has its own entry; the app selects by exact `uname -r`.

## One-Tap Jailbreak Flow

**preflight** (kernel release / trace channel) → **98260 UAF** (fake cred / SELinux zero-write) → **cred child one-shot ksud late-load** → wait for module & su → **finish** (ksud install, unload kernel guard, SUSFS, VFS, screenshot restore, launch manager).

Each kernel version has its own K source and `libk<version>.so`. Shared engine is in `plant_core.inc`. Vivo devices (6.12.23 / 6.12.58 vivo builds) zero the `__tracepoint_sys_exit->funcs` slot used by `vr.ko` before waking the root child.

- Fast path: plant ~2–3 s, full flow ~4–9 s. Recycle misses add a few seconds — normal.
- After any chain failure: plant keeps the holder; same boot can retry immediately. Do not manually kill or reap the holder.

## Features

- **Home**: ROOT manager dropdown, flow switches (VFS only on 6.18; vivo V2505A hides anti-root items; 6.6.118 hides SUSFS/VFS/hot-switch); info card shows kernel version and auto-selected exploit.
- **Logs**: Real-time streaming log of the current run.
- **History**: Each run saves a `.log`; tap to view full text, swipe left to export/share.
- **About**: Version, check update, source code / community / feedback, AboutLibraries dependency list (with versions and licenses), and offline-bundled open source license texts (GPL-3.0, NOTICE, Apache-2.0, MIT, GPL-2.0, MPL-2.0).
- **Extra Features → Droidspaces Support** (6.18.21 only): Tap "Download Module" to fetch the latest `Droidspaces-LKM` release from GitHub, download the zip to `Download/Shark/`, then flash it in KernelSU Manager → Modules → Install. Module is not bundled in the APK.
- **ROOT Manager → Dynamic Switching** (6.18.21 / 6.12.69 / 6.12.38 / 6.12.58 / 6.12.23; not 6.6.118): First clean boot loads the universal KSU LKM via `libksud_universal.so` (initial KernelSU). After load, Extra Features shows "Manager Hot Switch" to switch between KernelSU / KernelSU-Next / BakaSU / SukiSU / FinaSU without reboot or re-jailbreak. Target manager is re-opened after switch.

## Error Handling

| Log | Action |
| --- | --- |
| `PROBE_FAIL` / `kernel mismatch` | Current kernel not in supported list (exact `uname -r` match required for 6.18.21 / 6.12.69 / 6.12.38 / 6.12.58 / 6.12.23 / 6.6.118). |
| `MANAGER` / `KSUD_MISSING` | Install the corresponding manager APK first. |
| `STALE_PLANT` | Previous plant still running; wait for it to become holder then retry. |
| `PLANT_FAIL` | Plant keeps holder and exits; same boot can retry directly. |
| `LATE_LOAD_FAIL` | Module did not appear in time; check ksud output in log, confirm manager version, then retry. |
| Kernel crash / reboot | Inherent risk of 98260 race; reboot and retry. |

## Runtime

- **6.18.21** → `libk61821.so`; **6.12.69** → `libk61269.so` (two OTA builds selected by uname).
- **6.12.38 (PLR110)** → `libk61238.so`; **6.12.58 (PLZ110 / V2505A OS6/OS7)** → `libk61258.so`; **6.12.23 (V2505A)** → `libk61223.so`.
- **6.6.118 (PKJ110 / PKH110 / Pad etc.)** → `libk66118.so` (two OTA builds by uname); KMI android15-6.6.
- All matched by **exact `uname -r`**. Unmatched devices show "not supported" on One-Tap Jailbreak.
- All entries run in-place from the app's native library dir. Child cwd/HOME/TMPDIR are under app filesDir; nothing is deployed to `/data/local/tmp`. ksud is executed from the installed manager APK. SUSFS supported on 6.18/6.12 (6.12 uses `libsusfs_guard_lkm_612.so`); 6.6.118 does not. VFS switch only for 6.18.
- For research on your own devices only.
