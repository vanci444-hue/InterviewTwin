| 字段 | 内容 |
|---|---|
| 作者 | 赵家奇 |
| 日期 | 2026-10-26 |
| 事项 | InterviewTwin 的 Agent 安装、终端安装与更新指南 |
| 版本 | v6.5 |

# InterviewTwin 安装与更新

可以让 Agent 安装，也可以在终端执行命令。两种方式都支持使用默认人物、创建自己的分身和后续更新。

## 安装前准备

- Python 3.10+，以及目标工作区的文件与执行权限。
- 从 GitHub 安装时，需要能访问该仓库；终端方式还需要 Git。
- 开始对话需要目标 Agent 的模型服务可用。

人物资料保存于实际使用工作区的 `people/`，不保存在 Skill 安装目录中。安装完成后，请在这个工作区中使用 InterviewTwin。

## 方式一：让 Agent 安装

在准备使用的 Agent 中打开目标工作区，发送：

> 安装 https://github.com/vanci444-hue/InterviewTwin 的 Skill。

按宿主提示完成必要授权，安装后说“使用 InterviewTwin”，或直接开始提问。如果宿主需要刷新技能，按提示新建会话即可。

### 供安装 Agent 执行

1. 使用当前宿主的通用安装器，完整安装 `skills/interviewtwin/`。这是自包含的 Skill，默认人物的审核知识和原件已在 `assets/profiles/` 中，不必额外下载外层 profiles 或调用根目录专用安装器。
2. Skill 路径已经明确，不要反复查询目录树。已知宿主和工作区时直接使用，不扫描无关项目或电脑上其他 Agent。
3. 安装后读取 SKILL.md 的首次使用检查，按随包[操作入口](skills/interviewtwin/references/operations.md)执行离线初始化与真实读取。具体命令、更新步骤和运行故障处理由本文件与操作入口承接，SKILL.md 只保留相关检查与任务路由。若本轮无法发现新 Skill，在首次加载时执行；用户无需再输入一条安装命令。
4. 安装与初始化验证完成后，汇报结果即结束。默认保留下载的仓库、解压目录与安装工具副本（如 `InterviewTwin-installer`），不把清理这些目录作为安装收尾步骤，不主动执行 `rm -rf` 或其他等效删除，也不为可选清理额外请求删除授权。仅在用户明确要求清理时，先核对具体路径、内容及是否仍被安装或更新使用，再按宿主权限规则处理。

```sh
python3 "/实际Skill目录/scripts/bootstrap.py" --home "/实际工作区"
python3 "/实际Skill目录/scripts/twin.py" --home "/实际工作区" list
python3 "/实际Skill目录/scripts/twin.py" --home "/实际工作区" read --person 实际人物ID
```

命令中的路径和人物 ID 由 Agent 按实际结果填写。脚本位置相对于已安装的 Skill，不依赖作者电脑。全局 Skill 安装也可使用，但 `--home` 应指向用户工作区，不能指向全局 Skill 目录。

通用安装器没有统一的安装后执行钩子。初始化由安装 Agent 或首次加载的 Skill 完成，不能仅凭目录复制成功就宣布人物已经可读。

## 方式二：在终端安装

以下命令适用于 macOS / Linux，默认安装到 **Cursor**。

在准备存放项目的目录打开终端，确认当前目录没有同名的 `InterviewTwin-installer` 文件夹，然后执行：

```sh
git clone https://github.com/vanci444-hue/InterviewTwin.git InterviewTwin-installer && python3 InterviewTwin-installer/scripts/get.py --source "$PWD/InterviewTwin-installer" --repo https://github.com/vanci444-hue/InterviewTwin --home "$PWD/InterviewTwin-workspace" --host cursor
```

命令只克隆一次完整仓库。安装工具核对仓库来源、目标 commit 和副本状态后，直接使用该副本安装 Skill、初始化默认人物，并保存后续更新来源，不再下载第二份 ZIP。

- `InterviewTwin-installer`：下载的仓库和安装工具。
- `InterviewTwin-workspace`：实际使用工作区，保存 Skill、人物资料与更新记录。

安装完成后，用 Cursor 打开 **InterviewTwin-workspace** 文件夹，说：

> 使用 InterviewTwin。

若安装到已有项目，将 `--home` 后的路径替换为该项目的绝对路径并保留引号。不要把安装工具目录误当作实际使用工作区。

### 选择其他 Agent

替换命令最后的 `cursor` 即可：

| Agent | `--host` 参数 | 项目级 Skill 目录 |
|---|---|---|
| Codex | `codex` | `.agents/skills/interviewtwin/` |
| Cursor | `cursor` | `.cursor/skills/interviewtwin/` |
| Claude Code | `claude-code` | `.claude/skills/interviewtwin/` |
| WorkBuddy 本地代码项目 | `workbuddy` | `.codebuddy/skills/interviewtwin/` |

终端命令是项目级安装，不会同时安装到电脑上的所有 Agent。Windows 用户可使用方式一；上述终端命令未作为 Windows 命令验证。

### 已有下载副本或离线包

已有干净的 Git 副本时，无须再次克隆；调用该副本中的 get.py，传入 `--source`、原仓库地址、工作区和宿主即可。此路径仍会核对远端引用，不是离线安装。副本有修改、来源不一致或 commit 不匹配时会停止，不自动覆盖。

只有解压后的完整包、需要离线安装时，可运行：

```sh
python3 "/完整包目录/scripts/install.py" --source "/完整包目录" --home "/实际工作区" --host cursor
```

离线安装如实记录本地来源。后续更新需要该路径仍然可用，或由用户明确提供新来源；不能把本地包来源冒充已核验的 GitHub 来源。

## 更新 InterviewTwin

无论使用哪种方式安装，都可以在实际工作区对 Agent 说：

> 更新 InterviewTwin。

默认更新能力和绑定的随包人物，保留自建人物、草稿、原件与旧版本。明确只升级能力时，不同步人物。固定 tag/commit 不自动改为默认分支。

### 通过通用 Skill 安装器安装的版本

1. 执行 `bootstrap.py --home 工作区 --check`，核查当前人物完整性；异常时停止。
2. 沿用宿主记录或用户上下文中的原来源、目录与 ref 更新 Skill。安装器不支持覆盖时，先在临时目录取得并验证新版，保留原能力备份再替换，不先删除唯一可用副本。
3. 使用新版 `bootstrap.py --home 工作区 --update` 同步绑定人物，再实际 list/read。用户明确“只升级能力”时跳过此步；后续普通加载也不会偷偷切换人物版本。

原来源无法从宿主记录或上下文确定时，才询问来源；随包仓库声明不代表原安装来源已经联网核验。

通用安装器替换能力与同步人物是两个阶段，不能承诺跨工具原子性。人物同步失败时明确报告“能力已更新，人物保持旧版”，保留资料与证据；人物事务本身失败会回滚指针及本次新增快照。

### 通过终端或完整包安装的版本

Agent 读取 `.interviewtwin/installations/<host>.json`，核对 `updater.files` 中的工具哈希，使用 `updater.directory` 指向的保留工具：

```sh
python3 "/已核验的更新工具目录/get.py" --update --home "/实际工作区" --host cursor
```

实际路径来自安装记录，不猜目录哈希。明确只升级能力时附加 `--no-profile`。GitHub 来源和更新工具已经保存在工作区；初次克隆目录默认保留，不影响正常使用和后续更新。清理属于用户另行发起的可选操作，不自动执行。

此入口先检查原来源 commit；同 commit 且能力、人物和更新工具完整时，不下载完整包。有变化时获取一次，并通过原有事务同步能力与绑定人物。旧记录缺少 commit 时，首次更新需要获取内容以完成迁移。

## 人物资料如何保护

- 随包 assets 是审核快照的只读初始化材料，用户自己的资料写入工作区 `people/`。
- 首次加载只补齐缺失人物；已有正式人物保持原版本，不在面试中自动更新。
- 同 ID 的本地草稿、未绑定的不同快照和修改过的正式资料不会被自动接管或覆盖。
- 新人物版本保留旧快照，自建人物、草稿与本地原件不被删除。
- 人物降级、同版本异内容或其他来源造成的版本冲突会阻止自动覆盖。
- 全局 Skill 可以服务多个工作区，各工作区人物独立。

资料可读、模型已加载和回答质量是不同验证结果。更新后按宿主需要刷新会话，并实际读取人物确认版本。

## 常见问题

### 已经有 InterviewTwin-installer 文件夹

不要反复执行 git clone，也不要删除未知内容。确认它是原仓库的干净副本后，执行原命令中 `&&` 后的安装部分；副本陈旧时，由 Agent 核对来源后获取目标版本。

### GitHub 访问失败或证书校验失败

保留已有安装，报告实际失败环节。同一错误不要循环重试，不关闭 TLS 校验，不改用未知镜像。

终端的 Git 路径不依赖 Python HTTPS 下载。确需备用下载时，使用已审核的 get.py 并省略 `--source`，明确选择 `--transport zip`；ZIP 路径优先使用系统 curl，再使用 Python HTTPS。备用路径仍失败时停止，可改用审核后的完整离线包。

只有实际使用 Python HTTPS 且证书校验失败时，才检查对应 Python 的 CA 配置；python.org 的 macOS 安装包可使用对应版本目录中的 `Install Certificates.command`。不要在未确定 Python 来源时盲目修改证书。

### 文件已安装，但 Agent 找不到 Skill

确认打开的是实际使用工作区，安装位置符合目标宿主要求，再按宿主提示刷新或新建会话。不要通过反复下载和重装来处理会话刷新问题。

### 更新提示人物资料冲突

保留原资料，不删除人物目录、清单或绑定记录来绕过检查。由 Agent 说明冲突位置，待明确处理方式后继续。

### 旧版安装器无法读取人物格式

0.1.12及更早安装器不支持 schema 2。先从原来源读取并审核新版安装入口完成迁移，不删除原件或人物来强行更新。

## 维护者：生成随包人物材料

审核资料以根目录 `profiles/` 为源，不直接修改 assets 生成副本。运行：

```sh
python3 scripts/build_skill_seed.py
```

构建时逐字节复制已审核人物；发布前核对两份文件集合、清单和哈希一致。种子不包含草稿、评测答案或私人运行记录。

具体安装与宿主验证范围见[安装验证报告](docs/安装验证.md)。
