# Shark User Manual

Shark uses Stellar or Shizuku to drive the device-side 98260 exploit as shell, load the selected manager's LKM, and provide temporary root access. Grant permission before the first run.

> Shark currently supports Oplus-family devices with kernel releases 6.18.21, 6.12.69, 6.12.38, 6.12.58, 6.12.23, and 6.6.118. Matching uses the complete `uname -r`; unsupported builds are rejected.

## Quick start

1. Install the selected root manager (KernelSU / FinaSU / KernelSU Next / BakaSU / SukiSU Ultra). CI builds of KernelSU Next are not currently supported.
2. Activate Stellar (recommended) or Shizuku using wireless debugging or ADB, then grant Shark permission.
3. On Shark's home screen, tap **Run root exploit**. Wait for `DONE`, `SU_ID_RC=0`, and `uid=0(root)`.
4. After root is confirmed, Shark performs one userspace reboot to enable modules. The circuit breaker protects against a boot loop by removing Shark-related modules if the reboot does not reach a stable boot.
5. If the log reports **MODULE NOT LOADED**, run the exploit again after the device is available.
6. Shark checks for updates when opened. Gitee Releases is tried first, followed by GitHub; updates can be downloaded and handed to the system installer.

## Permissions and preparation

- **Stellar first, Shizuku fallback:** Stellar is preferred when both services are available.
- **Install the manager first:** `ksud` is executed from the installed manager APK's `lib/arm64` directory.
- **Use a clean boot when possible:** each supported kernel release has its own entry point and is matched exactly.

## Root flow

**preflight** (kernel release / trace channel) → **98260 UAF** (fake cred / SELinux zero-write) → **one-shot `ksud late-load`** → wait for the module and `su` → **cleanup** (manager installation, guard unloading, SUSFS, VFS, screenshot restore, and manager launch).

Each kernel release has its own K source and `libk<release>.so`; the shared engine is in `plant_core.inc`.

- The fast path takes about 2–3 seconds; the full flow usually takes 4–9 seconds.
- After a failed chain, the plant hands its pages to a holder, so the exploit can be retried in the same boot. Do not manually kill or reap the holder.

## Features

- **Home:** root-manager selection, flow switches, kernel information, and the automatically selected exploit.
- **Logs:** live output for the current run.
- **History:** each run is saved as a `.log`; tap an entry to read it, or swipe left to export it.
- **About:** version information, update checking, source/community/issue links, and dependency licenses.
- **Extras → Droidspaces:** on 6.18.21, download the latest `Droidspaces-LKM` release to `Download/Shark/`, then install it from KernelSU → Modules.
- **Dynamic Switching:** on supported 6.18/6.12 builds, load the universal KSU LKM once after a clean boot and switch between installed managers without another exploit run.

## Troubleshooting

| Log | Action |
| --- | --- |
| `PROBE_FAIL` / `kernel mismatch` | The exact kernel release is not supported. |
| `MANAGER` / `KSUD_MISSING` | Install the selected manager APK and try again. |
| `STALE_PLANT` | Wait for the previous plant to become a holder, then retry. |
| `PLANT_FAIL` | The holder is retained; retry in the same boot. |
| `LATE_LOAD_FAIL` | Inspect the `ksud` output and verify the manager version. |
| Kernel crash/reboot | This is an inherent risk of the 98260 race. After reboot, run the flow again. |

## Runtime details

- All entry points run directly from the app's native library directory.
- Child-process `cwd`, `HOME`, and `TMPDIR` remain under the app's files directory.
- No tools are deployed to `/data/local/tmp`; `ksud` is executed from the installed manager APK.
- SUSFS is supported on the 6.18/6.12 lines; VFS is available only on the 6.18 entry point.
- Use only on devices you own and understand.
