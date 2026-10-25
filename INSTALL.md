| 字段 | 内容 |
|---|---|
| 作者 | 赵家奇 |
| 日期 | 2026-10-25 |
| 事项 | 同一个仓库链接在不同 Agent 中安装、初始化人物及更新的执行入口 |
| 版本 | v4.3 |

# InterviewTwin 链接安装入口

## Agent 安装入口（安装器 0.2.0）

当前合并交付：能力0.1.21／赵家奇资料1.1.5／安装器0.2.0。安装与更新使用以下统一入口。

收到“安装仓库链接的 Skill”后，先读本文件。已知宿主及当前工作区就直接使用，不扫描其他项目，不搜索电脑上的其他 Agent。仓库页面无法列出文件时，只读取该仓库默认分支的原始 INSTALL.md；可用 Git 的 `ls-remote --symref 仓库 HEAD` 确定默认分支。不要重复获取目录树。只有宿主或目标目录确实不明时才询问。

固定路径：取得一次完整仓库 → 审核 scripts/get.py 与 scripts/install.py → 复用该副本安装 → 检查文件结果 → 在目标宿主确认加载。不要额外安装插件或创建新 Skill。


## 两种安装入口

[README](README.md) 提供使用者可直接复制的入口；本文件说明 Agent 的执行流程、人物初始化、更新保护及故障处理。两种方式使用同一套安装逻辑，均需 Python 3.10+、可访问 GitHub 的网络，以及目标工作区的文件与执行权限。终端方式还需要 Git；开始面试需要目标 Agent 的模型服务可用。

### 方式一：在指定 Agent 中发一句话

在准备使用的 Agent 中打开目标工作区，发送：

> 安装 https://github.com/vanci444-hue/InterviewTwin 的 Skill

Agent 先读取本说明和 README，确定当前宿主与目标工作区，获取并审核安装工具，再按下方“安装执行流程”运行。不需要创建新 Skill 或安装额外插件；不能仅凭电脑装了某个 App 就猜测当前宿主，无法确定时询问。

不要只复制 SKILL.md。完整安装包括通用 Skill、`people/` 人物资料、原 GitHub 来源与后续更新工具。默认人物初始化后，加载 Skill 展示实际可用人物及功能菜单；用户已明确面试或创建任务时直接进入该任务。文件安装完成不等于当前会话已经加载，必要时重新打开目标工作区或新建会话。

### 方式二：在终端执行命令，指定目标 Agent

需要额外安装 Git。以下示例适用于 macOS / Linux 的终端，默认目标为 **Cursor**。先进入你准备存放 InterviewTwin 的目录，确认该目录下没有同名的 `InterviewTwin-installer` 文件夹，然后复制执行：

```sh
git clone https://github.com/vanci444-hue/InterviewTwin.git InterviewTwin-installer && python3 InterviewTwin-installer/scripts/get.py --source InterviewTwin-installer --repo https://github.com/vanci444-hue/InterviewTwin --home "$PWD/InterviewTwin-workspace" --host cursor
```

这条命令只克隆一次完整仓库；安装器核对 origin、目标 commit 和干净状态，然后直接安装该副本，不再下载 ZIP。`InterviewTwin-installer` 存放下载的工具；`InterviewTwin-workspace` 是实际使用工作区，里面保存 Skill、人物资料与更新记录。安装成功后，用目标 Agent 打开 **InterviewTwin-workspace** 文件夹。

将命令最后的 `cursor` 换成对应值即可选择其他 Agent：

| 目标 Agent | `--host` 的值 | 工作区内的 Skill 目录 |
|---|---|---|
| Codex | `codex` | `.agents/skills/interviewtwin/` |
| Cursor | `cursor` | `.cursor/skills/interviewtwin/` |
| Claude Code | `claude-code` | `.claude/skills/interviewtwin/` |
| WorkBuddy 本地代码项目 | `workbuddy` | `.codebuddy/skills/interviewtwin/` |

如果要安装到已有项目，将 `--home` 后的路径替换成该项目的绝对路径并保留引号。当前通过 `--host` 选择 Agent，尚未提供交互选择菜单；这也是项目级安装，不会自动安装到电脑上的所有 Agent。

Windows 用户可使用方式一；以上终端命令未作为 Windows 命令验证。网络访问失败时，检查 GitHub 连通性或使用下载后的本地包，详见下方“安装执行流程”的本地包说明。不要只用通用安装器复制 Skill 目录：本项目还需要独立人物资料初始化。

若提示 `CERTIFICATE_VERIFY_FAILED`，说明 Python 的 HTTPS 证书校验未通过。macOS 使用 python.org 安装包时，可先运行对应 Python 应用目录中的 `Install Certificates.command`；其他安装方式请修复该 Python 环境的 CA 证书配置。Git 正常时优先使用 Git 路径，不必修复 Python HTTPS 才能安装；只有无 Git、无 curl 而使用 Python ZIP 下载时才涉及该配置。不要关闭证书校验。

## 原始资料与人物版本（本轮生效）

每个人物有自己的原件、草稿和确认版本。上传MD/TXT、PDF、PNG/JPG/JPEG/WebP时，先按原字节归档；粘贴文字保存为UTF-8 TXT再归档。每文件上限20MiB；不能读取的格式先说明，不能将上传成功当作解析成功。其他格式的原件目前不进入自动原件包，可在本人同意后转换成支持格式。原件与整理后的知识分别保留，不用AI改写内容替代用户原件。

- `people/<id>/sources/<sha256>/<原文件名>`：创建者本地归档。重复上传复用同字节对象，同名新文件保留为另一对象。原路径不写入分发清单。
- `people/<id>/authoring/draft/{knowledge,sources}`：知识与本次候选原件；修改知识时默认保留草稿已选原件，明确选择空列表才排除。`source-links.json`记录已核对的来源对应。
- `people/<id>/releases/<version>/{knowledge,sources,manifest.json}`：只包含当前指纹经内容确认和披露确认的文件。原件审核的是文件版本及允许提供的内容，不等于自动认定其中每句都正确。
- GitHub/本地分发源仍为`profiles/<id>/`，安装后进入人物的`releases/`；作者的本地归档不会被整体同步给接收者。通用Skill目录不保存人物简历。

默认面试读取知识，查看简历/依据时显式读取当前人物当前版本的`sources/`。来源对应只是证据关联，不意味着整份知识都来自简历；未覆盖的历史理由不能补造。原件和知识存在冲突时停止认领冲突结论，回到创建者确认，不在接收者面试中自动重写知识。

内容确认、披露确认、实际发布仍独立。未审核原件默认排除，界面必须显示实际纳入/排除列表。被排除的原件名称和本地路径不进入分发来源对应。文件或来源对应变化后，相关审核不能自动沿用。

普通更新整体更新原来源的能力和绑定人物快照，包括随包简历。先核验、再切换版本指针；旧版原件、本地归档、草稿和其他人物不覆盖。正式快照里的简历被本地修改时停止更新；失败时恢复原指针并保留原件。只升级能力时完全不写人物文件。新会话实际读取新版后才报告使用生效。

正式分发仓库：https://github.com/vanci444-hue/InterviewTwin。

## 人物schema与旧版迁移

人物schema 2沿用`files`完整SHA256清单，同时允许`knowledge/*.md`和`sources/`中受支持的原件；`source_links`为知识路径到随包原件路径列表。清单与实际文件集合必须完全相等，快照摘要包含manifest和所有原件。schema 1纯知识包继续可读和安装，新增包使用schema 2。不是把原件全文塞入SKILL.md，也不新增数据库或账号系统。

安装器不改写创建者的`people/<id>/sources`归档，仅事务性安装整个版本目录。读取二进制原件时返回实际文件位置、哈希和“未解析”状态，交由宿主读取；Markdown/TXT返回原文。脚本没有OCR或PDF解析器。

0.1.12及更早的保留安装器不支持schema 2。首次迁移时Agent从用户已指定的原分发来源读取新版INSTALL并审核新版安装器，使用新版`scripts/get.py --update`完成迁移；不得运行旧工具失败后删除资料强行覆盖，也不得自动执行未经审核的下载脚本。0.1.13保留的新工具之后按普通一句话更新工作。不同宿主仍分别验收。


以下步骤供收到安装请求的 Agent 执行，不要求面试官自己编辑配置。用户请求安装仅授权本地安装，不授权公开资料或发送消息。

## 安装执行流程

1. 确定当前宿主与工作区，检查 Python 3.10+。宿主参数为 codex、cursor、claude-code、workbuddy。项目级目录映射保持不变。
2. 已有本次获取并审核的完整 Git 仓库时直接复用；否则优先 Git 获取一次。不要搜索无关项目或把作者源码目录当接收者工作区。
3. 审核两份安装脚本，在任意目录运行（路径换成绝对路径）：

```sh
python3 /已审核仓库/scripts/get.py --source "/已审核仓库" --repo https://github.com/OWNER/REPO --home "/实际使用工作区" --host cursor
```

副本必须为独立仓库根目录，origin 匹配指定仓库，目标 commit 匹配 ref，且无修改或未跟踪文件。安装器从该 commit 导出内容并校验，零额外完整下载；会读取远端引用元数据，因此不是离线安装。完整 SHA 为用户明确指定的固定内容标识。HEAD/分支若在下载后移动，会明确停止，不能静默安装另一份内容。

4. 若只有已审核安装器而没有完整仓库，可运行同一命令但省略 `--source`：自动优先 Git，仅获取目标 commit 一次。Git 失败时不自动循环重试；确认故障后只允许明确尝试一次 `--transport zip`，仍失败就停止。无 Git 时直接进入 ZIP 路径，优先 curl，再用 Python HTTPS。所有路径保留 TLS 校验、不使用未知镜像。ZIP 路径继续限制体积、路径及链接，但没有 commit 快捷检查，更新可能再次下载完整包。
5. 纯离线解压包使用 `python3 scripts/install.py --source /包目录 --home /工作区 --host cursor`。其来源如实记录为本地路径，不能标为可信 GitHub 来源；删除本地来源后需重新提供。
6. 输出文件安装状态、能力与人物版本、来源 commit、完整下载次数。当前经审核的 get.py/install.py 单独保存在更新工具目录，记录内容哈希；不回退为下载包中的旧工具，不修改 Skill 或人物资料。
7. 尝试当前会话加载；宿主不能刷新时明确提示打开目标工作区、新建会话说“使用 InterviewTwin”。文件安装通过不等于模型已加载，不循环重装来解决会话发现问题。

失败状态含 category：dependency_or_file_missing、certificate_error、network_or_remote_error、integrity_or_source_conflict。同一错误不重复执行，不遍历电脑寻找证书，不改全局权限。缺依赖、网络、来源不一致与本地修改分别说明；原安装保留。

## 一句话更新

无论通过哪种入口安装，后续都可在实际使用工作区对目标 Agent 说“更新 InterviewTwin”。不要在安装工具下载目录中误建人物工作区，也不需要重复克隆来代替正常更新。

安装器0.2.0起，先校验当前记录中的更新工具哈希，再由保留工具检查原来源 commit；没有变化时不重新读取整仓库或下载完整包。旧安装器迁移仍先读取原来源最新 INSTALL.md，并审核新版工具，不能盲跑旧工具。更新器不兼容时不得删除资料或要求用户编写命令。用户仍只需说“更新 InterviewTwin”，迁移步骤由Agent执行。默认更新原分发来源的通用能力和绑定人物资料，保留接收者自建人物、草稿和旧快照；只有明确要求“只升级能力”时使用 `--no-profile`。绑定身份来自首次安装记录，不固定写死为赵家奇。

Agent 读取工作区 `.interviewtwin/installations/<host>.json`，核对 `updater.files`，从 `updater.directory` 获取保留的 `get.py`，执行 `python3 更新工具路径/get.py --update --home 当前工作区 --host 当前宿主`。工具目录相对于工作区，不能猜测哈希名称。`distribution_profile` 记录分发人物；默认能力和该人物资料在同一事务中更新，一项校验失败不安装另一项。首次下载的临时目录可删除；GitHub 来源、ref 和下载指纹已持久保存。人物来源单独记录，不因导入另一个人物改变既有能力来源。

若使用固定 tag/commit，更新仍指向固定版本；切换到其他版本必须明确新目标。HEAD/分支才跟踪该来源的新内容。旧安装没有来源记录时，从已审核仓库入口补装一次，不猜来源。0.1.11及更早的更新工具默认只升级能力，首次迁移需由Agent使用新源中的 `scripts/get.py --update --home 当前工作区 --host 当前宿主`（不加 `--no-profile`）；新工具能从旧记录唯一同源人物迁移绑定。多个同源人物无法唯一确定时才询问，不猜人物。后续使用新保留工具。

已取得安装器时，可用下载入口合并获取与安装：

```sh
python3 scripts/get.py --repo https://github.com/OWNER/REPO --ref HEAD --home "/实际使用工作区" --host codex
```

`OWNER/REPO` 必须替换为实际审核来源，默认 HEAD 跟随原仓库默认分支；维护者只将审核后的交付内容放入该分支。只有用户明确要求锁定版本时才指定 tag/commit，不能将固定 ref 的重装称为获取最新版。`--no-profile` 仅升级通用能力。下载器只支持公开 HTTPS GitHub 仓库，不接收凭据，不上传或发布。私有仓库通过宿主正常授权下载后执行本地安装。

更新发现正式内容有本地修改时停止覆盖；不得删清单或删人物来强行更新。新版本文件安装与新会话加载分别验证，失败须说明旧版是否仍可用。

## 安装器0.2.0的更新判定

普通更新同步能力与绑定人物。Git 来源保存 repository、ref、实际 commit，来源身份比较忽略 commit 与下载指纹；同一来源的新 commit 更新来源记录，即使能力版本号未变。固定 tag/commit 保持固定，HEAD/分支检查该引用。

同 commit 仅在能力、人物快照、指针和更新工具完整性通过后返回 already_current_pending_session_validation，完整下载次数为0。只有能力更新时不检查或改写人物；人物未同步时，下一次普通更新不能被同 commit 快捷判断跳过。有新 commit 获取一次，复用事务安装器；失败保护原安装、自建人物、原件、草稿与旧快照。旧记录缺 commit 时首次获取一次完成迁移。

安装器独立版本为0.2.0，与能力及人物版本分别记录。更新后仍保留已经审核的工具；如未来升级安装器，需审核新版入口，不直接执行下载包里的脚本。

## 支持边界

- 通用规则使用标准 `SKILL.md` 与相对路径，Python 操作脚本不依赖特定模型 API。各宿主只适配发现目录。
- Codex 项目级目录为 `.agents/skills/interviewtwin/`，Cursor 为 `.cursor/skills/interviewtwin/`，Claude Code 为 `.claude/skills/interviewtwin/`，WorkBuddy 本地代码项目为 `.codebuddy/skills/interviewtwin/`。
- WorkBuddy 的“上传技能”是另一种导入路径：可用专门的 skill-only ZIP，但它不带人物资料；还需在实际工作区初始化人物。不能把云端项目与本地代码项目混为一谈。
- `npx skills add` 等通用安装器通常只复制 Skill 目录。当前人物包位于仓库独立目录，因此不能把“只安装了通用 Skill”当成本产品完整安装；本项目主入口使用本说明完成全部步骤。
- 跨宿主复用不等于回答效果相同。各自的安装、发现、问答、更新与权限须分别验证；当前状态见验收报告。WorkBuddy 由创建者实测。

## 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-10-25 | 建立统一链接入口，明确宿主路径、独立人物初始化、更新保护与验证边界 |
| v1.1 | 2026-10-25 | 保存安装来源和独立更新工具，新增无链接重复输入的更新入口及更新范围说明 |
| v1.2 | 2026-10-25 | 修正普通更新为能力与原分发人物同步更新；仅能力升级可选，补充旧工具迁移 |
| v2.0 | 2026-10-25 | 安装schema 2人物原件，旧安装器先通过审核入口迁移；本轮不发布 |
| v2.1 | 2026-10-25 | 覆盖更新：通用人物评测、默认HEAD与原来源更新策略、实际版本及会话验收；保留v2.0及此前记录，未发布 |
| v3.2 | 2026-10-25 | 覆盖更新：与 README 对齐 Agent 指令与终端命令两种入口，补齐四宿主参数、工作区、证书故障及统一更新说明；安装代码不变 |
| v3.3 | 2026-10-25 | 恢复简短安装指令；宿主识别、人物初始化及核验仍由 Agent 按本说明执行 |
