# 构建与安装

## 固定输入

| 输入 | 版本 / 校验 |
| --- | --- |
| gpu-unlock-ada | `d28c485418c3d9d034cd4bac19200bc33dd3453b` |
| 编译镜像 | `dante90/syno-compiler@sha256:73f27f7f33c96549eb03ee6450c0eee8c54e16182d0ec62dcda65c7ec2f7d2fb` |
| 官方内核源码 | Synology 7.3-86009 / epyc7002 / linux-5.10.x.txz |
| 内核源码 SHA256 | `0c5f70ba9a4c8372f862a5f2778b7fe8903b667f2a94671012a480a74295aaf1` |
| 官方目录所列 MD5 | `18b6f2ec90313c12da6864e97478e966` |
| NVIDIA kernel source | 610.43.03；SHA256 `7e118923c7a23edc36114d63273a46e3e04e9af98695a42203e7ac2dfe9fc1dc` |
| nvidia-utils 包 | 610.43.03-1 x86_64_v3；SHA256 `e17e7c92eeffa178b0fe1f40eb17a47095f8fc3ce4a77bf115cf5bd5a4df86e9` |

官方内核下载地址已写入 `scripts/prepare.sh`。NVIDIA 下载地址与固定摘要由上游 `firmware/fetch_artifacts.py` 管理；下载失败时应恢复对应输入，不应跳过摘要检查或替换成其他版本。

用于解锁事务的 610.43.03 固件与现有 595.99.02 驱动的 GSP 固件分开存放。不要替换现有驱动目录。

## 构建

在独立 Linux 工作目录检出仓库。需要 git、curl、patch、make、gcc、Python 3、tar、xz、zstd、sha256sum 和 Docker；生成器可能通过包下载器访问网络。可选 PyCryptodome 用于上游离线 AES 解码测试。

```sh
git clone https://github.com/sw1313/synology-gpu-unlock-ada.git
cd synology-gpu-unlock-ada
bash scripts/prepare.sh
bash scripts/build.sh
bash scripts/build-firmware.sh
```

`prepare.sh` 在 `work/upstream` 检出固定提交并应用补丁，验证官方内核源码后提取 SDK 缺失的 framebuffer C 源文件。已有 `work/upstream` 时拒绝覆盖，避免重复打补丁。

编译容器使用 `/opt/epyc7002/build` 与 `/opt/epyc7002/bin`，产物为：

```text
work/stage/modules/fbdev.ko
work/stage/modules/fb.ko
work/stage/modules/gpu_unlock.ko
work/stage/firmware/*
```

依赖链是 `gpu_unlock -> libsha256, fb`、`fb -> fbdev`。`libsha256.ko` 使用目标 DSM 自带的匹配版本，不发布二进制。

镜像默认 ENTRYPOINT 是 `/opt/do.sh`，构建脚本显式覆盖为 bash。DSM 缺少 CPU CFS quota 支持，故采用 make `-j2`，不要为该主机添加 `docker --cpus`。构建容器仅挂载源码和工作目录，不访问 `/dev`、不加载宿主模块。

## 安装前检查

当前公共安装工具只接受 README 中的参考配置，包括固定 `0000:01:00.0`、`10de:2803` 和 `10b0:1903`。即使显卡商品名称相同，也应以实际 PCI ID 为准。它不是面向其他机型的通用安装器。

在目标 NAS 检查：

```sh
uname -r
uname -v
lspci -nnk -s 0000:01:00.0
lspci -vv -s 0000:01:00.0
cat /sys/bus/pci/devices/0000:01:00.0/boot_vga
systemctl cat systemd-udev-trigger.service
```

要求非 boot VGA、支持 FLR（`FLReset+`），且解锁执行点早于 NVIDIA 绑定显卡。实测 DSM 的 NVIDIA 自动加载发生在 udev PCI coldplug 阶段，普通套件启动时已经太晚。

实测的原有 ExecStartPre 只记录块设备 dry-run 和清理 uevent helper；公开 drop-in 追加在其后、正式 coldplug 前。必须核查本机 unit。若现有 prestart、initramfs 或其他服务已加载 NVIDIA，当前流程会跳过已绑定显卡，不会强行解绑。

## 安装（默认停用）

将仓库源码及本机构建的 `work/stage` 放到目标 NAS 的同一个工作目录，以 root 执行：

```sh
python3 scripts/install.py --stage work/stage --sha-module /lib/modules/libsha256.ko
systemctl cat systemd-udev-trigger.service
gpu-unlock-ada status
```

安装工具会拒绝现有安装和固件路径，避免覆盖。它检查机型、内核 release、PCI 身份、非 boot VGA、唯一 NVIDIA UUID 和模块 vermagic，并在本机记录精确 `uname -r/-v` 与 UUID。文件由 root 持有，配置目录权限为 0700，模式初始为 `disabled`。

vermagic 检查不是所有内核 ABI 的证明；构建源必须与实际目标内核匹配。配置记录的是当前目标身份，不能自动证明任意来源的模块可信。只使用自己审查、构建的 stage。SHA manifest 用于检测安装后的文件变化，不是数字签名。

新增安装工具在本仓库中提供，尚未对另一台 NAS 执行完整安装演练。已验证的运行脚本仅整理了入口和锁文件生命周期以便测试，事务门禁与既有成功部署一致；没有将此整理版本重新覆盖到实测 NAS。

## 单次验证和持续模式

```sh
gpu-unlock-ada arm-once
```

在维护窗口安排正常重启。`once` 在检查通过、开始模块加载前消费为 disabled；前置检查失败时不会消费。重启后：

```sh
gpu-unlock-ada status
nvidia-smi
dmesg | grep -E 'gpu_unlock|payload result|selector result|post-FLR|NVRM|Xid'
```

同时要求内核 payload、权限、selector、FLR 后检查通过，`transaction_result=0`，目标及实验开关一致，NVIDIA 正常接管，`status` 的只读 RM getter 返回全速。只有 `insmod` 成功或 `nvidia-smi` 显示显卡并不够。

确认应用数值和功能检查通过后：

```sh
gpu-unlock-ada enable
```

此命令将未来开机设为 persistent。命令本身不会执行当前 GPU 解锁，也不代替上述单次验收。任何内核构建身份变动都会让启动前置检查跳过事务，需重建并重新验证。
