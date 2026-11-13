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

### 包系统与 API

```text
pkg list                 列出已安装包
pkg install FILE         安装 .wct / .wctpkg 脚本包
pkg run NAME             运行包
pkg remove NAME          删除包
pkg info NAME            查看包内容

api list                 列出系统 API
api call METHOD ARGS     调用 API
```

包是放在 FAT32 `\\packages` 目录中的 `.wct`/`.wctpkg` 脚本。`.wctpkg` 可以在文件头声明元数据，安装后会自动加入 `help` / `pkg list` / `api call cmd.list`。包可以通过 `api call` 控制终端、任务和文件：

```text
api call term.write Hello
api call term.clear
api call task.list
api call task.kill 3
api call fs.ls \\home\\wct
api call pkg.list
api call cmd.list
api call cmd.ps
```

安装后的包文件名（去掉扩展名）会自动成为一个命令。例如安装 `hello.wct` 后直接输入 `hello` 即可执行。`api call cmd.NAME` 可以调用任意原生命令，`term.exec` 可以执行整条命令。

安装后的命令会出现在：

```text
pkg list
help                 底部的 Package commands
api call cmd.list    底部的 package commands
```

如果命令没有出现，先检查：

```text
pkg list
cat \packages\hello.wct
pkg run hello
```

| API | 作用 |
| --- | --- |
| `term.write TEXT` | 在终端打印一行文字 |\n| `term.color NAME` | 设置终端文字颜色 |
| `term.clear` | 清屏并重绘标题 |
| `term.banner` | 重绘 WCT-OS 标题 |
| `term.exec CMD` | 执行一整条终端命令 |
| `task.list` | 显示原生进程表 |
| `task.kill PID` | 结束进程，PID 1/2 受保护 |
| `task.poweroff` | 保存日志、显示 Logo 并关机 |
| `fs.ls [PATH]` | 列出 FAT32 目录 |
| `fs.cat FILE` | 显示文件内容 |
| `fs.write FILE TEXT` | 覆盖写入一行 |
| `fs.cp SRC DST` | 复制文件 |
| `fs.rm FILE` | 删除文件 |
| `fs.mkdir DIR` | 创建目录 |
| `pkg.list` | 列出已安装包 |
| `pkg.run NAME` | 运行包 |
| `sys.hw` | 显示 CPU、固件、内存信息 |
| `sys.log [ARGS]` | 查看/写入/清空/保存日志 |
| `cmd.list` | 列出全部原生命令 |
| `cmd.NAME ARGS` | 调用指定原生命令 |

### 桌面 GUI

```text
gui       进入 WCT-OS 桌面
exitgui   在桌面命令行输入，返回终端
```

桌面运行在 UEFI GOP framebuffer 上，使用内嵌 8x16 字体绘制，不依赖文本模式；鼠标通过 UEFI Simple Pointer / Absolute Pointer 协议读取。桌面使用后缓冲 + 一次性 Blit，避免整屏重绘闪烁；`run.ps1` 会添加 USB tablet 以便 QEMU 鼠标事件进入固件。

- 鼠标点击 Files / Terminal / Theme / Exit
- 键盘方向键选择，Enter 打开
- Files：点击目录进入，点击 Back 返回上级
- Terminal：点击 Terminal 打开，输入 `exitgui` 关闭桌面
- Theme：点击切换主题（也支持 F3）
- Exit：点击退出（也支持 F10）
- 键盘 `exitgui` + Enter 也可退出桌面

鼠标不可用时仍可用方向键和 Enter 操作桌面。

### USB 存储

```text
ls \                根目录会显示 usb0/、usb1/ 等挂载目录
cd \usb0            进入第一块 USB 存储
cd \usb1            进入第二块 USB 存储
usb                 列出 UEFI 可见的 USB 挂载
usb N               直接进入 usbN
usb boot            返回启动根目录
usb rescan          重新扫描（插入 U 盘后使用）
```

USB 存储通过主板 UEFI 固件驱动访问，需要 FAT32 文件系统。挂载后它只是根目录下的 `usb0/`、`usb1/` 虚拟目录；对该目录执行 `ls`、`cat`、`cp`、`pkg` 等操作就是操作 U 盘。

### 关于

```text
about
```

显示作者 `aqtwWCT95` 和 WCT 内核版本 `4.0.441`。

### .wctpkg 元数据

```text
#!wctpkg
# name: Hello
# version: 1.0.0
# author: aqtwWCT95
# command: hello
# description: print a green greeting
# color: green

api call term.write Hello from a .wctpkg package
```

- `command`：安装后生成的命令名
- `version`：显示在包列表和 `pkg info`
- `author`：作者
- `description`：帮助列表中的说明
- `color`：包运行时自动切换文字颜色
- 元数据行都是注释，不会被执行

终端颜色 API：

```text
color green
color cyan
color reset
api call term.color purple
```

支持：black、blue、green、cyan、red、magenta、brown、gray、darkgray、lightblue、lightgreen、lightcyan、lightred、purple、yellow、white。

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
build-native-only.cmd / .ps1    只构建 64 MiB 纯原生镜像
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
