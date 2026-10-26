# 启动与内核适配

启动顺序：DSM 原有 udev prestart → 本项目 preload → PCI coldplug → NVIDIA 正常绑定。

1. root 配置决定 disabled / once / persistent；同一 boot 的成功标记阻止重复事务，文件锁串行化检查。
2. 校验精确内核 release/build、目标 PCI/子系统 ID、所有本地 payload 与模块文件摘要。
3. 已绑定驱动或存在其他 driver_override 时拒绝事务。
4. once 在模块加载前消费为 disabled；加载 libsha256、fbdev、fb。
5. 通过 driver_override 持有未绑定的目标，使用唯一精确 targets 和 ad106_experimental=1 加载 gpu_unlock。
6. 等待内核模块初始化完成，读取只读 transaction_result。仅当结果为 0、目标/实验开关一致且显卡仍未绑定时，清除 hold。
7. 正常 coldplug 让原 NVIDIA 驱动接管；status 再通过公开 RM getter 检查 FMLA32/IMLA2/IMLA4 全速。

drop-in 的 ExecStartPre 使用前导 `-`，脚本也以成功退出保护全局 udev；这只表示可选集成不能阻断全机枚举，不表示 GPU 解锁成功。事务失败后的 hold 是刻意保留的隔离状态。

## Linux 5.10 补丁

`pci_dev_lock/unlock` 在目标内核不可作为外部模块接口直接使用。兼容层保持 Linux 5.10 的相同锁顺序：`pci_cfg_access_lock` → `device_lock`，按逆序释放；host mock 映射继续使用上游的模拟接口。

目标 SDK 没有 `crypto/sha2.h`，回退到 `crypto/sha.h`。现代 aperture API 不可用时回退到旧 `remove_conflicting_pci_framebuffers`，CONFIG_FB=n 时无 kernel framebuffer owner，返回 0；原有已绑定驱动检查仍在。

SDK 缺失 framebuffer 的 C 源文件，故从匹配的官方源码补齐 fbdev/fb 并构建依赖，没有删除 framebuffer 保护或绕过符号依赖。

`transaction_result` 初始为 `-EINPROGRESS`，单目标事务完成后通过 WRITE_ONCE 写入实际返回值。它是最后完成目标的结果，故公共 DSM 启动实现严格限制为一个精确目标，不能推广成多卡汇总状态。没有匹配目标、共享固件加载失败或事务未执行时，初始非零值会阻止放行。

上游 payload SHA、完成标记、权限、selector 与 FLR 后检查全部保留。诊断中的 AD102 字样来自共享的上游事务路径，并不表示 RTX 4060 Ti 的实际芯片变成 AD102。
