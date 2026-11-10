## 本地私人配置与首次运行

代码与私人运行数据分离：在同一个 Backend 目录运行、修复和提交代码；账号、设备、运行记录及私人识别模板只保存在本地，不随 Git 提交。`.gitignore` 不会清除旧提交中的数据，也不会自动取消已跟踪文件；发布前必须审阅暂存内容和历史，不能直接推送未经审核的旧历史。

### 新环境必须自行准备

MQTT 示例的 `LOCAL_MQTT_BROKER`、`LOCAL_MQTT_USERNAME`、`LOCAL_MQTT_PASSWORD` 也在同一份本地映射中填写；不运行示例时无需配置。首次安装可使用仓库的 `share_setup.py --init`，所有任务默认禁用且不覆盖已有配置。代码以本仓库 `master` 为准，日常修复直接在运行目录提交并推送；不要推送旧备份分支、旧标签或使用 `--all`、`--mirror`。

未审核的新模板保留在维护者本机，不随本次迁移上传；它们可能包含私人画面。依赖这些模板的功能需要在自己的设备重建并单独验证，不能把本机可运行等同于全新环境全部可运行。

`tasks/` 下新增 PNG 默认忽略，已经跟踪的公共模板仍正常管理。新增通用模板需逐图审核后使用 `git add -f -- <具体路径>` 明确加入；禁止批量强制加入图片目录。旧 `.github/workflows/` 不继承发布，以免重新启用上游镜像或自动化流程。

- `config/local_values.json`：部分历史定制流程使用 `LOCAL_SUPPORT_`、`LOCAL_OCR_NAME`、`LOCAL_PARTNER`、`LOCAL_EXAMPLE_ACCOUNT` 作为公开占位键；本地 JSON 将这些键映射到自己的账号名或角色名前缀（所有值必须为字符串）。例如 `LOCAL_SUPPORT_001` 会用 `LOCAL_SUPPORT_` 的值替换前缀并保留 `001` 后缀，也可单独映射完整键。文件不随 Git 提交；缺少映射时保留公开占位值，不猜测真实角色。映射在首次读取后缓存，修改后需在合适时机重启目标脚本进程，不重启模拟器。已有有效映射已在本机保留，不能上传。

- `config/deploy.yaml`：从 `deploy/template` 复制后填写本机 `PythonExecutable`、`GitExecutable`、`AdbExecutable`，路径推荐使用 `/`。核对更新源和分支；关闭 `AutoUpdate`、`ReplaceAdb`、`AutoConnect`、`EnableReload`，将 `AutoRestartTime` 设为 `null`。仅监听本机，不直接运行旧安装器或更新器覆盖当前代码。
- `config/template.json` 与 `config/<配置名>.json`：由当前 `ConfigModel` 生成，再用 OASX 配置自己的任务。不要从别人的运行配置复制账号；初始所有 `enable` 开关应为 `false`。
- 用户配置中的 `script.device`：填写真实 `serial`、窗口标题 `handle`、`package_name`、`screenshot_method`、`control_method`；涉及模拟器路径、实例名时也使用本机值。不要照抄作者的端口或自动启动模拟器。
- 多账号功能：在对应任务配置中填写自己的 `AccountInfo`，包括 `character`、`svr`、`account`、`account_alias`、`apple_or_android`。FindJade 还需要自己的 `sup_account_list` 和 `invite_info_list`；组队、师徒功能按各任务配置填写真实参与者及设备。仅运行单账号基础任务时无需填无关账号列表。
- 通知功能：只在本地填写通知渠道、收件目标及凭证，不把实际值写入源码、README 或提交记录。游戏登录、密码和验证码由用户完成。

在已安装依赖的独立 Windows Python 3.10 环境中，从 Backend 根目录生成空白用户配置；以下代码不连接设备，遇到已有同名文件会停止，不能覆盖正在使用的配置：

```python
import json
from pathlib import Path
from module.config.config_model import ConfigModel

def local_defaults(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'enable' and isinstance(child, bool):
                value[key] = False
            elif key in ('account', 'account_alias', 'character', 'svr', 'password', 'token', 'name') and isinstance(child, str):
                value[key] = ''
            else:
                local_defaults(child)
    elif isinstance(value, list):
        for child in value:
            local_defaults(child)
    return value

config_dir = Path('config')
config_dir.mkdir(exist_ok=True)
for config_name in ('template', 'oas1'):
    defaults = local_defaults(ConfigModel().model_dump(mode='json'))
    defaults['config_name'] = None if config_name == 'template' else config_name
    with (config_dir / (config_name + '.json')).open('x', encoding='utf-8') as handle:
        json.dump(defaults, handle, ensure_ascii=False, indent=2)
```

### 本地模板与运行记录

`config/` 整个目录（包括历史 `config/findjade/find_jade.json`）、`log/`、`work/`、截图、`toolkit/`、虚拟环境及 `.env` 文件不发布。日志包含账号进度，通常由程序自行生成；新环境不需要作者的日志，迁移同一用户的断点记录时应私下备份并单独核验。

以下模板不发布，使用涉及它们的功能前需在自己的设备制作并保存在原路径：`tasks/BondlingFairyland/invite/select_friend_off.png`、`select_friend_on.png`，`tasks/Component/SwitchAccount/res/sa_ming_character.png`，三个目录 `tasks/Component/Costume/main1/`、`tasks/GameUi/page/`、`tasks/KittyShop/ks/` 下的 `image_name.png`，以及 `tasks/WantedQuests/invite/wq_invite_friend_list_appear.png`。这些模板不是启动服务的通用凭证；没有需要的模板时，不启用对应功能，也不要用空白图或降低匹配阈值掩盖问题。

`private/` 可存放私下备份，但程序不会自动读取该目录或 `*.local.json`：当前有效配置仍是 `config/<配置名>.json`，模板仍按源码声明的原路径加载。不要把普通功能代码整体加入忽略规则；源码里若仍有个人信息，需要改为读取本地配置后才能公开。

启动前核对设备与账号未被其他 worker 占用，先验证服务、截图和一次安全点击，再只开启一个任务检查完整结果。不要切换桌面或启停模拟器。修复后的 `commit` 只保存本地代码版本，`push` 才上传；二者均不会让已运行进程自动加载新代码。

---

<div align="center">

# OnmyojiAutoScript

<br>

<div>
    <img alt="python" src="https://img.shields.io/badge/python-3.10-%233776AB?logo=python">
</div>
<div>
    <img alt="platform" src="https://img.shields.io/badge/platform-Windows-blueviolet">
</div>
<div>
    <img alt="license" src="https://img.shields.io/github/license/runhey/OnmyojiAutoScript">
    <img alt="GitHub repo size" src="https://img.shields.io/github/repo-size/runhey/OnmyojiAutoScript">
    <img alt="GitHub all releases" src="https://img.shields.io/github/downloads/runhey/OnmyojiAutoScript/total">
    <img alt="stars" src="https://img.shields.io/github/stars/runhey/OnmyojiAutoScript?style=social">
</div>
<br>

阴阳师自动化脚本

一键托管


### [文档](https://runhey.github.io/OnmyojiAutoScript-website/)

#### 主仓库: [https://github.com/runhey/OnmyojiAutoScript](https://github.com/runhey/OnmyojiAutoScript)

</div>

阴阳师，作为一个手游，已经进入了生命周期的晚期。从现在到关服的这段时间里，请减少花费在阴阳师上的时间，把一切都交给 OAS。

## 功能 Features

- **日常任务**: 悬赏封印、小猫咪、小杂签到、金币妖怪、年兽、花合战、地鬼、封魔、御魂整理
- **每周相关**: 真蛇、秘闻竞速、神秘商店、搜刮商店、斗技、每周小杂事
- **阴阳寮**: 结界上卡、结界蹭卡、结界突破、寮突破、狩猎战、集体任务、道馆
- **御魂副本**: 八岐大蛇、业原火、日轮之城、永生之海、六道之门
- **肝帝专属**: 探索、契灵、御灵、觉醒副本、石距、百鬼夜行
- **限时活动**: 每期爬塔、超鬼王、对弈竞猜、花车巡游、智力答题

### 显著特点
- **全部任务**: 你能想到的没有想到的都有，一条龙给你解放双手（该画饼画饼，该挖坑挖坑）
- **无缝衔接**: 时间管理大师，优异的任务调度系统，无缝寄养，无缝执行任务
- **装饰可选**: 全部初始皮肤是什么鬼，这里支持你喜欢的庭院、主题等等，[详细说明](https://github.com/runhey/OnmyojiAutoScript/issues/180)
- **百鬼夜行**: 利用AI来智能撒豆子，模型包含所有式神，[效果展示](https://runhey.github.io/OnmyojiAutoScript-website/docs/user-manual/hyakkiyakou)

## 许可证 LICENSE

This project is licensed under the GNU General Public License v3.0.

## 声明 Announcement
本软件开源、免费，仅供学习交流使用。开发者团队拥有本项目的最终解释权。使用本软件产生的所有问题与本项目与开发者团队无关。
OAS is a free open source software, if you paid for OAS from any channel, please refund.
OAS 是一款免费开源软件，如果你在任何渠道付费购买了OAS，请退款。

## 关于 Alas
OAS 基于碧蓝航线脚本 [AzurLaneAutoScript](https://github.com/LmeSzinc/AzurLaneAutoScript) 开发，考虑到星穹铁道脚本 [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot) 中所提及的问题，
OAS 在其基础上进行了如下优化：
- **调整设计架构**: 将前后端拆离出来更加灵活，方便后续的维护和扩展；优化代码架构使其减少同游戏耦合，更加通用。
- **搭建新的GUI**: 原先的方案过于臃肿，选用 [flutter](https://flutter.cn) 搭建一个全平台的界面端，界面更加舒适简洁
- **新的OCR库**: 跟随 [LmeSzinc](https://github.com/LmeSzinc) 的步伐， [ppocr-onnx](https://github.com/triwinds/ppocr-onnx) 更加简易使用，精度更高速度更快
- **新的Assets管理**: 构建了一个新的Assets管理系统，更加方便的管理游戏资源如图片，文字，点击等等
- **配置文件 [pydantic](https://github.com/pydantic/pydantic) 化**: pydantic 可以更加优雅的管理用户配置

## 相关项目 Relative Repositories

- [Alas](https://github.com/LmeSzinc/AzurLaneAutoScript): 碧蓝航线的自动化脚本
- [SRC](https://github.com/LmeSzinc/StarRailCopilot): 星铁速溶茶，崩坏：星穹铁道脚本，基于下一代Alas框架。
- [OASX](https://github.com/runhey/OASX): 同 OAS 对接的全平台 GUI
- [NikkeAutoScript](https://github.com/megumiss/NIKKEAutoScript): 胜利女神：NIKKE 自动日常脚本
- [AAS](https://github.com/TheFunny/ArisuAutoSweeper): 蔚蓝档案自动化脚本
- [MAA](https://github.com/MaaAssistantArknights/MaaAssistantArknights): 明日方舟小助手，全日常一键长草
- [FGO-py](https://github.com/hgjazhgj/FGO-py): 全自动免配置跨平台开箱即用的Fate/Grand Order助手
- [OAS-website](https://github.com/runhey/OnmyojiAutoScript-website): OAS 的文档网站，使用 [docusaurus](https://docusaurus.io/) 构建
- [ppocr-onnx](https://github.com/triwinds/ppocr-onnx): OCR 库，基于 onnxruntime 和 PaddleOCR
- [gurs](https://github.com/2833844911/gurs): 基于赛贝尔曲线模拟滑动轨迹, 引入其轨迹模拟人手滑动

## 联系/加入我们 Contact/Join Us



相对于其他的游戏，阴阳师玩家总体而言对脚本这类工具具有极高的排斥性。树大招风，无论你是否喜欢 OAS ，我们都希望你不在互联网上进行宣传，这保护 OAS , 也保护开发者们。

为此保持较高的入群门槛:
#### QQ交流群: 1群465946275 2群1076565458
- 你的QQ等级必须大于32级(🌞🌞)，注册时间超过一年，低等级账号成分复杂，还请见谅。
- 你必须拥有一个 Github 账户来点一个 **Star** (这并不影响你入群后取消Star)，同样的要求注册时间过半年。
- 入群验证填入你的 Github `username`(不是`name`)，无需在意问题是什么，由QQ机器人审核(机器永远的对的)。

#### QQ开发群: 207613181 (有意开发本项目请加此群, 请不要胡乱加群)

- 开发规划：[#354](https://github.com/runhey/OnmyojiAutoScript/issues/354)
- OAS 继承了 Alas 的设计思路，极大简便了开发，欢迎提交 PR，挑选你感兴趣的部分进行开发即可。
- OAS 仍在活跃中， 我们会不定期发布未来的工作在 Issues 上并标记为 `help wanted`，欢迎向 OAS 提交 PR，我们会认真阅读你的每一行代码的。

## 安装 Installation

- [学会提问](https://runhey.github.io/OnmyojiAutoScript-website/docs/user-manual/scientific-question): 最基本的要求，**必看必学必会**
- [用户手册](https://runhey.github.io/OnmyojiAutoScript-website/docs/user-manual/getting-started): 在线手册，不定期更新，包含所有使用说明
- [安装教程](https://runhey.github.io/OnmyojiAutoScript-website/docs/user-manual/installation): 保姆式安装手册,多翻翻有惊喜
- [开发文档](https://runhey.github.io/OnmyojiAutoScript-website/docs/development/preamble): 虽然迭代很多、年久失修，但入门开发必读，具体以源码为准

## 鸣谢 Acknowledgements

感谢所有参与到开发/测试中的朋友们

[![Contributors](https://contributors-img.web.app/image?repo=runhey/OnmyojiAutoScript)](https://github.com/runhey/OnmyojiAutoScript/graphs/contributors)

感谢所有完善文档的朋友们

[![Contributors](https://contributors-img.web.app/image?repo=runhey/OnmyojiAutoScript-website)](https://github.com/runhey/OnmyojiAutoScript-website/graphs/contributors)

<div align="center">

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=runhey/OnmyojiAutoScript&type=Date)](https://star-history.com/#runhey/OnmyojiAutoScript&Date)


## ⚡ Visitor count

![](https://profile-counter.glitch.me/runhey-OnmyojiAutoScript/count.svg)

</div>
