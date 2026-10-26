# 停用与恢复

管理命令只控制未来启动，不能在线撤销已经执行的固件事务：

```sh
gpu-unlock-ada disable
```

前置检查失败、NVIDIA 已绑定或 disabled 时，不启动 GPU 事务；系统正常继续 coldplug。事务开始后若任意门禁失败，脚本保留目标 `driver_override=gpu-unlock-ada-hold`，避免 NVIDIA 接管未知硬件状态。全局 udev 继续启动，显卡可能无法使用。

检查：

```sh
cat /etc/gpu-unlock-ada/last-result.json
cat /run/gpu-unlock-ada/state.json
cat /var/log/gpu-unlock-ada.log
cat /sys/bus/pci/devices/0000:01:00.0/driver_override
```

失败后先停用未来尝试，再正常关闭系统。若内核报告固件未停止、保留 DMA 缓冲区，或 GPU 处于 blocked/held 状态，应完全关闭并重新供电后恢复。不要强制卸载模块、手工清空 PCI hold 或在线反复加载尝试。

如果配置文件损坏而 CLI 无法停用，可移走本项目单独的 drop-in。以 root 执行以下精确路径操作，不改动 DSM 原有 unit：

```sh
mv /etc/systemd/system/systemd-udev-trigger.service.d/20-gpu-unlock-ada.conf \
   /etc/systemd/system/systemd-udev-trigger.service.d/20-gpu-unlock-ada.conf.disabled
systemctl daemon-reload
```

然后正常关机并按需要完全断电。该操作不卸载当前模块。重新启动后本项目不会再次执行事务；原 NVIDIA 加载流程继续工作。停用期间可保留安装文件作为排查材料。

DSM 升级后应检查内核身份、systemd unit 与启动顺序是否变化。不要直接复制旧机器的 mode.json、GPU UUID、last-result.json 或旧内核模块到新机器。
