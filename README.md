# WCT-OS LTS 1.0

一个 **GPT + FAT32 UEFI 镜像**里包含两套系统：

1. **WCT-OS Native**：自研的纯 C UEFI 原生终端，开机默认进入。
2. **WCT-OS Linux**：内嵌的 Linux 兼容子系统，提供 CPython、nano、中文输入和完整 POSIX 环境。

原生终端执行 `linux` 会直接启动内嵌的 Linux 子系统；Linux 里执行 `native` 会重启回到原生终端。两套系统共享同一块 FAT32 文件系统。

![WCT-OS 启动画面](screenshots/wct-boot.png)

![WCT-OS Native](screenshots/wct-native.png)

![WCT-OS 主题切换](screenshots/wct-theme-matrix.png)

![WCT-OS Linux 兼容子系统](screenshots/wct-linux.png)

## 启动

原生启动会先通过 GOP 清除主板 BIOS 遗留的开机 Logo，再显示蓝色 WCT-OS 方块 Logo，下方依次检测 CPU、主板平台、固件、最大内存，并按 60% 主内存 / 40% 防溢出预留显示结果；日志结束后等待 3 秒进入原生终端。

- **QEMU 完整版**：双击 `start.cmd`，或运行 `run.ps1`。\n- **QEMU 无 Linux 版**：双击 `start-no-linux.bat`。
- **实体机**：用 Rufus DD 模式或 `dd` 将 `dist/WCT-OS-LTS-1.0.img` 写入 U 盘，使用 **UEFI 启动**并关闭 **Secure Boot**。
- 当前为 UEFI 启动；传统 Legacy/CSM 不支持。

开机流程：

```text
UEFI firmware
  -> EFI\BOOT\BOOTX64.EFI          (自研 C 原生终端)
       ├─ 普通命令：文件操作、查看 FAT32
       └─ linux 命令
            -> wct\bootx64.efi     (systemd-boot)
            -> wct\vmlinuz + initrd.img
            -> WCT-OS Linux 兼容子系统
                 └─ native 命令 -> reboot -> 回到自研原生终端
```

## 原生终端命令

```text
help              ls [PATH]       cat FILE
cd [DIR]          pwd             run FILE.wct
write FILE TEXT   rm FILE         cp SRC DST
mkdir DIR         edit FILE       new FILE
sleep N           theme [NAME]    font [N|next]
theme [NAME]      font [N|next]   banner
date              hw              mem 128
mem free          ver             clear
log               ps              pid
kill PID          poweroff        reboot
linux             native

默认主题：wct；可切换 ubuntu / wct / matrix / amber / ice。字体/控制台模式：font 或 font next。
日志：log 查看开机和操作日志，log clear 清空。
```

原生终端直接通过 UEFI Simple File System 读写同一块 FAT32，因此 `ls \home\wct`、`cat \home\wct\WELCOME.TXT` 都可使用。

### 日志

```text
log                     查看开机日志和本次终端操作日志
log info|warn|error TEXT 写入一条指定级别日志
log save                保存到 WCT-年-月-日.LOG
log clear               清空日志
```

日志带 `HH:MM:SS` 时间戳，级别为 `[INFO]`、`[WARN]`、`[ERROR]`。日志会自动保存到 FAT32 根目录，格式为 `WCT-YYYY-MM-DD-N.log`。每次启动 N 从 1 开始递增：当天第一次启动是 `-1.log`，下一次启动是 `-2.log`，同一次启动内持续更新同一个文件。开机日志包含 CPU、主板平台、固件、最大内存、60/40 内存划分和 FAT32 初始化；之后执行过的命令也会记录在 `[cmd]` 条目里。

### 进程管理

```text
ps           列出原生进程表
pid          当前 shell 的 PID
kill PID     结束指定进程（1/2 受保护）
sudo kill PID 强制结束受保护进程
poweroff     保存日志、显示 Logo 后关机
```

原生层没有内核调度器，`ps` 显示的是 WCT 原生终端维护的进程表（wct-init / wct-shell），没有 wct-bg 占位进程。

### 硬件信息与内存占用

```text
hw               显示 CPU、固件、内存和终端信息
mem              查看内存
mem 128          占用 128 MiB 内存
mem free         释放占用
```

`mem` 按 MiB 计算，范围 1–4096。占用的内存会一直保留到 `mem free` 或重启。`hw` 和 `mem` 都可以直接写进 `.wct` 脚本。

## Linux 兼容子系统

输入 `linux` 后进入。包含：

- CPython 3.11.2（`python`）
- GNU nano 7.2（`nano`）
- Bash、coreutils、BusyBox
- UTF-8 中文环境 + zhcon 拼音输入法
- Linux 6.1 内核
- FAT32 挂载于 `/fat`，用户目录 `/home/wct`
- `native` 命令：重启回原生 WCT-OS

常用命令：

```bash
python --version
python
nano notes.txt
ls /fat
cn
native
```

### 中文输入

```bash
cn
```

zhcon 热键：

| 热键 | 功能 |
| --- | --- |
| `Alt+Space` | 开/关 CJK 模式 |
| `Ctrl+Space` | 开/关输入法 |
| `Ctrl+Alt+1` … `9` | 切换输入法（第 1 个为全拼） |
| `Ctrl+Alt+0` | 英文模式 |
| `Ctrl+D` | 退出 zhcon |

## 文件系统

镜像使用真实的 **GPT + FAT32**：

- 裸机固件和两套系统都从同一 FAT32 分区启动。
- 原生终端看到的是 FAT32 根目录（`\`）。
- Linux 子系统把该分区挂载为 `/fat`。
- `/home/wct` 是 `/fat/home/wct` 的链接；文件由 nano/Python 写入后重启仍然存在。
- 分区里同时有 `EFI/`、`loader/`、`wct/`、`home/`、`data/`。

## 构建

需要：

- MinGW-w64 GCC（编译自研原生 UEFI 应用）
- Python 3
- QEMU + OVMF（运行）
- 可访问 `http://deb.debian.org/debian/`
- Windows `curl.exe`

运行 `build.cmd`：

1. 编译 `native/main.c` 为 `native/build/native.efi`；
2. 下载并裁剪 Debian 软件包，生成 initramfs；
3. 生成 GPT + FAT32 镜像，写入原生 EFI、Linux 内核、initramfs 和启动配置。

```text
dist/WCT-OS-LTS-1.0.img   256 MiB，UEFI 可启动（含 Linux 子系统）
no-linux/WCT-OS-Native-Only-1.0.img   64 MiB 纯原生版，无 Linux
native/                         自研 C 原生终端
linux/                          Linux 兼容子系统构建脚本与根文件系统
start.cmd / run.ps1             QEMU + OVMF 启动
build.cmd / build.ps1           完整构建
```

## 边界

原生 WCT-OS 目前是一个 **freestanding C / UEFI 原生用户环境**：它有自己的终端、FAT32 文件操作和 Linux 子系统加载器，但还不是带进程调度、虚拟内存和驱动的完整内核。

内嵌的 Linux 子系统用于提供当前真正可用的 CPython、nano、中文输入和 POSIX 工具链。两者在一个镜像里，但边界清晰。


## 光标、cd 与 WCT 脚本

原生终端启用了闪烁的硬件文本光标，提示符会显示当前目录：

```text
wct@wct-os:\home\wct> _
```

`cd` 支持相对路径、绝对路径、`.` 和 `..`：

```text
cd \home\wct
cd script-demo
cd ..
pwd
```

提示符下按 **↑ / ↓** 浏览最近 16 条命令。

输入命令或路径时，右侧蓝色文字是自动联想结果；按 **Tab** 接受补全，命令名、文件名和目录名都支持。

### 终端编辑器

```text
new note.txt      # 直接创建一个空文件
edit note.txt     # 文件不存在时自动创建
```

`edit` 打开不存在的文件会立即创建空文件，然后进入编辑器。

编辑器内命令：

```text
a TEXT        追加一行
m             多行输入：Enter 换行，空行结束
i N TEXT      在第 N 行前插入
r N TEXT      替换第 N 行
d N           删除第 N 行
l             显示内容
w             保存
wq            保存并退出
q             保存并退出（兼容习惯）

快捷键：
Ctrl+S        保存
Ctrl+Q        强制退出，不保存
Ctrl+X        保存并退出
```

### .wct 脚本

用 `run FILE.wct` 执行脚本。内置示例在 `/home/wct/demo.wct`：

```bash
run demo.wct
```

支持的行：

```text
# 注释
set NAME VALUE
echo TEXT $NAME
cd PATH
pwd
ls [PATH]
cat FILE
write FILE TEXT
mkdir DIR
rm FILE
theme ubuntu|wct|matrix|amber|ice
font N|next
hw
mem 128
mem free
sleep 1..5
while CONDITION
  ...
end
inc NAME [N]
break
continue
clear
date
linux
```

### while 循环

```text
set i 0
while $i < 5
  echo Count: $i
  inc i
end
echo Done.
```

支持的条件：

```text
while true
while $i < 5
while $i <= 5
while $i == 5
while $i != 5
while $i > 0
while exists \path\file
```

`inc NAME [N]` 让数值变量增加 N（默认 1）。循环体用 `end` 结束；支持 `break` 和 `continue`，最多执行 10000 次防止死循环。内置示例：`/home/wct/while.wct`。

示例：

```text
theme matrix
set PROJECT wct-demo
echo Building $PROJECT
cd \home\wct
write readme.txt Hello from WCT script
cat readme.txt
```

脚本中的变量会在 `echo` 和普通命令参数中展开。
