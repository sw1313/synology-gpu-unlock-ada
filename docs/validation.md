# 验证记录与资料来源

验证日期：2026-10-26。环境见首页，运行中的驱动为 595.99.02。上游针对同一 PCI ID 的报告使用其他驱动，本仓库新增的是 DSM 与该驱动组合的集成证据。

## 验收层次

- 内核层：两次普通 warm reboot 均完成 payload 标记、required permissions、SS0/SS1 selector 和 FLR 后检查，transaction_result 均为 0。
- 启动交接：事务时目标未绑定，driver_override 持有目标，成功后释放，原 NVIDIA 驱动正常绑定。
- 驱动读取：通过上游公开 RM getter `0x20801230`，FMLA32/IMLA2/IMLA4 从 1（半速）变为 0（全速）。该探针不执行 BAR 写入、固件上传或 GPU reset。
- 指令输出：相同 cubin 的 FP16/FP32、TF32/FP32、INT4/INT32 每种模式检查 270,336 个输出单元，零 mismatches。
- 数值：三组 seeded 输入、方阵/矩形/非 tile 对齐形状，各含 FP16 和 BF16，总计六个 cuBLAS GEMM 用例，stock 与 persistent boot 状态均零错误。
- 功能：PyTorch 2.9.1+cu128 CUDA 计算通过；NVENC 命令成功，原记录的 stdout/stderr 为空，因此仅将 NVENC 记为功能检查，不提供编码性能结论。

两次正常重启的结果分别保留为 first-boot 与 persistent-boot JSON。boot ID 和 GPU UUID 已移除，未发布原始部署配置。

## 性能测法

`tensor_modes_issue.cu` 和 `tensor_modes_driver_runner.py` 来自固定上游提交的 `diagnostics/bench`。同卡、相同驱动、165W 功率上限、20,000 迭代、3 次重复，cubin SHA256：

```text
ca52f7901fc5837fe6ba379a06311fdb671d1775411ec0f2d6e1cea38879dbf2
```

保留全部三次计时、launch 参数、输出数量和误差计数，见 `evidence/*tensor-rates*.json`。首页取每种模式的最佳吞吐。BF16 结果来自另一项上游 `mma_bench` 指令探针，原始表格见相应日志。

复现时在独立 CUDA 工具链环境按上游 `diagnostics/bench/README.md` 构建。不同 CUDA 编译器可能产生不同 cubin，应对自己构建的二进制记录 SHA，并在两种状态中使用同一文件：

```sh
python3 work/upstream/diagnostics/bench/tensor_modes_driver_runner.py \
  /path/to/your/tensor_modes_issue_sm89.cubin \
  --sha256 YOUR-CUBIN-SHA256 \
  --expect-uuid GPU-YOUR-LOCAL-UUID \
  --expect-power-limit 165
```

从空闲 GPU 的 baseline 开始，记录时钟/功耗策略，再进行单次启用后的比较。不要为了复测在运行中的 GPU 上强制重置或卸载模块。

## 软件检查

历史实机准备阶段，打过补丁的固定上游 `make test-full` 运行 33 项，结果 OK、3 skipped。跳过项为缺少 PyCryptodome 的可选离线 AES 解码；真实固定资产的 AD102/GA102 mock transaction 和共享 GSP 检查已执行通过，见 `evidence/upstream-test-full.log`。

本仓库新增 15 项 preload 测试及 5 项隔离安装测试，后者需要 Linux。所有 sysfs、配置、目标目录和模块加载命令均为模拟对象，安装测试不接触宿主真实配置。它们检查失败状态、PCI hold 保留、once 消费、禁用模式和安装前拒绝条件。

发布前已在 Linux 临时目录运行全部 20 项并通过；Windows 运行 15 项 preload 测试通过、5 项 Linux 安装测试按条件跳过。补丁适用性、shell/Python 语法检查记录见 `evidence/publication-checks.json`。整理后的构建包装脚本尚未重跑完整的干净环境构建。

公开整理保留已验证事务逻辑，仅将 preload 入口包装为 main 并确保锁文件在返回后关闭，以便在测试中重复调用。公开安装工具为新整理代码，隔离文件系统测试不构成另一台 NAS 的端到端安装认证。

## 脱敏与局限

公开 evidence 为原始实机资料的选取和结构化整理，移除了 GPU/boot UUID、主机名、内网地址、SSH 端口、个人路径和容器名称；kernel-gates 只摘取关键门禁及驱动接管行。`SHA256SUMS` 对应公开版本，不对应私有原始包。

未上传内核模块、NVIDIA 固件、SPK、输入压缩包、SSH 密钥和本机 mode.json。现有实机部署未被公开仓库整理过程覆盖。

当前数据只覆盖一套硬件和两次普通重启，没有长期压力认证、冷启动矩阵或其他 DSM/主板/驱动组合验证。指令吞吐提升无法直接预测实际 LLM、GEMM 大任务或视频转码的加速比例。
