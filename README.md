| 字段 | 内容 |
|---|---|
| 作者 | 赵家奇 |
| 日期 | 2026-10-25 |
| 事项 | InterviewTwin |
| 版本 | v6.3 |

# InterviewTwin

让面试官通过对话了解一个人的真实经历、项目与判断方式，也支持其他人用自己的资料创建独立分身。

当前交付：**能力0.1.19／赵家奇资料1.1.3**。默认人物为赵家奇，代表项目餐小美。正式仓库：https://github.com/vanci444-hue/InterviewTwin。

## 结构与职责

```text
InterviewTwin/
├── skills/interviewtwin/
│   ├── SKILL.md              # 能力入口：识别任务，加载对应规则
│   ├── references/           # 面试、创建、维护和检测规则
│   └── scripts/twin.py       # 人物读取、资料管理与完整性检查
│
├── profiles/                 # 独立人物资料
│   └── zhaojiaqi/
│       ├── knowledge/        # 经历、项目、判断依据和表达风格
│       ├── sources/          # 审核后随包提供的原始资料
│       └── manifest.json     # 人物版本与文件完整性清单
│
├── scripts/                  # 安装、更新和评测工具；开发源码另含打包工具
├── tests/evaluation/         # 评测题与评价标准
├── docs/                     # 产品说明、使用方法与评测结论
└── INSTALL.md                # Agent 执行安装与更新的统一说明
```

## 面试回答流程

```text
用户提问
   ↓
确认当前人物，读取对应资料
   ↓
判断问题类型
   ├── 个人经历 → 依据已确认事实回答，不补造经历
   └── 方法论／假设题 → 给出专业分析，区分推演与亲历
   ↓
核对事实、职责、数字及实现状态
   ↓
自然回答，承接后续追问
```

通用 Skill 与人物资料分离，支持不同人物复用；评测材料独立存放，不进入正常面试工作区。

## 安装：任选一种方式

两种方式都会安装通用 Skill、初始化默认人物赵家奇的资料，并保存后续更新来源。需要 Python 3.10+、可访问 GitHub 的网络，以及目标 Agent 正常的文件与执行权限；开始面试还需要该 Agent 的模型服务可用。

### 方式一：在指定 Agent 中发一句话

打开你要使用的 **Codex、Cursor、Claude Code 或 WorkBuddy 本地代码项目**，进入准备使用的工作区，把下面这句话发给它：

> 请在当前工作区，为当前 Agent 安装 https://github.com/vanci444-hue/InterviewTwin 的 Skill，初始化随包人物资料，并核验安装结果。

在哪个 Agent 中发送，就为哪个 Agent 安装；如果 Agent 无法判断当前宿主或工作区，它会询问。Agent 负责获取仓库并按[安装说明](INSTALL.md)执行，你无需手动下载、解压或输入终端命令。宿主要求文件或执行授权时，正常确认。

### 方式二：在终端执行命令，指定目标 Agent

需要额外安装 Git。以下示例适用于 macOS / Linux 的终端，默认目标为 **Cursor**。先进入你准备存放 InterviewTwin 的目录，确认该目录下没有同名的 `InterviewTwin-installer` 文件夹，然后复制执行：

```sh
git clone https://github.com/vanci444-hue/InterviewTwin.git InterviewTwin-installer && python3 InterviewTwin-installer/scripts/get.py --repo https://github.com/vanci444-hue/InterviewTwin --home "$PWD/InterviewTwin-workspace" --host cursor
```

这条命令先下载安装工具，再从正式仓库获取并安装当前版本。`InterviewTwin-installer` 存放下载的工具；`InterviewTwin-workspace` 是实际使用工作区，里面保存 Skill、人物资料与更新记录。安装成功后，用目标 Agent 打开 **InterviewTwin-workspace** 文件夹。

将命令最后的 `cursor` 换成对应值即可选择其他 Agent：

| 目标 Agent | `--host` 的值 | 工作区内的 Skill 目录 |
|---|---|---|
| Codex | `codex` | `.agents/skills/interviewtwin/` |
| Cursor | `cursor` | `.cursor/skills/interviewtwin/` |
| Claude Code | `claude-code` | `.claude/skills/interviewtwin/` |
| WorkBuddy 本地代码项目 | `workbuddy` | `.codebuddy/skills/interviewtwin/` |

如果要安装到已有项目，将 `--home` 后的路径替换成该项目的绝对路径并保留引号。当前通过 `--host` 选择 Agent，尚未提供交互选择菜单；这也是项目级安装，不会自动安装到电脑上的所有 Agent。

Windows 用户可使用方式一；以上终端命令未作为 Windows 命令验证。网络访问失败时，检查 GitHub 连通性或使用下载后的本地包，详见[安装说明](INSTALL.md)。不要只用通用安装器复制 Skill 目录：本项目还需要独立人物资料初始化。

若提示 `CERTIFICATE_VERIFY_FAILED`，说明 Python 的 HTTPS 证书校验未通过。macOS 使用 python.org 安装包时，可先运行对应 Python 应用目录中的 `Install Certificates.command`；其他安装方式请修复该 Python 环境的 CA 证书配置。修复后无需再次克隆，单独重跑上面 `&&` 后面的 `python3 ...` 命令即可，不要关闭证书校验。

### 安装后开始使用

安装完成并加载后，先展示实际可用人物和功能菜单，让使用者选择下一步。需要新建会话才能加载的宿主，可在新会话中说“使用 InterviewTwin”，进入同一菜单。

默认人物初始化成功后的菜单示例：

> InterviewTwin 已准备好。当前可面试的人物：赵家奇。
>
> 你想做什么？
>
> 1. **面试赵家奇**：了解经历、项目，讨论方法论并连续追问。
> 2. **创建我的分身**：提供简历或项目资料，整理、试问并确认个人版本。
> 3. **维护与更新**：修改自己的资料，或更新已安装的 Skill 和随包人物。
> 4. **检查分身**：检查资料完整性，或了解如何评测回答质量。
>
> 可以选一项，也可以直接说你的需求。

人物列表以实际安装内容为准。使用者已经明确提出“面试赵家奇”等任务时直接进入对应流程，不重复菜单。

## 更新与创建自己的分身

更新：

> 更新 InterviewTwin

Agent根据安装时记录的GitHub来源检查更新：有新版时更新Skill和随包人物资料；没有新版时告知当前已是最新。自建人物、原件、草稿和旧快照默认保留，无需额外声明；发现正式资料有本地修改时暂停覆盖。明确锁定到固定版本时，不自动切换到其他版本。

当前由使用者发起更新，不后台自动检查、不主动推送通知，也不自动替换已安装内容。

创建个人版本：

> 我要创建自己的分身。这是我的简历，请整理成草稿，让我试问。

试问、纠错后分别确认内容与可提供范围，生成独立人物版本。详见[使用说明](docs/使用说明.md)。

## 交付材料

| 内容 | 入口 |
|---|---|
| 运行Skill与人物资料 | `skills/interviewtwin/`、`profiles/zhaojiaqi/` |
| 产品与使用说明 | [设计取舍](docs/产品设计与取舍.md)、[使用说明](docs/使用说明.md) |
| 评测集 | [问答题库](tests/evaluation/cases.v1.json)、[第二人物示例](tests/evaluation/second-person-015.json) |
| 评测方法 | [方法与运行说明](docs/评测运行说明.md) |
| 结果与样例 | [验证结论与限制](docs/交付评测结论.md)、[真实回答](docs/真实回答样例.md) |

Codex是主要实测环境；其他宿主实际模型效果未验证。当前版本只进行打包与安装核验，未重新做模型评分。已知问题及历史证据范围见验证结论。内部日志、历史修复过程和私人面试材料不在交付包中。
