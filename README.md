<h1 align="center"><img src="docs/images/app-icon.png" width="56" height="56" align="absmiddle" alt="Shark"> Shark</h1>

<p align="center"><b>Temporary root and root-manager switching for supported Android devices</b></p>

Shark uses Stellar or Shizuku to drive the device-side CVE-2026-98260 exploit, load a selected root manager LKM, and provide a temporary KernelSU-compatible root environment without unlocking the bootloader.

## Supported kernels

The app matches the complete `uname -r` and currently supports:

- Android 17 / kernel 6.18.21
- Android 16 / kernels 6.12.69, 6.12.58, 6.12.38, and 6.12.23
- Android 15 / kernel 6.6.118

Supported root managers are KernelSU, KernelSU Next, BakaSU, SukiSU Ultra, and FinaSU. The manager APK must be installed separately; Shark executes that APK's `ksud`.

## Features

- One-tap temporary root with automatic exploit selection.
- Optional SUSFS, VFS, anti-root guard, and kernel-security-guard controls.
- Dynamic manager switching on supported 6.18/6.12 builds.
- Live logs and durable run history.
- Online APK updates with SHA-256 and signing-certificate verification.
- Droidspaces module download support on 6.18.21.
- One userspace reboot after root confirmation to enable modules.
- A boot-loop circuit breaker that removes only Shark-related module directories after an unsuccessful reboot.

## Root flow

1. Install the desired root manager APK.
2. Start Stellar or Shizuku and grant Shark permission.
3. Select a manager or Dynamic Switching.
4. Tap **Run root exploit** and wait for `DONE`, `SU_ID_RC=0`, and `uid=0(root)`.
5. Shark arms the recovery hook, confirms root, and performs one userspace reboot to enable modules.

The recovery hook is stored in `/data/adb/service.d/shark-circuit-breaker.sh`. It marks the boot as stable when `sys.boot_completed=1`; if the next boot fails before stability, it removes only module directories whose names identify Shark, SUSFS, Droidspaces, or Hybrid Mount.

## Project layout

```text
app/       Android app, Compose UI, privileged-service integration, logs, and updates
exploit/   Rust runners and per-kernel C exploit plants
lkm/       SUSFS guard, Hybrid Mount, and related build tooling
ports/     Device-specific notes and recovery tooling
docs/      Screenshots and badges
```

## Build

Build the Android app:

```bash
cd app
./gradlew :app:assembleRelease
```

Build the device-side runners:

```bash
export ANDROID_NDK_HOME=/path/to/ndk
./exploit/build-all.sh
```

## Safety

CVE-2026-98260 is a race-condition UAF and can cause a kernel panic or reboot. Use Shark only on devices you own. Dynamic Switching requires a clean boot the first time.

## License

Shark code is GPL-3.0. Bundled SUSFS and Hybrid Mount components are GPL-2.0. See `LICENSE`, `NOTICE`, and the bundled license texts for details.
