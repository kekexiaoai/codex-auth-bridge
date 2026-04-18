# codex-auth-bridge

`codex-auth-bridge` is a command-line tool for working with browser login auth files in ChatGPT/Codex workflows.

Chinese documentation: [简体中文](README.zh-CN.md)

## What it does

- Converts between `chatgpt` and `codex` `auth.json` structures
- Generates stable filenames from account metadata
- Exports one or more auth files to `sub2api.json`
- Exports `sub2api.json` accounts back into `codex` files used by CPA

## Supported formats

- `chatgpt`: the auth file format used by Codex CLI and Codex App
- `codex`: the auth file format used by CPA and supported by this project

## Features

- Detects whether the input is `chatgpt` or `codex`
- Supports both single-file conversion and directory batch conversion
- Generates account-based filenames by default when no output name is provided:
  `"<type>-<first-8-of-sha256(account_id)>-<email>-<tier>.json"`
- Supports exporting or appending entries to `sub2api.json`
- When exporting to `sub2api`, it:
  - updates existing entries for the same account
  - preserves different accounts under the same email
  - prefers `last_refresh`, then token timestamps, when choosing the latest record
  - keeps compatibility with `proxies: []`
- Supports exporting `sub2api.json` back into batch `codex` files
- `codex` is the format used by CPA

## Installation

### Download `cli.py` directly

The script has no third-party runtime dependencies. You can download [`src/codex_auth_bridge/cli.py`](src/codex_auth_bridge/cli.py) and run it directly:

```bash
python3 cli.py -h
python3 cli.py detect auth.json
```

### Run from source

```bash
git clone https://github.com/kekexiaoai/codex-auth-bridge.git
cd codex-auth-bridge
python3 -m unittest discover -s tests -p 'test_cli.py'
PYTHONPATH=src python3 -m codex_auth_bridge.cli -h
```

### Install as a command

```bash
pip install .
codex-auth-bridge -h
```

## Commands

Use `--lang zh|en|auto` to control output language. The default is `zh`, and `auto` follows the environment locale.

### 1. Detect format

```bash
codex-auth-bridge --lang en detect auth.json
codex-auth-bridge detect auth.json
codex-auth-bridge detect auths/
```

### 2. Convert format

```bash
codex-auth-bridge convert auth.json
codex-auth-bridge convert auth.json output.json
codex-auth-bridge convert auths/
codex-auth-bridge convert auths/ output-dir/
```

### 3. Export to sub2api

```bash
codex-auth-bridge export-sub2api auths/ sub2api.json
codex-auth-bridge export-sub2api auths/ sub2api.json --proxy-key proxy-demo
```

### 4. Export sub2api to codex (CPA)

```bash
codex-auth-bridge export-codex sub2api.json codex-auths/
codex-auth-bridge export-codex sub2api.json codex-auths/ --skip-invalid
```

## Output behavior

### Auth conversion

If no output filename is provided, the converted file is written next to the source file and the tool prefers the account-based naming rule.

Example:

```text
codex-demo.json -> chatgpt-<hash>-demo@example.com-team.json
```

### sub2api export

- Existing entries are matched by `chatgpt_user_id + chatgpt_account_id`
- If the account already exists, the tool compares:
  1. `last_refresh`
  2. `access_token.iat`
  3. `expires_at`

### codex export

- `export-codex` reads accounts from `sub2api.json` and writes one `codex` file per account
- Output filenames follow the same account-based rule:
  `codex-<first-8-of-sha256(account_id)>-<email>-<tier>.json`
- `--skip-invalid` skips invalid entries and continues exporting the rest

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_cli.py'
```

## Special Thanks

- [Linux.do](https://linux.do/)

## License

MIT
