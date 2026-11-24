用户说，帮我把代码提交一下远程仓库吧，那么此时Agent需要做的事情：

1. 查看机器中的远程仓库地址和已缓存凭据（按平台检查 `~/.git-credentials` 是否有对应主机记录）。如果没有，请指引用户新建仓库链接，并**在本机终端自行写入凭据**；**禁止在对话中索要或接收 Token**。

2. 如果有，打印当前的 [user.name]，[user.email]，[仓库标识和URL], [远程仓库分支]

   a. 跟用户确认提交到哪个仓库。默认：GitLab 推 `yulin-dev`（保留该分支，网页 MR 合 `main`）；GitHub 只推 `main`，不要 GitHub `yulin-dev`
   b. 查询项目正常连接到仓库以及 token 是否有效
   b. 查询远程仓库该分支是否有更新，跟用户确认是否先拉取还是覆盖
   c. 跟用户确认是否需要更改 [user.name]，[user.email]（默认不改 git config）
   d. 查询 README.md 更新信息，跟用户确认 commit [message]
   e. 提交前扫描本机绝对/相对路径、Token、Key、IP。进 Git 的换成占位符；`git add` 后立刻把工作区还原成本机值，再 commit。`0-Agent-demo/` 应在 gitignore 中。

3. 拿到关键信息后，后台帮助用户提交（在 `yulin-dev` 上）

    ```bash
    git add .
    git commit -m "<message>"

    git push gitlab yulin-dev
    git push github yulin-dev:main
    git push github --delete yulin-dev 2>/dev/null || true
    git branch -u gitlab/yulin-dev
    ```

4. GitLab 合 `main`：教用户走网页 MR；若已有 open MR（如 !4），打开它 Merge，不要新建。GitLab 默认不删 `yulin-dev`。

   