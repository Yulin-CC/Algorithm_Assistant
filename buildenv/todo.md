# buildenv 待办

蓝图还没写完的部分。补一份就删一行。做完在 `开发日志.md` 记一次迭代。

---

## 需要本地压缩包才能写

这三个仓有团队改动，没有可 clone 的完整来源，要用户提供压缩包后才能写蓝图。

| 仓 | 装到 | 状态 | 缺什么 |
| --- | --- | --- | --- |
| SCM | `3-TASK/SCM` | 📦 待压缩包 | 团队版源码包。上游是 `github.com/StephenApX/UCD-SCM`，但团队改了 ultralytics，靠 `install_tbr.sh` 打补丁 |
| GEOLabeling | `z-OTHERS/GEOLabeling` | 📦 待压缩包 | 源于 `github.com/CVHub520/X-AnyLabeling`，团队改了什么不明 |
| Agent-DEMO | `z-OTHERS/Agent-DEMO` | 📦 待压缩包 | 自建项目，无官方源码 |

拿到压缩包后，按 `README.md` §5 的七节格式写。

### SCM 已探明的事

压缩包到了可以直接用，这几点不用再查：

- 环境：conda `scm`，Python 3.9
- 仓内有 `install_tbr.sh`：把 `utils/tbr/` 的补丁装进当前 conda 环境的 ultralytics，改三个文件
  - `head.py` → `ultralytics/nn/modules/head.py`
  - `predictor.py` → `ultralytics/yolo/engine/predictor.py`
  - `tasks.py` → `ultralytics/nn/tasks.py`
- **装完环境必须跑这个脚本**，否则 SCM 推理和 ONNX 导出都不生效
- 脚本会检查 `CONDA_PREFIX`，没激活环境会退出

---

## 其它

| 事 | 说明 |
| --- | --- |
| 蓝图随仓变化更新 | 上游大版本升级、环境变量改动后，对应蓝图要跟着改 |
