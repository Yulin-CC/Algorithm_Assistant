---
name: standard-git-repo
description: >-
  Git 仓库规范，本地基线与远程推送一条线。建仓库 / git init / 上版本控制走
  分类、.gitignore 三分法、首次基线快照；提交到远程 / push / 同步 GitLab 走
  凭据校验、脱敏（占位符进 index、工作区还原本机值）、推送。含密钥红线、
  Windows 口径、日常快照与回滚。Use when 建仓库, git init, 上版本控制,
  这个项目还没 git, 提交到远程, push, 同步 GitLab, 同步 GitHub.
---

# 🧾 Git 仓库规范

  - **概述**: 一个目录从「没有版本控制」到「推上远程」的完整口径。前半段是**本地基线**：先分类哪些文件不该进库，写 `.gitignore`，再 `git init`，拍第一个快照。后半段是**远程提交**：校验凭据、脱敏、推 GitLab / GitHub。两段共用同一份忽略清单和同一条密钥红线。**本机是 Windows**，命令一律给 PowerShell 写法；服务器仓上的操作换 bash 写法的对应命令。
  - **日期**: 2026-11-26

---

## 0 触发与前置

  - **触发词（本地）**：建仓库、git init、上版本控制、这个项目还没 git、整理成规范仓库。
  - **触发词（远程）**：提交远程、push、同步 GitLab、同步 GitHub。
  - **分流**：先跑 `git rev-parse --is-inside-work-tree`。
    - 返回 `true`：已有仓库。要建槽、改仓内文件 → 直接看 §8；要推远程 → 从 §4 开始。
    - 报错 `not a git repository`：按 §1 → §3 建基线，再进 §4。

  **(1)** 确认仓库边界，别把仓建错层：

    ```powershell
    git rev-parse --show-toplevel    # 已在仓内时看根在哪
    ```

  - 一个目录是另一个仓的子目录时，`rev-parse` 会返回**父仓**的根。这种情况不要在这个目录再 `git init`，先和用户确认要建独立仓还是留在父仓。

  **(2)** 本产线的硬约束：

  - `Algorithm_Assistant` 根**不在本机建仓**。对外发布的干净仓只放服务器（`workarea/env-*/projects.md` 记地址），本机 `.cursor/` 不是干净仓。
  - 算法仓上的 `0-Agent-demo/`、`config/`、`data/` 改动前，先确认该仓已有基线，否则这一轮改动不可回滚。`standard-project_agentdemo` 会来读本节。

  **(3)** 新开的 shell 里 `git` 可能不在 PATH 上：

    ```powershell
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
      $env:PATH += ';' + (Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd')
    }
    git --version
    ```

  - 只影响这一次会话，不写进全局 PATH，也不用 `setx`。装 Git 时没勾「加入 PATH」就会这样；`git --version` 能打出版本号再往下走。

  - **原则**：`git init` 只新增 `.git/`，**不改动任何业务文件**。真正的风险不在 init，而在「哪些文件被装进第一个提交」。

---

## 1 先分类，再 init

  第一个提交一旦落下，历史里就永久带着它装过的所有内容。所以顺序固定是 **先写 `.gitignore`，再 `git init`**。反过来做，`git add -A` 那一刻就已经把该挡的东西装进去了。

### 1.1 `.gitignore` 三分法

  按「为什么不该进库」分三类，逐类确认，不要凭印象随手加：

  | 类别 | 典型条目 | 为什么 |
  |------|----------|--------|
  | **运行产物** | `.venv/`、`__pycache__/`、`*.py[oc]`、`dist/`、`build/`、`logs/`、`tmp/`、`runs/`、`_tmp/` | 可重建、天天变，进库只会让 diff 全是噪音 |
  | **数据与业务资料** | `data/`、`customer/`、`datasets/`、`weights/`、`*.ckpt`、`*.pth`、`*.parquet` | 体积大、含客户信息或行踪轨迹，不该随代码分发 |
  | **密钥与凭据** | `.env`、`*.key`、`*.pem`、`credentials.json`、`config/*secret*.json`、`**/mcp.json`（含 token 时） | 泄露即账单风险；历史不可撤回，见 §2 |

  **(1)** 本产线额外要挡的，单独一组写清理由：

    ```gitignore
    # 运行产物
    .venv/
    __pycache__/
    *.py[oc]
    logs/
    tmp/
    _tmp/

    # 数据与业务资料
    customer/
    data/
    weights/
    0-Agent-demo/

    # 密钥与凭据
    .env
    src/*/config/mcp.json

    # 组内房间与本机运行态
    room.md
    online.json
    .room.lock
    ```

  - `customer/` 下是客户票和历史路径，`room.md` / `online.json` 是本机房间运行态。这两类都不该随代码分发。
  - 算法仓的 `0-Agent-demo/` 含本轮数据入口和权重指向，进库会让每个仓都带一份别人的训练记录。

  **(2)** 写文件时的编码硬要求：

    ```powershell
    # 只有这一种写法 git 一定认得
    @(
      '__pycache__/'
      'tmp/'
    ) | Set-Content .gitignore -Encoding utf8
    ```

  - **禁止**用 `>` 或 `Out-File -Encoding Unicode` 写 `.gitignore`。实测 PowerShell 5.1 的 `>` 写出 UTF-16LE，git **静默不认**：`git check-ignore -v <file>` 返回 exit 1，文件照旧挂在 `??` 里，没有任何报错。
  - 写完必须验一次：

    ```powershell
    git check-ignore -v tmp
    ```

    返回一行 `<规则> <路径>` 才算生效；无输出就是没读到 `.gitignore`，回头查编码。

### 1.2 检查三个硬指标

  **(1)** 看清忽略有没有真的生效。注意 `--ignored` 和 `-uall` 缺一不可：

    ```powershell
    git status --short --ignored -uall
    ```

  - 不加 `--ignored`：`!!` 行根本不出现，你会误以为忽略清单没配。
  - 不加 `-uall`：被忽略的整个目录会塌成一行 `!! tmp/`，看不到里面具体有什么。要逐个文件核对时必须带它。
  - 输出对照：`??` 未跟踪 / `M` 已改 / `!!` 已忽略。该忽略的必须出现在 `!!`，而不是还挂在 `??` 里。

  **(2)** 揪大文件（本机没有 `du`，`find` 是 Windows 的 `find.exe`，两者都不能照 Linux 写法用）：

    ```powershell
    Get-ChildItem -Recurse -File -Force -ErrorAction SilentlyContinue |
      Where-Object { $_.Length -gt 5MB -and $_.FullName -notmatch '\\\.git\\' } |
      Sort-Object Length -Descending |
      Select-Object -First 20 @{n='MB';e={[math]::Round($_.Length/1MB,1)}}, FullName
    ```

  - 单个文件 **> 5MB** 默认不进库（二进制、模型、数据），确需版本化改走 Git LFS 并在 README 注明。

  **(3)** 排除嵌套仓。子目录里已有 `.git` 时，`git add -A` 会**静默**把那个目录记成一个 `160000` 的 gitlink（只记一个 commit 号，不记内容），clone 下来是一个空壳目录，且不报错。

    ```powershell
    Get-ChildItem -Recurse -Directory -Force -Filter .git -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty FullName
    ```

  - 输出里有任何一条落在本仓内（不是本仓根自己的 `.git`），先把它写进 `.gitignore`，或确认要当 submodule。两个都不是，就先停下问用户。
  - 已经误加的，按 `git rm --cached <目录>` 撤出 index（文件不动）。

---

## 2 密钥红线（最容易犯且不可逆）

  **commit 是快照，写进历史就改不掉。** 提交了密钥之后，即使 `git rm --cached` 再提交一次，历史里那条 commit 仍然带着它：

  ```powershell
  git log --oneline --all -- secret.txt    # 依然翻得出来
  ```

  正确顺序只有一种：**第一次提交前就排除**。

  - 配置文件里带密钥的，仓库里放 **模板**，实体文件忽略：

    ```text
    config/mcp.json           # 真实值，忽略
    config/mcp.example.json   # 占位符，进库
    ```

  - 模板里把 token 换成 `<YOUR_TOKEN>`，并在 README 的「环境搭建」里写明怎么生成。
  - 已经误提交的，**不要**用 `git rm --cached` 假装解决。要么轮换密钥（推荐，成本最低），要么重写历史（`git filter-repo`，需单独评审）。
  - 私钥文件（`*.pem`、`id_rsa`）不要提交，也不要为了「先跑起来」临时加进去。

---

## 3 首次提交

    ```powershell
    git init -b main
    git config user.name  "<name>"
    git config user.email "<email>"

    git add -A
    git status --short          # 落笔前最后看一眼装了什么
    git commit -m "chore: 初始化仓库，数据与密钥不进版本库"
    ```

  - **分支**：必须带 `-b main`。本机没有 `~/.gitconfig`，裸 `git init` 出的是 `master`，而 §6 / §7 全程按 `main` 和 `yulin-dev` 推，分支名对不上会推成一个空分支。
  - **身份**：`git config` 不带 `--global`。只在当前仓库写，不动用户的全局配置。用户确认要改全局时才加 `--global`。
  - **`git add -A` 只允许这一次**。首次提交没有历史可污染，整仓打包才安全。日常提交**禁止** `git add .` / `git add -A`，走 §8，理由见 §5.3。
  - **提交信息**：`<类型>: <做了什么>`，类型用 `feat` / `fix` / `docs` / `chore` / `refactor` / `test`。中英文皆可，但一次提交只说一件事。
  - **粒度**：搬文件、改行为、改格式不要混在同一个 commit 里，否则 diff 无法审查。
  - **落笔前必看** `git status --short`，确认没有 `customer/`、`.env`、`*.key`、`tmp/` 混在待提交列表里。有就先修 `.gitignore`，不要靠 `git commit` 之后再补救。

  **(1)** 关于 `warning: LF will be replaced by CRLF`：

  - 本机 `core.autocrlf=true`，首次提交几乎每个文本文件都会打这条。属正常，不影响历史内容。
  - 但跨机协作（服务器上跑 Linux）时，同一条警告意味着同一个文件在两台机器上会来回显示为「已修改」。这类仓必须写 `.gitattributes`，把行尾固定下来：

    ```gitattributes
    # 统一文本判定与行尾
    * text=auto eol=lf

    # Windows 专用脚本保留 CRLF
    *.bat text eol=crlf
    *.cmd text eol=crlf
    *.ps1 text eol=crlf

    # 二进制不做转换
    *.png binary
    *.jpg binary
    *.pt binary
    *.onnx binary
    *.zip binary
    ```

  - 加了之后要跑一次 `git add --renormalize .`，把已跟踪文件按新规则重写。**先看 `git status --short` 和 `git diff --cached --numstat`**：纯行尾转换的特征是每个文件的增删行数相等（如 `341 341`）。若某文件增删不等，说明内容也变了，得单独查。这类提交单独一条，不要和功能改动混在一起。
  - 中文文件名在 `git status` 里显示成 `"\345\274\200\345\217\221..."` 时，是这个仓没关 `core.quotepath`。设一次即可：

    ```powershell
    git config core.quotepath false
    ```

  - 纯 Windows 的仓不用 `.gitattributes`；但只要服务器上也提交，就一定要。

  **(2)** 提交后再核一遍，四件事都要成立：

    ```powershell
    git branch --show-current                       # main
    git ls-files | Select-String '^(customer|tmp|_tmp)/'   # 应无输出
    git ls-files -s | Select-String '^160000'       # 应无输出（无 gitlink）
    git log --oneline                               # 至少一条
    ```

---

## 4 remote 与凭据

  - **认证方式**：统一 **HTTP/HTTPS** + Token；`credential.helper=store` 缓存于 `~/.git-credentials`。
  - **remote 命名**：`github`（个人）、`gitlab`（团队）；`<仓库标识>` 是 `git remote` 别名，不是分支名。
  - **默认分支策略（双远程）**：
    - **GitHub**：只维护 `main`，**不要**保留 `yulin-dev`。本地在 `yulin-dev` 开发时，用 `git push github yulin-dev:main` 快进到 `main`；若 GitHub 上已有 `yulin-dev`，push 后 `git push github --delete yulin-dev`，本地跟踪改回 `gitlab/yulin-dev`。
    - **GitLab**：保留 `yulin-dev`。push 到 `gitlab yulin-dev`，再通过网页 **Merge Request** 合进 `main`（见 §7.2）。合完默认**不删** GitLab 的 `yulin-dev`。
  - **凭据安全（强制）**：
    - **禁止**在对话中向用户索要 Token，**禁止**接受用户在聊天里粘贴的 Token。
    - **禁止**将 Token 写入 shell 命令、`echo`、日志或任何 Agent 可回显的输出。
    - 新仓库 / 目标平台无缓存凭据时，**停止 push**，仅指引用户**在本机终端自行**配置（见 §4.3），配置完成后再继续。
  - **注意**：未经用户明确同意，不得 `git push --force`；受保护分支被拒绝时，改用 `pull --allow-unrelated-histories` 合并。

### 4.1 检查 remote 与凭据

  - 在项目根目录执行。只判断凭据**有没有**，不读、不打印内容：

    ```powershell
    git rev-parse --is-inside-work-tree
    git config user.name
    git config user.email
    git config --global credential.helper
    git remote -v
    Test-Path "$HOME\.git-credentials"
    Select-String -Path "$HOME\.git-credentials" -Pattern 'github\.com' -Quiet -ErrorAction SilentlyContinue
    Select-String -Path "$HOME\.git-credentials" -Pattern '<gitlab-host>' -Quiet -ErrorAction SilentlyContinue
    git status -sb
    ```

  - `<gitlab-host>` 取自 `git remote get-url gitlab` 的域名（如 `doc.geoai.com`）。
  - **禁止** `Get-Content "$HOME\.git-credentials"`。要看的话只看有没有对应主机，`Select-String -Quiet` 返回布尔即可。

### 4.2 缺少 remote 时

  - 指引用户新建链接：

    ```powershell
    git remote add <仓库标识> <远程仓库URL>
    # 例：git remote add gitlab http://doc.geoai.com:5002/geoai/ai/yoloe.git
    ```

  - 加远程之前回头确认 §2：历史里没有密钥，否则推上去等于公开。

### 4.3 缺少凭据时（用户自行写入）

  - 触发条件：目标 `<仓库标识>` 对应主机在 `~/.git-credentials` 中**无记录**，或 push 报 `could not read Username` / 认证失败。
  - **立即停止**，不得继续 push；向用户说明「该平台凭据未缓存」，并给出以下指引（**对话中不出现 Token 字样以外的敏感信息，不索要 Token**）：

  **(1)** 在平台创建访问凭据

  | 平台 | 创建路径 | 所需权限 |
  | ---- | -------- | -------- |
  | GitHub | Settings → Developer settings → Personal access tokens | `repo` |
  | GitLab | Settings → Access Tokens | `write_repository` |

  **(2)** 用户在本机终端自行写入（Agent **不得代写**）

    ```powershell
    git config --global credential.helper store

    # 将 <平台用户名> 与 <访问凭据> 替换为实际值后，在本机终端执行：
    # 注意：必须是 https://（两个斜杠），写成 https: 会导致认证失败
    Add-Content -Path "$HOME\.git-credentials" -Value "https://<平台用户名>:<访问凭据>@github.com"

    # GitHub 占位符（切勿把真实凭据写进 Skill 或对话）：
    # Add-Content -Path "$HOME\.git-credentials" -Value "https://<GitHub用户名>:<PAT>@github.com"

    # GitLab 占位符：
    # Add-Content -Path "$HOME\.git-credentials" -Value "https://<平台用户名>:<访问凭据>@doc.geoai.com:5002"
    ```

  **(3)** 用户回复「已配置」后，Agent 执行 §5.4 连通性与 Token 校验；通过后再进入 §5。

  - **注意**：
    - 缺少 remote 或凭据时**停止**，等用户自行补全并确认后再继续。
    - 凭据行格式必须为 `https://用户名:凭据@主机`；`https:`（少一个 `/`）会导致 `could not read Username`。
    - 若用户在聊天中误发凭据，**不要**写入文件或回显；提醒其立即在平台撤销并重新生成。

---

## 5 打印现状并与用户确认

### 5.1 收集远程信息

  - 先 fetch，再对比本地与远程差异：

    ```powershell
    git fetch --all
    git branch -a
    git log --oneline HEAD..<仓库标识>/<分支>   # 远程有、本地无
    git log --oneline <仓库标识>/<分支>..HEAD   # 本地有、远程无
    ```

  - 向用户打印（凭据仅说明「已缓存 / 未缓存」，禁止输出明文、禁止索要）：
    - `user.name` / `user.email`
    - 各 `<仓库标识>` → URL
    - 本地当前分支、候选远程分支
    - `git status` 摘要
    - 远程是否领先（需 pull）

### 5.2 必须逐项确认

  - 使用 AskQuestion 或对话，拿到以下确认前**不得 push**：

    - **a.** 提交到哪个 `<仓库标识>`？默认：GitLab → `yulin-dev`；GitHub → `main`（不要 GitHub `yulin-dev`）。是否新建分支？
    - **b.** 远程该分支有更新时，先 **pull** 还是覆盖（覆盖需明确授权 force push）？
    - **c.** 是否修改 `user.name` / `user.email`？（默认不改 git config）
    - **d.** 读 `README.md`「更新日志」与 `git diff --stat`，拟定 commit message 并请用户确认。
    - **e.** 按 §5.3 扫描本机路径、IP、Token/Key。进 Git 的必须是占位符，工作区保留本机值。列出命中后执行；用户当次点名「这条保留」的除外。

  - commit message 拟定规则：
    - 优先对照 `README.md` 更新日志
    - 无对应条目时，根据 `git diff --stat` 一句话概括
    - 示例：`docs: 更新 README 开集训练说明`、`feat: 新增 data/create_data.py`

### 5.3 提交内容脱敏（占位符进 Git，本机值留在工作区）

  - **时机**: §5.2 确认仓库 / 分支之后、`git add` / `commit` / `push` **之前**。
  - **目的**: 本机可以写真实路径、地址、密钥；**推到 Git 上的版本只能是占位符**。提交完成后，工作区文件必须仍是本机原值。
  - **原则**: 先列出命中。默认这些命中只以占位符进入 index，磁盘上的原值马上还原。用户当次点名「这条保留」的不替换。禁止把整份本机值 `git add` 后直接提交。

  **(1)** 扫描即将提交的文本（含未跟踪、已修改；尊重 `.gitignore`）。排除 `z-others/`、`third_party/`、`.git/`、`customer/`、`agents/TeamLeader/`、`tmp/`。仓库内源码相对路径（如 `util/app.py`）不替换。

  - 后两类是本产线特有：`customer/` 各票的 `todo.md` / `require.md` 和 `agents/TeamLeader/HANDOFF-*.md` 是本机路径与主机地址最密的地方（单文件可达 20 处），不排除会让扫描列表被票和交接文件淹掉，真该看的源码反而漏掉。

  | 检查 | 要替换 | 不替换 |
  | ---- | ------ | ------ |
  | 本机路径 | 绝对路径（`/home/...`、`/data/...`）、`~`、盘符（`C:\`、`Z:\`）、指向仓库外数据或环境的相对路径 | `util/app.py` 这类仓库内相对路径 |
  | IP | 具体 IPv4 / IPv6，含写在 URL 里的 | `0.0.0.0`、`127.0.0.1` |
  | Token / Key | `api_key`、`token`、`secret`、`password` 的赋值；`ghp_`、`github_pat_`、`glpat-`、`sk-`、`AKIA`、`Bearer` 等前缀 | 文档里的占位符本身（`<token>`、`<api-key>`） |

  - **代码里的路径白名单是例外，保留真值**。像 `tools/0-General/1-LocalMachine/util/paths.py` 里 `Path("/path/to/data")` 这种，是程序运行要读的默认根，改成占位符会让代码直接失效；它也不是「文档里的机器信息」。判断口径：**写给人看的路径要脱敏，写给程序读的路径保留**。同一类文件在 `.skill/SKILL.md` 的说明里引用同一个值，也一并保留，并在技能里写明这条例外。

    ```powershell
    $EX = @('-g','!z-others/**','-g','!third_party/**','-g','!.git/**','-g','!customer/**','-g','!agents/TeamLeader/**','-g','!tmp/**')

    rg -n --no-messages '/home/[^/[:space:]]+/|~/|[A-Za-z]:[\\/]' @EX
    rg -n -i --no-messages '(api[_-]?key|secret|access[_-]?token|password|passwd)\s*[:=]\s*[\x22\x27][^\x22\x27<][^\x22\x27]{5,}' @EX
    rg -n --no-messages 'ghp_|github_pat_|glpat-|sk-|AKIA|Bearer ' @EX
    rg -n --no-messages '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' @EX
    ```

  - **注意**：PowerShell 里不要写 `2>/dev/null`。它会去找 `D:\dev\null` 并报错。`rg` 用 `--no-messages` 静音；其余命令用 `-ErrorAction SilentlyContinue`。
  - **注意**：引号在 PowerShell 里会吃掉一半。密码那条用 `\x22` / `\x27` 写引号，不要写 `["']`——实测在双引号包里会被剥成 `[]`，正则直接失效且不报错。
  - **注意**：盘符那条要写 `[A-Za-z]:[\\/]`。写成 `[A-Za-z]:\\` 只认反斜杠，`D:/xxx` 这种正斜杠写法会漏。

  **(2)** 检查 `0-Agent-demo/`：应写入 `.gitignore`，且不得出现在 `git status` 待添加列表。若仍被跟踪，经用户确认后执行 `git rm -r --cached 0-Agent-demo`。私钥文件（`*.pem`、`id_rsa`）不要提交，停下来问用户。

  **(3)** 占位符对照：

  | 类型 | 工作区（保留） | Git 中写成 |
  | ---- | -------------- | ---------- |
  | conda | `source /path/to/home/miniconda3/etc/profile.d/conda.sh` | `source /path/to/miniconda3/etc/profile.d/conda.sh` |
  | 脚本数据路径 | `dataset="/path/to/home/0-data/..."` | `dataset="/path/to/dataset"` |
  | 其它本机路径 | `/path/to/home/...`、`/data/...`、`Z:\...` | `/path/to/...` |
  | IP / 服务地址 | `http://192.168.1.10:8081/v1` | `http://<ip>:8081/v1` |
  | Token / Key | 真实密钥字符串 | `<token>` 或 `<api-key>` |
  | 密码 | 真实密码 | `<password>` |

  **(4)** 只把占位符写入 index，随即还原工作区。顺序固定，不能省「改占位符」或「恢复」：备份 → 只改命中处 → `git add` → **立刻**用备份盖回工作区 → 再 `git commit`。备份放在仓库外；提交失败也要还原，不要把占位符留在磁盘上。

    ```powershell
    # 本机（Windows）
    $backup = Join-Path $env:TEMP ("git-sanitize-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    # 对每个命中文件（路径相对于仓库根，$file 如 'config/mcp.json'）：
    New-Item -ItemType Directory -Force -Path (Join-Path $backup (Split-Path $file -Parent)) | Out-Null
    Copy-Item -LiteralPath $file -Destination (Join-Path $backup $file) -Force
    # 1. 工作区暂时改成占位符（只改命中处，其余不动）
    #    $t = [IO.File]::ReadAllText((Resolve-Path $file))
    #    $t = $t -replace '/path/to/home/miniconda3', '/path/to/miniconda3'
    #    [IO.File]::WriteAllText((Resolve-Path $file), $t, (New-Object System.Text.UTF8Encoding($false)))
    # 2. 这一版写入 index
    git add -- $file
    # 3. 立刻恢复工作区。commit 读 index，磁盘回到本机原值
    Copy-Item -LiteralPath (Join-Path $backup $file) -Destination $file -Force
    ```

  - 写占位符时用 `[IO.File]::WriteAllText` 配 `UTF8Encoding($false)`，不要用 `Set-Content -Encoding utf8`：后者在 PowerShell 5.1 会加 BOM，`.sh` 和 `.py` 进 index 后首行会多三个字节。
  - 仓库在服务器上时，备份、改占位符、`git add`、恢复都在该仓库目录用 bash 做（`cp` / `sed -i` / `git add` / `cp` 回），不要另拷一份到别的机器冒充恢复。

  **(5)** 提交后核对，两项都要成立：

    ```powershell
    git show HEAD:<file>          # 里是占位符，没有本机路径、具体 IP、真实 Token/Key
    ```

  - 工作区 `<file>` 仍是提交前的本机值。
  - 删掉 `$backup`。这些文件在 `git status` 里会再次显示为已修改，这是预期的：磁盘是本机值，HEAD 是占位符。下次提交必须再走本节，**禁止直接 `git add .` 把本机值送进仓库**。

  - **注意**：
    - 无命中则在 §5.2 汇报「脱敏：通过」，不必打断。
    - 禁止为了提交去改掉工作区里的本机值；禁止提交完不还原。`git commit` 之前工作区必须已经恢复。
    - 这次 diff 没碰到的旧文件，不要为了脱敏去改；它们留到下次被修改时再走本节。
    - 本检查不能替代 `.gitignore`；`0-Agent-demo/` 必须被忽略。

### 5.4 连通性与 Token 校验

  - **时机**: 用户 §5.2 / §5.3 确认后、§6 执行 `add` / `commit` / `push` **之前**；凭据刚配置完（§4.3 步骤 3）亦执行本节。
  - **目的**: 提前发现「凭据格式错误 / Token 失效 / 无写权限 / 网络不通」，避免 commit 完成后才 push 失败。
  - **原则**: 全程 `GIT_TERMINAL_PROMPT=0`（禁止交互式索要凭据）；**禁止**读取或输出 `~/.git-credentials` 明文。

  - 在项目根目录**顺序执行**（将 `<仓库标识>`、`<分支>` 替换为用户确认值）：

    ```powershell
    $env:GIT_TERMINAL_PROMPT = 0
    $url  = git remote get-url <仓库标识>
    $host_ = ([uri]$url).Host

    # A. 凭据是否已缓存
    if (-not (Select-String -Path "$HOME\.git-credentials" -Pattern ([regex]::Escape($host_)) -Quiet -ErrorAction SilentlyContinue)) {
      Write-Host "FAIL: 凭据未缓存 ($host_)"; exit 1 }

    # B. 凭据行格式（常见错误：写成 https: 而非 https://）
    if (-not (Select-String -Path "$HOME\.git-credentials" -Pattern ([regex]::Escape($host_)) |
              Where-Object { $_.Line -match '^https?://' })) {
      Write-Host "FAIL: 凭据格式错误，须为 https://用户名:凭据@主机"; exit 1 }

    # C. git 能否读取凭据（仅看 exit code，不回显）
    "url=$url" | git credential fill | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: git 无法读取凭据"; exit 1 }

    # D. 仓库可达 + Token 读权限
    git fetch <仓库标识>
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: fetch 失败（网络或 Token 读权限）"; exit 1 }

    # E. Token 写权限（dry-run，不实际上传对象）
    git push --dry-run <仓库标识> <分支>
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: push dry-run 失败（Token 无效或无写权限）"; exit 1 }

    Write-Host "OK: 连通性与 Token 校验通过"
    ```

  - **失败处理**（停止 §6，不得继续 push）：

    | 现象 | 可能原因 | 处理 |
    | ---- | -------- | ---- |
    | `FAIL: 凭据未缓存` | `~/.git-credentials` 无对应主机 | → §4.3 |
    | `FAIL: 凭据格式错误` | `https:` 少 `/` 或缺少协议头 | → §4.3，强调 `https://` |
    | `FAIL: git 无法读取凭据` | `credential.helper` 未配置或格式损坏 | → §4.3 |
    | `could not read Username` | 同上，多为格式错误或 helper 未生效 | → §4.3 |
    | `Authentication failed` / `403` / `Invalid username or token` | Token 过期或权限不足 | → §4.3，提示重新生成并检查 `repo` / `write_repository` |
    | `fetch` 超时 | 网络问题 | → §6.1 网络超时配置后重试 §5.4 |

  - **向用户汇报**（仅说明通过 / 失败原因，禁止输出凭据）：
    - 目标 `<仓库标识>` / URL / `<分支>`
    - 各项检查结果：`凭据缓存` / `凭据格式` / `credential fill` / `fetch` / `push --dry-run`
    - 全部通过后方可进入 §6

---

## 6 提交与推送

  - **前置条件**: §5.3 已把占位符写入 index，并且工作区已恢复成本机原值；§5.4 连通性校验已通过。
  - 用户确认后，在项目根目录**顺序执行**。含本机路径 / IP / Token / Key 的文件**不要**在这里再次 `git add`（否则会把刚还原的本机值盖掉 index 里的占位符）。仓库在服务器上时，恢复的就是服务器上这份工作区：

    ```powershell
    # 仅当 §5.2 c 确认要改身份时才执行，且默认只写仓库级
    git config user.name  "<用户名>"
    git config user.email "<用户邮箱>"

    git checkout "<分支>"
    # 新建分支：git checkout -b "<分支>"

    git fetch <仓库标识>
    git pull <仓库标识> <分支> --no-rebase

    # 仅添加 §5.3 判定无命中的文件；命中文件已在 §5.3 用占位符 git add 并还原
    git add <无命中文件>
    git commit -m "<message>"

    git push -u <仓库标识> <分支>
    ```

  - **注意**：身份默认不动；若 §5.2 b 选择暂不 pull，跳过 `git pull`；无 staged 改动时跳过 `git commit`，直接 push。

### 6.1 异常处理

  - **`rejected (fetch first)`**（远程有 Initial commit）：

    ```powershell
    git pull <仓库标识> <分支> --allow-unrelated-histories --no-rebase --no-edit
    git checkout --ours README.md && git add README.md
    git commit -m "Merge remote initial commit"
    git push -u <仓库标识> <分支>
    ```

  - **protected branch 拒绝 force push**：仅 pull 合并，不要 force。

  - **认证失败**（`could not read Username`、`Authentication failed`、`403`）：
    - 若 §5.4 已执行仍失败（极少见，如 Token 中途失效）：回到 §4.3，指引用户自行写入凭据；**不得**在对话中索要或接收凭据后重试。

  - **网络超时**（`HTTP 408`、`RPC failed`）：可调大缓冲后重试，**不涉及凭据**：

    ```powershell
    git config --global http.postBuffer 524288000
    git config --global http.lowSpeedLimit 0
    git config --global http.lowSpeedTime 999999
    git config --global http.version HTTP/1.1
    ```

---

## 7 双仓库维护

  同时维护 GitLab + GitHub 时，**默认**：

  | 远程 | 日常分支 | 合进主干 |
  | ---- | -------- | -------- |
  | `gitlab` | 保留 `yulin-dev` | 网页 MR → `main`（§7.2） |
  | `github` | **只有** `main` | 本地 `yulin-dev` 快进推到 `github/main` |

  - **pull**：只从 `gitlab` 拉团队更新（`git pull gitlab yulin-dev --no-rebase`）。
  - **push 俩远程**（在 `yulin-dev` 上 commit 之后）：

    ```powershell
    git push gitlab yulin-dev
    git push github yulin-dev:main
    git push github --delete yulin-dev
    git branch -u gitlab/yulin-dev
    ```

  - **注意**：
    - 禁止给 GitHub 长期留 `yulin-dev`；`git push -u github yulin-dev` 会把本地跟踪改到 GitHub，推完必须 `-u gitlab/yulin-dev` 改回来。
    - GitHub `main` 可快进时不要 force；不能快进则先说明，未经同意不得 `--force`。
    - GitLab 的 `main` **不要**直接 push（受保护时用 MR）。
    - 远程没有 `yulin-dev` 时 `--delete` 会报 `remote ref does not exist`，属正常，可忽略。

### 7.1 GitHub：合进 main

    ```powershell
    git fetch github
    git log --oneline github/main..HEAD    # 将推上去的提交
    git push github HEAD:main              # 或 yulin-dev:main
    git push github --delete yulin-dev     # 远程有该分支才执行
    ```

### 7.2 GitLab：MR 合进 main（教用户点网页）

  Agent **默认不代替点 Merge**（除非用户明确说「帮我在 GitLab 上合」且有 API）。教用户：

  **(1)** 创建 MR：`Merge requests` → `New merge request`
  Source = `yulin-dev`，Target = `main`。
  快捷：`<gitlab仓库页>/-/merge_requests/new?merge_request%5Bsource_branch%5D=yulin-dev`

  **(2)** 若报 `Another open merge request already exists for this source branch: !N`：
  **不要新建**，打开已有 `!N`（源分支 push 后会自动带上最新 commit）→ Approve（如需要）→ **Merge**。

  **(3)** Merge 建议用 **Merge commit**（与历史 `Merge branch 'yulin-dev' into 'main'` 一致）。
  **不要勾** Delete source branch（GitLab 要保留 `yulin-dev`），除非用户当场说删。

  **(4)** 合完本地如需同步 `main`：

    ```powershell
    git fetch gitlab
    git checkout main
    git pull gitlab main --no-rebase
    git checkout yulin-dev
    ```

  - 需求原文见同目录 `requi.md`，口径以本文件为准。

---

## 8 日常快照与回滚

  基线落好之后，日常只走这一条窄路。

### 8.1 三个动作

  | 动作 | 命令 | 回答什么 |
  |------|------|----------|
  | 看 | `git status --short`、`git diff` | 我改了什么，哪些还没被跟踪 |
  | 拍 | `git add <文件>` ＋ `git commit -m "<类型>: <做了什么>"` | 存一次快照 |
  | 查 | `git log --oneline`、`git show --stat HEAD` | 拍过哪些，最近一次装了什么 |

  - **禁止** `git add .` / `git add -A`。按文件名加入。原因是 §5.3：含本机值的文件提交后磁盘上是原值、HEAD 是占位符，`git status` 里永远显示「已修改」，一个 `git add .` 就把本机路径和密钥重新送进仓库。
  - 一次提交只说一件事：搬文件、改行为、改格式分三次。

### 8.2 提交信息

  - 格式固定为 `<类型>: <做了什么>`。类型只用这一组：`feat` / `fix` / `docs` / `chore` / `refactor` / `test` / `style` / `perf` / `build` / `ci`。
  - 中英文皆可，但**类型前缀不能省**。省了之后 `git log` 没法按类型筛，也没法一眼看出哪条是功能、哪条是整理。
  - 自查命令，返回非空就是有漏的：

    ```powershell
    git log --format="%h %s" | Select-String -NotMatch '^[0-9a-f]+ (feat|fix|docs|chore|refactor|test|style|perf|build|ci)(\(.+\))?: '
    ```

  - 正文说清**为什么改**和**影响什么**，不要只列文件名。用 `-F -` 从 heredoc 读进多行信息，避免 shell 引号吃掉换行：

    ```powershell
    git commit -F - <<'MSG'
    refactor: 服务目录归位，启动与端口解耦

    - 端口与模型名归 server/，启动脚本归 workarea/link.md
    - clients 只读 config，不再硬编码地址
    MSG
    ```

  - **注意**：`git commit -m "a
b"` 在 PowerShell 里换行会被吃掉，多行一定用 `-F -`。

### 8.3 回滚分三级（从轻到重）

    ```powershell
    git checkout -- <file>        # ① 单个文件回到上次提交
    git restore --staged <file>   # ② 撤销 add，文件本身不动
    git revert <commit>           # ③ 整次提交反向抵消，生成新提交（历史保留）
    ```

  - **禁止**在共享分支上用 `git reset --hard` 抹历史；本地未提交的改动会一并丢失。
  - 回滚前先 `git status` 确认手里没有想保留的改动。
  - 已推上去的提交只能 `revert`，不能 `reset`。

---

## 9 自检清单

### 9.1 建基线

  - [ ] `git rev-parse --is-inside-work-tree` 返回 `true`，`--show-toplevel` 指向预期的仓根
  - [ ] `.gitignore` 已写且按 §1.1 三类分好，不是随手堆的
  - [ ] `git check-ignore -v <关键目录>` 有输出（说明编码对、规则真生效）
  - [ ] `git status --short --ignored -uall` 里该忽略的在 `!!`，不在 `??`
  - [ ] `git ls-files` 不含 `customer/`、`data/`、`tmp/`、`.env`、`*.key`、日志
  - [ ] `git ls-files -s` 无 `160000`（没有嵌套仓被塞成 gitlink）
  - [ ] 单个 > 5MB 的文件已排除或走 LFS
  - [ ] 分支是 `main`，`git log --oneline` 至少一条基线提交
  - [ ] 带密钥的配置有 `.example` 模板进库，实体文件被忽略
  - [ ] 服务器也会提交的仓：有 `.gitattributes`，且 `git config core.quotepath` 为 `false`
  - [ ] `git log --format="%s"` 里每条都带类型前缀

### 9.2 推远程

  - [ ] `~/.git-credentials` 有对应主机，格式是 `https://`（不是 `https:`）
  - [ ] `GIT_TERMINAL_PROMPT=0`，全程没有向用户索要凭据
  - [ ] §5.2 五项确认齐全，commit message 用户认过
  - [ ] §5.3 命中项以占位符进 index，工作区已还原本机值，`$backup` 已删
  - [ ] §5.4 五项校验（凭据缓存 / 格式 / `credential fill` / `fetch` / `push --dry-run`）全通过
  - [ ] `git show HEAD:<file>` 里是占位符，磁盘上是本机值
  - [ ] 推完 `git branch -vv` 显示的跟踪分支是预期的那个（GitHub 不留 `yulin-dev`）

---

  按「先分类 → 再 init → 落基线 → 日常快照 → 要备份才加远程」执行。init 本身零风险，风险全在第一个提交装了什么，和每次提交漏了脱敏。
