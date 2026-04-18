# codex-auth-bridge

`codex-auth-bridge` 是一个命令行工具，用来处理 ChatGPT/Codex 工作流里常见的浏览器登录 `auth.json` 文件。

English documentation: [README.md](README.md)

## 功能概览

- 在 `chatgpt` 与 `codex` 两种 `auth.json` 结构之间互转
- 根据账号信息生成稳定文件名
- 将单个或批量 auth 文件导出到 `sub2api.json`
- 将 `sub2api.json` 中的账号批量导回为 CPA 使用的 `codex` 文件

## 支持的格式

- `chatgpt`：Codex CLI 和 Codex App 使用的 auth 文件格式
- `codex`：CPA 使用的 auth 文件格式，也是本项目支持处理的格式

## 功能说明

- 探测输入文件是 `chatgpt` 还是 `codex`
- 支持单文件与目录批量转换
- 未显式指定输出文件名时，默认生成账号规则文件名：
  `"<类型>-<account_id 的 sha256 前 8 位>-<email>-<tier>.json"`
- 支持导出或追加到 `sub2api.json`
- 导出到 `sub2api` 时会：
  - 识别同一账号并更新已有记录
  - 保留同邮箱下的不同账号
  - 优先根据 `last_refresh`、再回退到 token 时间决定保留哪份记录
  - 兼容 `proxies: []`
- 支持将 `sub2api.json` 批量导出回 `codex` 文件
- `codex` 就是 CPA 使用的格式

## 安装

### 直接下载 `cli.py`

这个脚本没有第三方运行时依赖。你可以直接下载 [`src/codex_auth_bridge/cli.py`](src/codex_auth_bridge/cli.py) 并运行：

```bash
python3 cli.py -h
python3 cli.py detect auth.json
```

### 直接运行源码

```bash
git clone https://github.com/kekexiaoai/codex-auth-bridge.git
cd codex-auth-bridge
python3 -m unittest discover -s tests -p 'test_cli.py'
PYTHONPATH=src python3 -m codex_auth_bridge.cli -h
```

### 安装为命令

```bash
pip install .
codex-auth-bridge -h
```

## 命令

可以使用 `--lang zh|en|auto` 控制输出语言。默认是 `zh`，`auto` 会根据环境语言自动选择。

### 1. 探测格式

```bash
codex-auth-bridge --lang en detect auth.json
codex-auth-bridge detect auth.json
codex-auth-bridge detect auths/
```

### 2. 转换格式

```bash
codex-auth-bridge convert auth.json
codex-auth-bridge convert auth.json output.json
codex-auth-bridge convert auths/
codex-auth-bridge convert auths/ output-dir/
```

### 3. 导出到 sub2api

```bash
codex-auth-bridge export-sub2api auths/ sub2api.json
codex-auth-bridge export-sub2api auths/ sub2api.json --proxy-key proxy-demo
```

### 4. 导出 sub2api 到 codex（CPA）

```bash
codex-auth-bridge export-codex sub2api.json codex-auths/
codex-auth-bridge export-codex sub2api.json codex-auths/ --skip-invalid
```

## 输出约定

### auth 转换

未显式指定输出文件名时，默认输出到源文件所在目录，并优先使用账号规则文件名。

示例：

```text
codex-demo.json -> chatgpt-<hash>-demo@example.com-team.json
```

### sub2api 导出

- 当目标 `sub2api.json` 已存在账号时，默认按 `chatgpt_user_id + chatgpt_account_id` 识别是否为同一账号
- 若是同一账号，优先比较：
  1. `last_refresh`
  2. `access_token.iat`
  3. `expires_at`

### codex 导出

- `export-codex` 会从 `sub2api.json` 中读取账号，并为每个账号生成一个 `codex` 文件
- 输出文件名沿用同一套账号规则：
  `codex-<account_id 的 sha256 前 8 位>-<email>-<tier>.json`
- 使用 `--skip-invalid` 时，遇到无效条目会跳过并继续导出其他账号

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_cli.py'
```

## 特别鸣谢

- [Linux.do](https://linux.do/)

## License

MIT
