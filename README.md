# OAS：供 Agent 安装的脱敏分享版

基于 [OnmyojiAutoScript](https://github.com/runhey/OnmyojiAutoScript) 的定制分享版。安装路线是 **Windows → MuMu → 独立 OAS 后端 → 外置 OASX → 单任务验证**。不带作者账号、设备配置、运行记录或私人识别图片。

**不是所有功能开箱即用的安装包。** Agent 可按本文准备环境、生成空白配置并验证服务；登录由用户完成，缺图功能需要重新制作本地模板。服务能启动不等于游戏任务已通过。

## 复制给 Agent

```text
请按 https://github.com/wuyinghua-bjtu/oas 的完整 README 安装脱敏分享版。
先检查已有 OAS、OASX、MuMu、Python 和端口，不覆盖正在使用的安装。
Backend 与 OASX 分开放，后端只用本仓库 master，使用 Python 3.10 64 位独立环境。
安装依赖后运行 share_setup.py --init；不要复制作者账号、日志、截图或私人模板。
不要运行旧 easy-install 更新器、deploy.installer 或 gui.py，使用 server.py 和外置 OASX。
初始化不连接设备、不启停模拟器、不替换模拟器 ADB、不启用任务。
先验证配置、依赖、缺图清单以及 /home/test、/script_menu、/config_list。
登录和验证码由我完成；连接前确认真实 Serial、窗口标题及其他 worker 是否占用设备。
不切换桌面，不关闭、重启或启动模拟器；设置变更必须重启时先暂停并说明。
先测截图与控制，再由我选一个任务试跑，区分离线检查和实机完成。
卡住先查日志，有限重试安全返回；必要时只重启游戏，不通过重启模拟器解决。
不提交私人配置。最后给出安装路径、启动命令、实际端口、验证结果和剩余阻塞项。
```

## 1. 准备与隔离

- Windows 10/11 64 位，Git、Python **3.10 64 位**；本版依赖 `pywin32`，不承诺 macOS/Linux 直接可用。
- 已有 OAS 的用户另选目录，不在运行中的后端安装、更新或执行测试。
- 推荐独立目录：`D:\OAS-Share\Backend`、`D:\OAS-Share\OASX`。路径是示例，不能覆盖已有文件。
- 从 [MuMu 官网](https://mumu.163.com/) 安装模拟器，已有实例保留。游戏安装、登录、密码、验证码由用户完成。
- 开启 ADB 调试，在多开器记录目标实例的实际端口；先只接一个实例，不照抄别人的 Serial。
- 游戏画面应为 `1280 × 720` 横屏。默认庭院、默认战斗场景、简约战斗主题，关闭自动进入闲庭和个性结算；脚本庭院选项要与游戏一致。
- 不自动启停或重启已有模拟器，不切换桌面。设置变更需要重启时先让用户处理。窗口截图方案下不最小化 MuMu。

## 2. 安装后端

沿用 Backend/OASX 分离的原路线，但不直接运行原 easy-install 更新器：它可能拉回上游或处理其他进程。后端代码从本仓库取得，运行环境独立安装。

在 PowerShell 中执行，目标位置必须尚未存在本安装：

```powershell
git clone --branch master https://github.com/wuyinghua-bjtu/oas.git D:\OAS-Share\Backend
Set-Location D:\OAS-Share\Backend
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe share_setup.py --init
```

没有 `py` 时使用已核实为 3.10 64 位的 Python 完整路径创建环境；不要使用 WindowsApps 占位 `python.exe`。下载失败先排查网络或选择可信 PyPI 镜像，不关闭 TLS 校验。

初始化从代码默认值生成 `config/template.json`、`config/oas1.json`、`config/deploy.yaml`，不覆盖已有文件、不读取作者配置、不连接设备，并关闭配置内全部 `enable` 布尔开关。再次执行保留原文件。

默认：本仓库 `master`、仅监听 `127.0.0.1:22288`、不自动更新、不定时重启、不替换模拟器 ADB、不自动启动任务。

Agent 应在 `config/deploy.yaml` 中配置实际路径，路径使用 `/`：

- `PythonExecutable`：当前 `.venv/Scripts/python.exe` 完整路径。
- `GitExecutable`：`Get-Command git` 返回的完整路径。
- `AdbExecutable`：当前虚拟环境 `Lib/site-packages/adbutils/binaries/adb.exe` 的实际路径。

保留 `ReplaceAdb: false`，不执行 `python -m deploy.installer`、旧 `oas.exe` 或 `gui.py`。本路线不需要内置 Qt GUI。

## 3. 安装 OASX

从 [OASX Releases](https://github.com/runhey/OASX/releases) 下载 Windows 发布压缩包，解压到独立 OASX 目录，不把前端放入 Backend，也不要用源码包代替前端。

最初路线使用 `v0.3.2` Windows 包；这是历史参考，不保证永远最新。Agent 应记录实际下载版本，并验证能连接本版 API。

## 4. 启动与 API 验证

从 Backend 根目录运行：

```powershell
.\.venv\Scripts\python.exe server.py --host 127.0.0.1 --port 22288
```

保留这个终端；关闭会停止服务。需要后台运行时用 Python 完整路径、明确工作目录和独立日志，记录自己启动的进程，不结束其他后端。

端口占用先核对占用者，不杀进程；改用空闲端口并同步 OASX。另开 PowerShell 验证：

```powershell
Invoke-RestMethod http://127.0.0.1:22288/home/test
Invoke-RestMethod http://127.0.0.1:22288/script_menu
Invoke-RestMethod http://127.0.0.1:22288/config_list
```

预期分别为测试消息、任务菜单、包含 `oas1` 的配置列表。根地址没有网页不等于服务失败；这是 OASX 使用的 API。

打开 `oasx.exe`，登录实际 `127.0.0.1:端口`。默认用户名密码留空，仅用于本机，不开放公网，不关闭防火墙。**先手动启动 server.py，再连接 OASX；不要让 OASX 服务安装器再次运行旧更新路线。**

## 5. 自己的设备与单任务验收

选择 `oas1`，填写自己的 Serial 和真实窗口标题，不导入他人配置。确认其他 worker 未占用同一设备/账号，避免抢点击或互相踢号。

最初实机路线用 `window_background` 截图、`window_message` 控制；当前设备必须重新验证，不直接宣称可用。窗口标题和权限需匹配，MuMu 不最小化。需要改用 ADB 时单独评估，不自动替换模拟器 ADB。

验收顺序：

1. 服务 API 与 OASX 连接成功。
2. 目标设备截图成功，游戏区域实际 `1280 × 720`。
3. 对无风险目标做一次控制测试，确认点击准确。
4. 用户选择一个基础任务，只开这一项，核对次数、队伍和运行时间。
5. 观察进入、执行、结算/返回、下一次时间；直接证据充分才算通过。

账号认证由用户完成。卡住先暂停目标 worker、查日志、有限重试安全返回；必要时只处理游戏客户端，不无故启停或重启模拟器。

## 6. 缺图与功能边界

```powershell
.\.venv\Scripts\python.exe share_setup.py
```

列出源码直接引用但未包含的图片。静态检查不覆盖动态路径、模型和全部运行时依赖。部分原始模板含昵称/头像，部分新模板未隐私审核，不能整体复制作者截图目录，也不能用纯色图或降低阈值假装补齐。

涉及缺图的功能暂不开启。使用者可在自己的设备重新制作仅含必要 UI 的模板并本地保存；发布前逐图核查昵称、头像、好友信息。自定义多账号、协作、师徒和活动流程需要逐项重新配置与验证。

分享版仍需全新 Windows 完整安装、OASX 实机连接及游戏任务验收；维护者应明确报告验证范围，不承诺所有任务兼容当前游戏版本。

已有检查：使用已有 Python 工具环境在独立端口启动分享后端，`/home/test`、`/script_menu`、`/config_list` 均返回成功；默认用户配置可加载，重复初始化保留文件。未控制游戏，未验证全新依赖安装或 OASX。随后补入 73 张经审核的通用 UI 模板，保留私人字形及无法确认的图片不发布；静态检查仍有 37 个缺失图片引用（含图片规则 JSON），因此尚不能标记为完整可运行分享版。

## 7. 更新与隐私

更新源只用 `https://github.com/wuyinghua-bjtu/oas.git` 的 `master`。先暂停本安装的任务与后端、私下备份配置并检查 `git status`；有改动先审阅，不自动 stash/reset/clean。确认工作区干净后：

```powershell
git pull --ff-only origin master
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe share_setup.py --init
```

不重启模拟器；恢复前重复服务和单任务检查。OASX 内置更新前必须核对 Git 路径、origin 与停止范围，不中断别的实例。

用户配置、`.venv`、`toolkit`、日志、截图不上传。发布前审阅暂存差异，不用 `git add .`。私人模板即使位于已跟踪路径，也必须手动排除。

## 许可证与风险

保留原项目署名和 [GPL-3.0 许可证](LICENSE)。开源免费，仅供学习交流。自动化可能违反游戏协议并导致账号处罚，不用重要账号试错；不提供账号凭证，也不保证收益或稳定性。
