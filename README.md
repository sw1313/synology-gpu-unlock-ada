# synology-gpu-unlock-ada

将 [JustAResearcher/gpu-unlock-ada](https://github.com/JustAResearcher/gpu-unlock-ada) 接入黑群晖 DSM 的实机适配记录与源码。已在 **SA6400 / DSM 7.3.2 / RTX 4060 Ti 16GB / NVIDIA 595.99.02** 上完成两次普通重启验证，NVIDIA 驱动正常接管，指定 Tensor 指令吞吐约提升至原来的两倍。

本仓库新增 Linux 5.10 兼容补丁、udev 前置启动脚本、状态管理和脱敏验证资料。解锁原理、payload、固件生成器及 CUDA 探针来自上游，固定提交为 [`d28c485418c3d9d034cd4bac19200bc33dd3453b`](https://github.com/JustAResearcher/gpu-unlock-ada/tree/d28c485418c3d9d034cd4bac19200bc33dd3453b)。

## 实测环境与范围

| 项目 | 已验证配置 |
| --- | --- |
| DSM / 引导 | 7.3.2-86009 Update 5 / RR 26.4.0 |
| 模拟机型 / 平台 | SA6400 / epyc7002 |
| 内核 | 5.10.55+，SMP mod_unload，未启用 CONFIG_MODVERSIONS |
| 显卡 | RTX 4060 Ti 16GB，实际 PCI ID `10de:2803` |
| 子系统 ID | `10b0:1903` |
| 显卡位置 | `0000:01:00.0`，单 NVIDIA GPU，非 boot VGA，支持 FLR |
| 主板 | ASUS PRIME B760M-K D4 |
| 运行中的 NVIDIA 驱动 | 595.99.02，保持原有驱动 |
| 编译 SDK | Synology 7.3 epyc7002 / GCC 12.2.0 |

主板型号是测试条件，不代表主板白名单。是否可用还取决于 GPU、PCIe FLR、固件、内核符号和 NVIDIA 自动加载时机。其他主板、DSM 平台、PCI ID 或驱动组合尚未在本仓库验证。

公开的启动参考实现保留精确 BDF 限制；安装工具进一步限制到上表的 PCI/子系统 ID。不支持 `targets=all` 或多卡。调整这些条件需要重新检查启动顺序并进行实机验证。

## 实测结果

同一张卡、相同 cubin、165W 功率上限，20,000 次迭代、3 次重复，取最佳值：

| 指令测试 | 原始状态 | 解锁后 |
| --- | ---: | ---: |
| FP16 → FP32 | 47.6107 TF/s | 94.6157 TF/s |
| TF32 → FP32 | 23.6931 TF/s | 47.2030 TF/s |
| BF16 → FP32（mma_bench） | 47.4 TF/s | 94.8 TF/s |
| INT4 → INT32（对照组） | 376.906 TOP/s | 376.880 TOP/s |

两次重启均有 `transaction_result=0`，公开 RM getter 返回 FMLA32 / IMLA2 / IMLA4 均为 `0`（全速）。指令输出校验零错误，六组随机 FP16/BF16 cuBLAS GEMM 校验通过，PyTorch CUDA 计算与 NVENC 功能检查通过。

这些数值衡量特定指令吞吐，不能推导出推理、转码或所有应用翻倍。两次普通重启和功能检查也不等同于长期压力测试。详见 [验证记录](docs/validation.md) 和 [脱敏证据](evidence/)。

## 新增内容

- [内核兼容补丁](patches/dsm-5.10-compat.patch)：SHA 头文件兼容、PCI 锁兼容、旧 framebuffer 接口、只读事务结果。
- [启动脚本](runtime/preload.py)：在 DSM PCI coldplug 前执行，校验内核、PCI 身份及文件摘要；事务成功后放行 NVIDIA。
- [管理命令](runtime/gpu-unlock-ada)：`arm-once`、`enable`、`disable`、`status`。
- [systemd drop-in](systemd/20-gpu-unlock-ada.conf)：追加到 DSM 原有 udev 前置步骤，保留原有步骤。
- [构建脚本](scripts/)：固定上游提交、编译镜像和官方内核源码摘要，固件仅在本地生成。

本仓库不提供 `.ko`、NVIDIA 固件、驱动 SPK 或其他专有二进制。风扇/scemd 的独立兼容修复不在本仓库范围内。

## 构建和启用

需要 Linux 构建环境和 Docker。先阅读 [构建与安装](docs/build-and-install.md)，确认目标环境一致，再执行：

```sh
bash scripts/prepare.sh
bash scripts/build.sh
bash scripts/build-firmware.sh
```

安装工具在目标 NAS 本地生成硬件身份配置，**默认 disabled**，不会卸载驱动或在线重置显卡。其打包流程尚未在另一台 NAS 端到端验证；实测成功的是文档记录的启动机制及内核补丁。

安装并检查 udev 顺序后，先安排一次重启测试：

```sh
gpu-unlock-ada arm-once
# 在维护窗口正常重启；重启后检查：
gpu-unlock-ada status
nvidia-smi
```

确认 `Verified active: YES`、应用正确性和内核日志通过，再执行 `gpu-unlock-ada enable` 开启未来启动的持续尝试。`disable` 只改变未来启动，不会撤销当前硬件状态。

该流程会执行固件事务和 PCIe FLR。事务失败后可能保留 GPU 的 PCI hold，需要关闭后重新供电恢复。部署前应具备独立管理入口，详见 [停用与恢复](docs/recovery.md)。

## 开发检查

```sh
python3 -m unittest discover -s tests -v
```

本仓库启动保护测试使用模拟文件系统，不访问 GPU。`scripts/build-firmware.sh` 还会执行打过补丁的上游 `make test-full`，要求真实的固定版本输入和生成资产。软件测试不能替代新硬件上的重复验证。

## 许可与致谢

新增代码与兼容补丁采用 **GPL-2.0-only**，无担保，见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。上游及其引用的 Zagitta/gpu-unlock、TOTORONG/AD103_win_unlocker、WildFlash1st/cmp90hx-unlock 等项目提供了解锁链和研究基础。NVIDIA 固件、Synology 源码和工具链保留各自许可。

English: Source-only DSM SA6400/Linux 5.10 integration for the pinned upstream GPU unlock project. Validated on one RTX 4060 Ti 16GB with driver 595.99.02 across two warm reboots. This is a narrowly tested reference profile; instruction throughput results do not imply general application speedups.
