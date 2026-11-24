---
name: tool-git-remote
description: >-
  Pushes this repo to GitHub/GitLab over HTTPS token after secret scrub and
  connectivity checks. Scrub writes placeholders into the index, then restores
  the working tree to local values before commit. Use when the user says
  提交到远程, push, 同步 GitLab, or 同步 GitHub.
---

# 🔗 Git 远程仓库提交

  - **概述**: 当用户说「帮我把代码提交到远程仓库」「push 一下」「同步 GitLab / GitHub」等时，按本 Skill 执行：**先检查与确认，再校验连通性与 Token，最后提交**。脱敏默认是：进 Git 的那一版改成占位符，`git add` 后立刻把工作区恢复成本机原值，再 `git commit`。
  - **日期**: 2026-11-12

## 1 触发场景与原则

  - **触发词**: 提交远程、push、同步 GitLab、同步 GitHub。
  - **认证方式**: 统一 **HTTP/HTTPS** + Token；`credential.helper=store` 缓存于 `~/.git-credentials`。
  - **remote 命名**: `github`（个人）、`gitlab`（团队）；`<仓库标识>` 是 `git remote` 别名，不是分支名。
  - **默认分支策略（双远程）**：
    - **GitHub**：只维护 `main`，**不要**保留 `yulin-dev`。本地在 `yulin-dev` 开发时，用 `git push github yulin-dev:main` 快进到 `main`；若 GitHub 上已有 `yulin-dev`，push 后 `git push github --delete yulin-dev`，本地跟踪改回 `gitlab/yulin-dev`。
    - **GitLab**：保留 `yulin-dev`。push 到 `gitlab yulin-dev`，再通过网页 **Merge Request** 合进 `main`（见 §6.2）。合完默认**不删** GitLab 的 `yulin-dev`。
  - **凭据安全（强制）**:
    - **禁止**在对话中向用户索要 Token，**禁止**接受用户在聊天里粘贴的 Token。
    - **禁止**将 Token 写入 shell 命令、`echo`、日志或任何 Agent 可回显的输出。
    - 新仓库 / 目标平台无缓存凭据时，**停止 push**，仅指引用户**在本机终端自行**配置（见 §2.2），配置完成后再继续。
  - **注意**: 未经用户明确同意，不得 `git push --force`；受保护分支被拒绝时，改用 `pull --allow-unrelated-histories` 合并。

## 2 检查 remote 与凭据

  - 在项目根目录执行以下命令：

    ```bash
    git rev-parse --is-inside-work-tree
    git config user.name
    git config user.email
    git config --global credential.helper
    git remote -v
    test -f ~/.git-credentials && echo "credentials: yes" || echo "credentials: no"
    # 按目标平台检查是否已有缓存（仅判断有无，禁止读取或输出凭据内容）
    grep -q 'github.com' ~/.git-credentials 2>/dev/null && echo "github cred: yes" || echo "github cred: no"
    grep -q '<gitlab-host>' ~/.git-credentials 2>/dev/null && echo "gitlab cred: yes" || echo "gitlab cred: no"
    git status -sb
    ```

  - `<gitlab-host>` 取自 `git remote get-url gitlab` 的域名（如 `doc.geoai.com`）。

### 2.1 缺少 remote 时

  - 指引用户新建链接：

    ```bash
    git remote add <仓库标识> <远程仓库URL>
    # 例：git remote add gitlab http://doc.geoai.com:5002/geoai/ai/yoloe.git
    ```

### 2.2 缺少凭据时（用户自行写入）

  - 触发条件：目标 `<仓库标识>` 对应主机在 `~/.git-credentials` 中**无记录**，或 push 报 `could not read Username` / 认证失败。
  - **立即停止**，不得继续 push；向用户说明「该平台凭据未缓存」，并给出以下指引（**对话中不出现 Token 字样以外的敏感信息，不索要 Token**）：

    **步骤 1 — 在平台创建访问凭据**

    | 平台 | 创建路径 | 所需权限 |
    | ---- | -------- | -------- |
    | GitHub | Settings → Developer settings → Personal access tokens | `repo` |
    | GitLab | Settings → Access Tokens | `write_repository` |

    **步骤 2 — 用户在本机终端自行写入**（Agent **不得代写**）

    ```bash
    git config --global credential.helper store

    # 将 <平台用户名> 与 <访问凭据> 替换为实际值后，在本机终端执行：
    # 注意：必须是 https://（两个斜杠），写成 https: 会导致认证失败
    echo "https://<平台用户名>:<访问凭据>@github.com" >> ~/.git-credentials

    # GitHub 占位符（切勿把真实凭据写进 Skill 或对话）：
    # echo "https://<GitHub用户名>:<PAT>@github.com" >> ~/.git-credentials

    # GitLab 占位符：
    # echo "https://<平台用户名>:<访问凭据>@doc.geoai.com:5002" >> ~/.git-credentials
    ```

    **步骤 3 — 用户回复「已配置」后**，Agent 执行 §3.4 连通性与 Token 校验；通过后再进入 §3 收集远程信息。

  - **注意**:
    - 缺少 remote 或凭据时**停止**，等用户自行补全并确认后再进入 §3。
    - 凭据行格式必须为 `https://用户名:凭据@主机`；`https:`（少一个 `/`）会导致 `could not read Username`。
    - 若用户在聊天中误发凭据，**不要**写入文件或回显；提醒其立即在平台撤销并重新生成。

## 3 打印现状并与用户确认

### 3.1 收集远程信息

  - 先 fetch，再对比本地与远程差异：

    ```bash
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

### 3.2 必须逐项确认

  - 使用 AskQuestion 或对话，拿到以下确认前**不得 push**：

    - **a.** 提交到哪个 `<仓库标识>`？默认：GitLab → `yulin-dev`；GitHub → `main`（不要 GitHub `yulin-dev`）。是否新建分支？
    - **b.** 远程该分支有更新时，先 **pull** 还是覆盖（覆盖需明确授权 force push）？
    - **c.** 是否修改 `user.name` / `user.email`？（默认不改 git config）
    - **d.** 读 `README.md`「更新日志」与 `git diff --stat`，拟定 commit message 并请用户确认。
    - **e.** 按 §3.3 扫描本机路径、IP、Token/Key。进 Git 的必须是占位符，工作区保留本机值。列出命中后执行；用户当次点名「这条保留」的除外。

  - commit message 拟定规则：

    - 优先对照 `README.md` 更新日志
    - 无对应条目时，根据 `git diff --stat` 一句话概括
    - 示例：`docs: 更新 README 开集训练说明`、`feat: 新增 data/create_data.py`

### 3.3 提交内容脱敏（占位符进 Git，本机值留在工作区）

  - **时机**: §3.2 确认仓库 / 分支之后、`git add` / `commit` / `push` **之前**。
  - **目的**: 本机可以写真实路径、地址、密钥；**推到 Git 上的版本只能是占位符**。提交完成后，工作区文件必须仍是本机原值。
  - **原则**: 先列出命中。默认这些命中只以占位符进入 index，磁盘上的原值马上还原。用户当次点名「这条保留」的不替换。禁止把整份本机值 `git add` 后直接提交。

  **(1)** 扫描即将提交的文本（含未跟踪、已修改；尊重 `.gitignore`）。排除 `z-others/`、`third_party/`、`.git/`。仓库内源码相对路径（如 `util/app.py`）不替换。

    | 检查 | 要替换 | 不替换 |
    | ---- | ------ | ------ |
    | 本机路径 | 绝对路径（`/home/...`、`/data/...`）、`~`、盘符（`C:\`、`Z:\`）、指向仓库外数据或环境的相对路径 | `util/app.py` 这类仓库内相对路径 |
    | IP | 具体 IPv4 / IPv6，含写在 URL 里的 | `0.0.0.0`、`127.0.0.1` |
    | Token / Key | `api_key`、`token`、`secret`、`password` 的赋值；`ghp_`、`github_pat_`、`glpat-`、`sk-`、`AKIA`、`Bearer` 等前缀 | 文档里的占位符本身（`<token>`、`<api-key>`） |

    ```bash
    rg -n '/home/[^/[:space:]]+/|~/|[A-Za-z]:\\\\' \
      -g '!z-others/**' -g '!third_party/**' -g '!.git/**'
    rg -n -i '(api[_-]?key|secret|access[_-]?token|password|passwd)\s*[:=]\s*['\''\"][^'\''\"<][^'\''\"]{5,}' \
      -g '!z-others/**' -g '!third_party/**' -g '!.git/**'
    rg -n 'ghp_|github_pat_|glpat-|sk-|AKIA|Bearer ' \
      -g '!z-others/**' -g '!third_party/**' -g '!.git/**'
    rg -n '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' \
      -g '!z-others/**' -g '!third_party/**' -g '!.git/**'
    ```

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

    ```bash
    backup=$(mktemp -d /tmp/git-sanitize-XXXX)
    # 对每个命中文件（路径相对于仓库根）：
    mkdir -p "$backup/$(dirname "$file")"
    cp "$file" "$backup/$file"
    # 1. 工作区暂时改成占位符（只改命中处，其余不动）
    #    sed -i 's#/path/to/home/miniconda3#/path/to/miniconda3#g' "$file"
    # 2. 这一版写入 index
    git add -- "$file"
    # 3. 立刻恢复工作区。commit 读 index，磁盘回到本机原值
    cp "$backup/$file" "$file"
    ```

    无命中的文件按原样 `git add`。然后 `git commit`。index 里是占位符，工作区已是本机值。仓库在服务器上时，备份、改占位符、`git add`、恢复都在该仓库目录做；恢复的是这份工作区，不要另拷一份到别的机器冒充恢复。

  **(5)** 提交后核对，两项都要成立：

    - `git show HEAD:<file>` 里是占位符，没有本机路径、具体 IP、真实 Token/Key
    - 工作区 `<file>` 仍是提交前的本机值

    删掉 `$backup`。这些文件在 `git status` 里会再次显示为已修改，这是预期的：磁盘是本机值，HEAD 是占位符。下次提交必须再走本节，禁止直接 `git add .` 把本机值送进仓库。

  - **注意**:
    - 无命中则在 §3.2 汇报「脱敏：通过」，不必打断。
    - 禁止为了提交去改掉工作区里的本机值；禁止提交完不还原。`git commit` 之前工作区必须已经恢复。
    - 这次 diff 没碰到的旧文件，不要为了脱敏去改；它们留到下次被修改时再走本节。
    - 本检查不能替代 `.gitignore`；`0-Agent-demo/` 必须被忽略。

### 3.4 推送前连通性与 Token 校验

  - **时机**: 用户 §3.2 / §3.3 确认后、§4 执行 `add` / `commit` / `push` **之前**；凭据刚配置完（§2.2 步骤 3）亦执行本节。
  - **目的**: 提前发现「凭据格式错误 / Token 失效 / 无写权限 / 网络不通」，避免 commit 完成后才 push 失败。
  - **原则**: 全程 `GIT_TERMINAL_PROMPT=0`（禁止交互式索要凭据）；**禁止** `cat` / 输出 `~/.git-credentials` 明文；`git credential fill` 的 stdout **必须**重定向到 `/dev/null`。

  - 在项目根目录**顺序执行**（将 `<仓库标识>`、`<分支>` 替换为用户确认值）：

    ```bash
    export GIT_TERMINAL_PROMPT=0
    url=$(git remote get-url <仓库标识>)
    host=$(echo "$url" | sed -E 's#https?://([^/@]+@)?([^/]+).*#\2#')

    # A. 凭据是否已缓存
    grep -q "$host" ~/.git-credentials || { echo "FAIL: 凭据未缓存 ($host)"; exit 1; }

    # B. 凭据行格式（常见错误：写成 https: 而非 https://）
    grep "$host" ~/.git-credentials | grep -qE '^https?://' || { echo "FAIL: 凭据格式错误，须为 https://用户名:凭据@主机"; exit 1; }

    # C. git 能否读取凭据（仅看 exit code，不回显）
    printf 'url=%s\n' "$url" | git credential fill >/dev/null || { echo "FAIL: git 无法读取凭据"; exit 1; }

    # D. 仓库可达 + Token 读权限
    git fetch <仓库标识> || { echo "FAIL: fetch 失败（网络或 Token 读权限）"; exit 1; }

    # E. Token 写权限（dry-run，不实际上传对象）
    git push --dry-run <仓库标识> <分支> || { echo "FAIL: push dry-run 失败（Token 无效或无写权限）"; exit 1; }

    echo "OK: 连通性与 Token 校验通过"
    ```

  - **失败处理**（停止 §4，不得继续 push）：

    | 现象 | 可能原因 | 处理 |
    | ---- | -------- | ---- |
    | `FAIL: 凭据未缓存` | `~/.git-credentials` 无对应主机 | → §2.2 |
    | `FAIL: 凭据格式错误` | `https:` 少 `/` 或缺少协议头 | → §2.2，强调 `https://` |
    | `FAIL: git 无法读取凭据` | `credential.helper` 未配置或格式损坏 | → §2.2 |
    | `could not read Username` | 同上，多为格式错误或 helper 未生效 | → §2.2 |
    | `Authentication failed` / `403` / `Invalid username or token` | Token 过期或权限不足 | → §2.2，提示重新生成并检查 `repo` / `write_repository` |
    | `fetch` 超时 | 网络问题 | → §4.1 网络超时配置后重试 §3.4 |

  - **向用户汇报**（仅说明通过 / 失败原因，禁止输出凭据）：
    - 目标 `<仓库标识>` / URL / `<分支>`
    - 各项检查结果：`凭据缓存` / `凭据格式` / `credential fill` / `fetch` / `push --dry-run`
    - 全部通过后方可进入 §4

## 4 后台执行提交

  - **前置条件**: §3.3 已把占位符写入 index，并且工作区已恢复成本机原值；§3.4 连通性校验已通过。
  - 用户确认后，在项目根目录**顺序执行**。含本机路径 / IP / Token / Key 的文件**不要**在这里再次 `git add`（否则会把刚还原的本机值盖掉 index 里的占位符）。仓库在服务器上时，恢复的就是服务器上这份工作区：

    ```bash
    git config --global user.name "<用户名>"
    git config --global user.email "<用户邮箱>"

    git checkout "<分支>"
    # 新建分支：git checkout -b "<分支>"

    git fetch <仓库标识>
    git pull <仓库标识> <分支> --no-rebase

    # 仅添加 §3.3 判定无命中的文件；命中文件已在 §3.3 用占位符 git add 并还原
    git add <无命中文件>
    git commit -m "<message>"

    git push -u <仓库标识> <分支>
    ```

  - **注意**: 若用户 §3.2 **c** 确认不修改身份，跳过 `git config` 两行；若 §3.2 **b** 选择暂不 pull，跳过 `git pull`；无 staged 改动时跳过 `git commit`，直接 push。

### 4.1 异常处理

  - **`rejected (fetch first)`**（远程有 Initial commit）：

    ```bash
    git pull <仓库标识> <分支> --allow-unrelated-histories --no-rebase --no-edit
    git checkout --ours README.md && git add README.md
    git commit -m "Merge remote initial commit"
    git push -u <仓库标识> <分支>
    ```

  - **protected branch 拒绝 force push**：仅 pull 合并，不要 force。

  - **认证失败**（`could not read Username`、`Authentication failed`、`403`）：

    - 若 §3.4 已执行仍失败（极少见，如 Token 中途失效）：回到 §2.2，指引用户自行写入凭据；**不得**在对话中索要或接收凭据后重试。

  - **网络超时**（`HTTP 408`、`RPC failed`）：可调大缓冲后重试，**不涉及凭据**：

    ```bash
    git config --global http.postBuffer 524288000
    git config --global http.lowSpeedLimit 0
    git config --global http.lowSpeedTime 999999
    git config --global http.version HTTP/1.1
    ```

## 5 回报结果

  - 执行完毕后向用户报告：

    - 目标 `<仓库标识>` / `<分支>` / commit hash
    - push 是否成功
    - 若同步多个 remote，分别说明

    ```bash
    git log -1 --oneline
    git status -sb
    git branch -vv
    ```

## 6 双仓库维护

  同时维护 GitLab + GitHub 时，**默认**：

  | 远程 | 日常分支 | 合进主干 |
  | ---- | -------- | -------- |
  | `gitlab` | 保留 `yulin-dev` | 网页 MR → `main`（§6.2） |
  | `github` | **只有** `main` | 本地 `yulin-dev` 快进推到 `github/main` |

  - **pull**：只从 `gitlab` 拉团队更新（`git pull gitlab yulin-dev --no-rebase`）。
  - **push 俩远程**（在 `yulin-dev` 上 commit 之后）：

    ```bash
    git push gitlab yulin-dev
    git push github yulin-dev:main
    git push github --delete yulin-dev 2>/dev/null || true
    git branch -u gitlab/yulin-dev
    ```

  - **注意**：
    - 禁止给 GitHub 长期留 `yulin-dev`；`git push -u github yulin-dev` 会把本地跟踪改到 GitHub，推完必须 `-u gitlab/yulin-dev` 改回来。
    - GitHub `main` 可快进时不要 force；不能快进则先说明，未经同意不得 `--force`。
    - GitLab 的 `main` **不要**直接 push（受保护时用 MR）。

### 6.1 GitHub：合进 main

  ```bash
  git fetch github
  git log --oneline github/main..HEAD    # 将推上去的提交
  git push github HEAD:main              # 或 yulin-dev:main
  git push github --delete yulin-dev     # 远程有该分支才执行
  ```

### 6.2 GitLab：MR 合进 main（教用户点网页）

  Agent **默认不代替点 Merge**（除非用户明确说「帮我在 GitLab 上合」且有 API）。教用户：

  **(1)** 创建 MR：`Merge requests` → `New merge request`  
  Source = `yulin-dev`，Target = `main`。  
  快捷：`<gitlab仓库页>/-/merge_requests/new?merge_request%5Bsource_branch%5D=yulin-dev`

  **(2)** 若报 `Another open merge request already exists for this source branch: !N`：  
  **不要新建**，打开已有 `!N`（源分支 push 后会自动带上最新 commit）→ Approve（如需要）→ **Merge**。

  **(3)** Merge 建议用 **Merge commit**（与历史 `Merge branch 'yulin-dev' into 'main'` 一致）。  
  **不要勾** Delete source branch（GitLab 要保留 `yulin-dev`），除非用户当场说删。

  **(4)** 合完本地如需同步 `main`：

    ```bash
    git fetch gitlab
    git checkout main
    git pull gitlab main --no-rebase
    git checkout yulin-dev
    ```

  - **注意**: 需求原文见同目录 `requi.md`。
