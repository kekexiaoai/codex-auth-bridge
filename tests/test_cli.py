import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from codex_auth_bridge import cli as MODULE


def cli_env():
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{SRC_PATH}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(SRC_PATH)
    )
    return env


def run_cli(args, extra_env=None):
    env = cli_env()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "codex_auth_bridge.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def iter_repo_text_files():
    allowed_suffixes = {".py", ".md", ".toml", ".txt", ".json"}

    yield ROOT / "README.md"
    yield ROOT / "README.zh-CN.md"
    yield ROOT / "pyproject.toml"
    yield ROOT / "LICENSE"

    for base_dir in (ROOT / "src", ROOT / "tests"):
        for path in sorted(base_dir.rglob("*")):
            if path.is_file() and path.suffix in allowed_suffixes:
                yield path


class OpenAIFormatConvertTests(unittest.TestCase):
    def make_jwt(self, payload):
        header = {"alg": "none", "typ": "JWT"}
        return ".".join(
            [
                self.base64url_encode(json.dumps(header, separators=(",", ":"))),
                self.base64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True)),
                "signature",
            ]
        )

    def base64url_encode(self, text):
        return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8").rstrip("=")

    def make_access_token(
        self,
        account_id,
        user_id="user-123",
        plan_type="team",
        exp=200,
        iat=100,
        client_id="app_test_client",
    ):
        return self.make_jwt(
            {
                "client_id": client_id,
                "exp": exp,
                "iat": iat,
                "https://api.openai.com/auth": {
                    "chatgpt_account_id": account_id,
                    "chatgpt_plan_type": plan_type,
                    "chatgpt_user_id": user_id,
                },
            }
        )

    def test_chatgpt_to_codex_accepts_minimal_payload(self):
        chatgpt_data = {
            "OPENAI_API_KEY": "",
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": "access-token",
                "id_token": "id-token",
            },
        }

        converted = MODULE.chatgpt_to_codex(chatgpt_data)

        self.assertEqual(
            converted,
            {
                "access_token": "access-token",
                "disabled": False,
                "email": "",
                "expired": "",
                "id_token": "id-token",
                "last_refresh": "",
                "type": "codex",
            },
        )

    def test_codex_to_chatgpt_keeps_empty_api_key_string(self):
        codex_data = {
            "access_token": "access-token",
            "id_token": "id-token",
            "type": "codex",
        }

        converted = MODULE.codex_to_chatgpt(codex_data)

        self.assertEqual(converted["OPENAI_API_KEY"], "")
        self.assertEqual(converted["auth_mode"], "chatgpt")
        self.assertEqual(converted["disabled"], False)
        self.assertEqual(converted["last_refresh"], "")
        self.assertEqual(
            converted["tokens"],
            {
                "access_token": "access-token",
                "id_token": "id-token",
            },
        )

    def test_detect_subcommand_reports_source_and_target(self):
        chatgpt_data = {
            "OPENAI_API_KEY": "",
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": "access-token",
                "id_token": "id-token",
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "chatgpt.json"
            input_path.write_text(json.dumps(chatgpt_data), encoding="utf-8")

            result = run_cli(["detect", str(input_path)])

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("识别格式：chatgpt", result.stdout)
        self.assertIn("可转换为：codex", result.stdout)

    def test_detect_subcommand_reports_source_and_target_in_english(self):
        chatgpt_data = {
            "OPENAI_API_KEY": "",
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": "access-token",
                "id_token": "id-token",
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "chatgpt.json"
            input_path.write_text(json.dumps(chatgpt_data), encoding="utf-8")

            result = run_cli(["--lang", "en", "detect", str(input_path)])

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Detected format: chatgpt", result.stdout)
        self.assertIn("Convertible to: codex", result.stdout)

    def test_detect_subcommand_auto_language_uses_english_locale(self):
        chatgpt_data = {
            "OPENAI_API_KEY": "",
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": "access-token",
                "id_token": "id-token",
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "chatgpt.json"
            input_path.write_text(json.dumps(chatgpt_data), encoding="utf-8")

            result = run_cli(
                ["--lang", "auto", "detect", str(input_path)],
                extra_env={
                    "LANG": "en_US.UTF-8",
                    "LC_ALL": "en_US.UTF-8",
                },
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Detected format: chatgpt", result.stdout)
        self.assertIn("Current status: convertible", result.stdout)

    def test_export_sub2api_help_uses_subcommand_parser(self):
        result = run_cli(["export-sub2api", "-h"])

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("sub2api.json 输出路径", result.stdout)
        self.assertIn("--proxy-key", result.stdout)

    def test_export_codex_help_uses_subcommand_parser(self):
        result = run_cli(["export-codex", "-h"])

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("codex 输出目录", result.stdout)
        self.assertIn("--skip-invalid", result.stdout)

    def test_convert_subcommand_writes_detected_target_format(self):
        chatgpt_data = {
            "OPENAI_API_KEY": "",
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": "access-token",
                "id_token": "id-token",
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "chatgpt.json"
            output_path = Path(temp_dir) / "codex.json"
            input_path.write_text(json.dumps(chatgpt_data), encoding="utf-8")

            result = run_cli(["convert", str(input_path), str(output_path)])

            if output_path.exists():
                converted = json.loads(output_path.read_text(encoding="utf-8"))
            else:
                converted = None

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIsNotNone(converted)
        self.assertEqual(converted["type"], "codex")
        self.assertEqual(converted["access_token"], "access-token")
        self.assertEqual(converted["id_token"], "id-token")

    def test_convert_subcommand_uses_default_output_name_for_single_file(self):
        account_id = "account-123"
        email = "demo@example.com"
        tier = "team"
        codex_data = {
            "access_token": self.make_access_token(account_id, plan_type=tier),
            "account_id": account_id,
            "email": email,
            "id_token": self.make_jwt(
                {
                    "sub": account_id,
                    "email": email,
                    "tier": tier,
                }
            ),
            "type": "codex",
        }
        expected_hash = hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:8]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "codex-demo.json"
            expected_output_path = Path(temp_dir) / f"chatgpt-{expected_hash}-{email}-{tier}.json"
            input_path.write_text(json.dumps(codex_data), encoding="utf-8")

            result = run_cli(["convert", str(input_path)])

            if expected_output_path.exists():
                converted = json.loads(expected_output_path.read_text(encoding="utf-8"))
            else:
                converted = None

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn(str(expected_output_path), result.stdout)
        self.assertIsNotNone(converted)
        self.assertEqual(converted["auth_mode"], "chatgpt")

    def test_convert_subcommand_converts_directory_into_default_output_names(self):
        alpha_account_id = "alpha-account"
        alpha_email = "alpha@example.com"
        alpha_tier = "team"
        chatgpt_data = {
            "OPENAI_API_KEY": "",
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": self.make_access_token(alpha_account_id, plan_type=alpha_tier),
                "account_id": alpha_account_id,
                "id_token": self.make_jwt(
                    {
                        "sub": alpha_account_id,
                        "email": alpha_email,
                        "tier": alpha_tier,
                    }
                ),
            },
        }
        beta_account_id = "beta-account"
        beta_email = "beta@example.com"
        beta_tier = "pro"
        codex_data = {
            "access_token": self.make_access_token(beta_account_id, plan_type=beta_tier),
            "account_id": beta_account_id,
            "email": beta_email,
            "id_token": self.make_jwt(
                {
                    "sub": beta_account_id,
                    "email": beta_email,
                    "tier": beta_tier,
                }
            ),
            "type": "codex",
        }
        alpha_hash = hashlib.sha256(alpha_account_id.encode("utf-8")).hexdigest()[:8]
        beta_hash = hashlib.sha256(beta_account_id.encode("utf-8")).hexdigest()[:8]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "inputs"
            input_dir.mkdir()
            (input_dir / "chatgpt-alpha.json").write_text(json.dumps(chatgpt_data), encoding="utf-8")
            (input_dir / "codex-beta.json").write_text(json.dumps(codex_data), encoding="utf-8")

            result = run_cli(["convert", str(input_dir)])

            output_one = input_dir / f"codex-{alpha_hash}-{alpha_email}-{alpha_tier}.json"
            output_two = input_dir / f"chatgpt-{beta_hash}-{beta_email}-{beta_tier}.json"

            converted_one = json.loads(output_one.read_text(encoding="utf-8")) if output_one.exists() else None
            converted_two = json.loads(output_two.read_text(encoding="utf-8")) if output_two.exists() else None

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIsNotNone(converted_one)
        self.assertIsNotNone(converted_two)
        self.assertEqual(converted_one["type"], "codex")
        self.assertEqual(converted_two["auth_mode"], "chatgpt")

    def test_convert_subcommand_uses_forced_account_filename_pattern(self):
        account_id = "18fd2654-0e5b-4026-9f8c-adef4dce58a1"
        email = "forced-filename@example.com"
        tier = "team"
        chatgpt_data = {
            "OPENAI_API_KEY": "",
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": "access-token",
                "account_id": account_id,
                "id_token": self.make_jwt(
                    {
                        "sub": account_id,
                        "email": email,
                        "tier": tier,
                    }
                ),
            },
        }
        expected_hash = hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:8]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.json"
            expected_output_path = Path(temp_dir) / f"codex-{expected_hash}-{email}-{tier}.json"
            input_path.write_text(json.dumps(chatgpt_data), encoding="utf-8")

            result = run_cli(
                [
                    "convert",
                    str(input_path),
                    "--force-account-filename",
                ]
            )

            converted = json.loads(expected_output_path.read_text(encoding="utf-8")) if expected_output_path.exists() else None

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn(str(expected_output_path), result.stdout)
        self.assertIsNotNone(converted)
        self.assertEqual(converted["type"], "codex")

    def test_export_sub2api_subcommand_merges_directory_accounts(self):
        alpha_account_id = "sub2api-alpha-account"
        alpha_email = "alpha@example.com"
        alpha_tier = "team"
        beta_account_id = "sub2api-beta-account"
        beta_email = "beta@example.com"
        beta_tier = "pro"

        chatgpt_data = {
            "OPENAI_API_KEY": "",
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": self.make_access_token(alpha_account_id, user_id="user-alpha", plan_type=alpha_tier, exp=500, iat=100),
                "account_id": alpha_account_id,
                "id_token": self.make_jwt(
                    {
                        "sub": alpha_account_id,
                        "email": alpha_email,
                        "tier": alpha_tier,
                        "https://api.openai.com/auth": {
                            "organizations": [{"id": "org-alpha"}],
                        },
                    }
                ),
                "refresh_token": "refresh-alpha",
            },
        }
        codex_data = {
            "access_token": self.make_access_token(beta_account_id, user_id="user-beta", plan_type=beta_tier, exp=900, iat=300),
            "account_id": beta_account_id,
            "email": beta_email,
            "id_token": self.make_jwt(
                {
                    "sub": beta_account_id,
                    "email": beta_email,
                    "tier": beta_tier,
                    "https://api.openai.com/auth": {
                        "organizations": [{"id": "org-beta"}],
                    },
                }
            ),
            "refresh_token": "refresh-beta",
            "type": "codex",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "auths"
            input_dir.mkdir()
            (input_dir / "chatgpt-alpha.json").write_text(json.dumps(chatgpt_data), encoding="utf-8")
            (input_dir / "codex-beta.json").write_text(json.dumps(codex_data), encoding="utf-8")
            output_path = Path(temp_dir) / "sub2api.json"
            output_path.write_text(
                json.dumps(
                    {
                        "proxies": [{"proxy_key": "proxy-demo"}],
                        "accounts": [
                            {
                                "credentials": {
                                    "chatgpt_account_id": alpha_account_id,
                                    "chatgpt_user_id": "user-alpha",
                                    "refresh_token": "stale-refresh-alpha",
                                },
                                "extra": {
                                    "email": alpha_email,
                                    "chatgpt_account_id": alpha_account_id,
                                    "chatgpt_user_id": "user-alpha",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = run_cli(["export-sub2api", str(input_dir), str(output_path)])
            exported = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("更新: alpha@example.com", result.stdout)
        self.assertIn("添加: beta@example.com", result.stdout)
        self.assertEqual(len(exported["accounts"]), 2)
        alpha_account = next(account for account in exported["accounts"] if account.get("extra", {}).get("email") == alpha_email)
        self.assertEqual(alpha_account["credentials"]["refresh_token"], "refresh-alpha")
        beta_account = next(account for account in exported["accounts"] if account.get("extra", {}).get("email") == beta_email)
        self.assertEqual(beta_account["proxy_key"], "proxy-demo")
        self.assertEqual(beta_account["credentials"]["chatgpt_account_id"], beta_account_id)
        self.assertEqual(beta_account["credentials"]["chatgpt_user_id"], "user-beta")
        self.assertEqual(beta_account["credentials"]["client_id"], "app_test_client")
        self.assertEqual(beta_account["credentials"]["email"], beta_email)
        self.assertEqual(beta_account["credentials"]["id_token"], codex_data["id_token"])
        self.assertEqual(beta_account["credentials"]["organization_id"], "org-beta")
        self.assertEqual(beta_account["credentials"]["plan_type"], beta_tier)
        self.assertEqual(beta_account["credentials"]["refresh_token"], "refresh-beta")
        self.assertEqual(beta_account["credentials"]["expires_at"], 900)
        self.assertEqual(beta_account["credentials"]["expires_in"], 600)
        self.assertNotIn("plan_type", beta_account["extra"])

    def test_export_sub2api_allows_empty_proxies_without_proxy_key(self):
        account_id = "empty-proxy-account"
        email = "empty-proxy@example.com"
        auth_data = {
            "access_token": self.make_access_token(account_id, user_id="user-empty", plan_type="free", exp=600, iat=100),
            "account_id": account_id,
            "email": email,
            "id_token": self.make_jwt(
                {
                    "sub": account_id,
                    "email": email,
                    "plan": "free",
                }
            ),
            "refresh_token": "refresh-empty",
            "type": "codex",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "auths"
            input_dir.mkdir()
            (input_dir / "account.json").write_text(json.dumps(auth_data), encoding="utf-8")
            output_path = Path(temp_dir) / "sub2api.json"
            output_path.write_text(
                json.dumps(
                    {
                        "exported_at": "2026-04-04T09:45:12Z",
                        "proxies": [],
                        "accounts": [],
                    }
                ),
                encoding="utf-8",
            )

            result = run_cli(["export-sub2api", str(input_dir), str(output_path)])
            exported = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(exported["proxies"], [])
        self.assertEqual(len(exported["accounts"]), 1)
        self.assertNotIn("proxy_key", exported["accounts"][0])

    def test_export_sub2api_preserves_same_email_plus_and_multiple_team_accounts(self):
        shared_email = "shared@example.com"
        plus_account_id = "plus-account"
        team_one_account_id = "team-one-account"
        team_two_account_id = "team-two-account"

        plus_auth = {
            "access_token": self.make_access_token(plus_account_id, user_id="user-plus", plan_type="plus", exp=400, iat=100),
            "account_id": plus_account_id,
            "email": shared_email,
            "id_token": self.make_jwt(
                {
                    "sub": plus_account_id,
                    "email": shared_email,
                    "plan": "plus",
                    "https://api.openai.com/auth": {
                        "organizations": [{"id": "org-personal"}],
                        "chatgpt_plan_type": "plus",
                    },
                }
            ),
            "refresh_token": "refresh-plus",
            "type": "codex",
        }
        team_one_auth = {
            "access_token": self.make_access_token(team_one_account_id, user_id="user-team-1", plan_type="team", exp=500, iat=100),
            "account_id": team_one_account_id,
            "email": shared_email,
            "id_token": self.make_jwt(
                {
                    "sub": team_one_account_id,
                    "email": shared_email,
                    "tier": "team",
                    "https://api.openai.com/auth": {
                        "organizations": [{"id": "org-team-1"}],
                        "chatgpt_plan_type": "team",
                    },
                }
            ),
            "refresh_token": "refresh-team-1",
            "type": "codex",
        }
        team_two_auth = {
            "access_token": self.make_access_token(team_two_account_id, user_id="user-team-2", plan_type="team", exp=600, iat=100),
            "account_id": team_two_account_id,
            "email": shared_email,
            "id_token": self.make_jwt(
                {
                    "sub": team_two_account_id,
                    "email": shared_email,
                    "tier": "team",
                    "https://api.openai.com/auth": {
                        "organizations": [{"id": "org-team-2"}],
                        "chatgpt_plan_type": "team",
                    },
                }
            ),
            "refresh_token": "refresh-team-2",
            "type": "codex",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "auths"
            input_dir.mkdir()
            (input_dir / "plus.json").write_text(json.dumps(plus_auth), encoding="utf-8")
            (input_dir / "team-1.json").write_text(json.dumps(team_one_auth), encoding="utf-8")
            (input_dir / "team-2.json").write_text(json.dumps(team_two_auth), encoding="utf-8")
            output_path = Path(temp_dir) / "sub2api.json"

            result = run_cli(
                ["export-sub2api", str(input_dir), str(output_path), "--proxy-key", "proxy-demo"]
            )
            exported = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        shared_accounts = [account for account in exported["accounts"] if account.get("extra", {}).get("email") == shared_email]
        self.assertEqual(len(shared_accounts), 3)
        self.assertEqual(
            sorted(account["credentials"]["refresh_token"] for account in shared_accounts),
            ["refresh-plus", "refresh-team-1", "refresh-team-2"],
        )

    def test_export_sub2api_updates_existing_same_account_user_instead_of_duplicating(self):
        account_id = "shared-team-account"
        email = "member@example.com"
        user_id = "user-member"
        existing_entry = {
            "name": "custom-member-name",
            "platform": "openai",
            "type": "oauth",
            "credentials": {
                "access_token": "old-access",
                "chatgpt_account_id": account_id,
                "chatgpt_user_id": user_id,
                "expires_at": 1,
                "expires_in": 1,
                "organization_id": "org-team",
                "refresh_token": "old-refresh",
            },
            "extra": {
                "email": email,
                "plan_type": "team",
                "organization_id": "org-team",
                "chatgpt_account_id": account_id,
                "chatgpt_user_id": user_id,
                "last_refresh": "2026-04-15T09:00:00+00:00",
                "privacy_mode": "training_off",
            },
            "proxy_key": "proxy-demo",
            "concurrency": 10,
            "priority": 1,
            "rate_multiplier": 1,
            "auto_pause_on_expired": True,
        }
        updated_auth = {
            "access_token": self.make_access_token(account_id, user_id=user_id, plan_type="team", exp=999, iat=100),
            "account_id": account_id,
            "email": email,
            "id_token": self.make_jwt(
                {
                    "sub": account_id,
                    "email": email,
                    "tier": "team",
                    "https://api.openai.com/auth": {
                        "organizations": [{"id": "org-team"}],
                        "chatgpt_plan_type": "team",
                    },
                }
            ),
            "refresh_token": "new-refresh",
            "last_refresh": "2026-04-16T09:00:00+00:00",
            "type": "codex",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "auths"
            input_dir.mkdir()
            (input_dir / "member.json").write_text(json.dumps(updated_auth), encoding="utf-8")
            output_path = Path(temp_dir) / "sub2api.json"
            output_path.write_text(
                json.dumps(
                    {
                        "proxies": [{"proxy_key": "proxy-demo"}],
                        "accounts": [existing_entry],
                    }
                ),
                encoding="utf-8",
            )

            result = run_cli(["export-sub2api", str(input_dir), str(output_path)])
            exported = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(len(exported["accounts"]), 1)
        account = exported["accounts"][0]
        self.assertEqual(account["name"], "custom-member-name")
        self.assertEqual(account["credentials"]["refresh_token"], "new-refresh")
        self.assertEqual(account["credentials"]["expires_at"], 999)
        self.assertEqual(account["credentials"]["plan_type"], "team")
        self.assertEqual(account["credentials"]["email"], email)
        self.assertEqual(account["extra"]["privacy_mode"], "training_off")

    def test_export_sub2api_keeps_existing_entry_when_last_refresh_is_newer(self):
        account_id = "same-account"
        email = "same@example.com"
        user_id = "same-user"
        existing_entry = {
            "name": "same",
            "platform": "openai",
            "type": "oauth",
            "credentials": {
                "access_token": "old-access",
                "chatgpt_account_id": account_id,
                "chatgpt_user_id": user_id,
                "expires_at": 1000,
                "expires_in": 900,
                "organization_id": "org-team",
                "refresh_token": "existing-refresh",
            },
            "extra": {
                "email": email,
                "plan_type": "team",
                "organization_id": "org-team",
                "chatgpt_account_id": account_id,
                "chatgpt_user_id": user_id,
                "last_refresh": "2026-04-17T09:00:00+00:00",
            },
            "proxy_key": "proxy-demo",
            "concurrency": 10,
            "priority": 1,
            "rate_multiplier": 1,
            "auto_pause_on_expired": True,
        }
        incoming_auth = {
            "access_token": self.make_access_token(account_id, user_id=user_id, plan_type="team", exp=2000, iat=100),
            "account_id": account_id,
            "email": email,
            "id_token": self.make_jwt(
                {
                    "sub": account_id,
                    "email": email,
                    "tier": "team",
                    "https://api.openai.com/auth": {
                        "organizations": [{"id": "org-team"}],
                        "chatgpt_plan_type": "team",
                    },
                }
            ),
            "refresh_token": "incoming-refresh",
            "last_refresh": "2026-04-16T09:00:00+00:00",
            "type": "codex",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "auths"
            input_dir.mkdir()
            (input_dir / "member.json").write_text(json.dumps(incoming_auth), encoding="utf-8")
            output_path = Path(temp_dir) / "sub2api.json"
            output_path.write_text(
                json.dumps(
                    {
                        "proxies": [{"proxy_key": "proxy-demo"}],
                        "accounts": [existing_entry],
                    }
                ),
                encoding="utf-8",
            )

            result = run_cli(["export-sub2api", str(input_dir), str(output_path)])
            exported = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        account = exported["accounts"][0]
        self.assertEqual(account["credentials"]["refresh_token"], "existing-refresh")
        self.assertEqual(account["extra"]["last_refresh"], "2026-04-17T09:00:00+00:00")

    def test_export_codex_subcommand_exports_multiple_accounts(self):
        alpha_account_id = "export-codex-alpha"
        alpha_email = "alpha@example.com"
        alpha_tier = "team"
        beta_account_id = "export-codex-beta"
        beta_email = "beta@example.com"
        beta_tier = "pro"
        alpha_hash = hashlib.sha256(alpha_account_id.encode("utf-8")).hexdigest()[:8]
        beta_hash = hashlib.sha256(beta_account_id.encode("utf-8")).hexdigest()[:8]

        sub2api_data = {
            "accounts": [
                {
                    "credentials": {
                        "access_token": self.make_access_token(alpha_account_id, user_id="user-alpha", plan_type=alpha_tier),
                        "chatgpt_account_id": alpha_account_id,
                        "email": alpha_email,
                        "id_token": self.make_jwt(
                            {
                                "sub": alpha_account_id,
                                "email": alpha_email,
                                "tier": alpha_tier,
                            }
                        ),
                        "refresh_token": "refresh-alpha",
                    },
                    "extra": {
                        "email": alpha_email,
                        "last_refresh": "2026-04-17T09:00:00+00:00",
                    },
                },
                {
                    "credentials": {
                        "access_token": self.make_access_token(beta_account_id, user_id="user-beta", plan_type=beta_tier),
                        "chatgpt_account_id": beta_account_id,
                        "email": beta_email,
                        "id_token": self.make_jwt(
                            {
                                "sub": beta_account_id,
                                "email": beta_email,
                                "tier": beta_tier,
                            }
                        ),
                        "refresh_token": "refresh-beta",
                    },
                    "extra": {
                        "email": beta_email,
                    },
                },
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "sub2api.json"
            output_dir = Path(temp_dir) / "codex-auths"
            input_path.write_text(json.dumps(sub2api_data), encoding="utf-8")

            result = run_cli(["export-codex", str(input_path), str(output_dir)])

            alpha_output = output_dir / f"codex-{alpha_hash}-{alpha_email}-{alpha_tier}.json"
            beta_output = output_dir / f"codex-{beta_hash}-{beta_email}-{beta_tier}.json"
            alpha_data = json.loads(alpha_output.read_text(encoding="utf-8")) if alpha_output.exists() else None
            beta_data = json.loads(beta_output.read_text(encoding="utf-8")) if beta_output.exists() else None

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIsNotNone(alpha_data)
        self.assertIsNotNone(beta_data)
        self.assertEqual(alpha_data["type"], "codex")
        self.assertEqual(alpha_data["account_id"], alpha_account_id)
        self.assertEqual(alpha_data["email"], alpha_email)
        self.assertEqual(alpha_data["last_refresh"], "2026-04-17T09:00:00+00:00")
        self.assertEqual(beta_data["type"], "codex")
        self.assertEqual(beta_data["account_id"], beta_account_id)
        self.assertEqual(beta_data["refresh_token"], "refresh-beta")

    def test_export_codex_subcommand_requires_id_token(self):
        account_id = "missing-id-token-account"
        email = "missing-id-token@example.com"
        sub2api_data = {
            "accounts": [
                {
                    "credentials": {
                        "access_token": self.make_access_token(account_id, plan_type="team"),
                        "chatgpt_account_id": account_id,
                        "email": email,
                    },
                    "extra": {
                        "email": email,
                    },
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "sub2api.json"
            output_dir = Path(temp_dir) / "codex-auths"
            input_path.write_text(json.dumps(sub2api_data), encoding="utf-8")

            result = run_cli(["export-codex", str(input_path), str(output_dir)])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("缺少必填字段：id_token", result.stderr)

    def test_export_codex_subcommand_can_skip_invalid_accounts(self):
        valid_account_id = "skip-invalid-valid-account"
        valid_email = "valid@example.com"
        valid_tier = "team"
        valid_hash = hashlib.sha256(valid_account_id.encode("utf-8")).hexdigest()[:8]
        invalid_email = "invalid@example.com"
        sub2api_data = {
            "accounts": [
                {
                    "credentials": {
                        "access_token": self.make_access_token(valid_account_id, plan_type=valid_tier),
                        "chatgpt_account_id": valid_account_id,
                        "email": valid_email,
                        "id_token": self.make_jwt(
                            {
                                "sub": valid_account_id,
                                "email": valid_email,
                                "tier": valid_tier,
                            }
                        ),
                    },
                    "extra": {
                        "email": valid_email,
                    },
                },
                {
                    "credentials": {
                        "access_token": self.make_access_token("invalid-account", plan_type="pro"),
                        "chatgpt_account_id": "invalid-account",
                        "email": invalid_email,
                    },
                    "extra": {
                        "email": invalid_email,
                    },
                },
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "sub2api.json"
            output_dir = Path(temp_dir) / "codex-auths"
            input_path.write_text(json.dumps(sub2api_data), encoding="utf-8")

            result = run_cli(["export-codex", str(input_path), str(output_dir), "--skip-invalid"])

            valid_output = output_dir / f"codex-{valid_hash}-{valid_email}-{valid_tier}.json"
            valid_data = json.loads(valid_output.read_text(encoding="utf-8")) if valid_output.exists() else None

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIsNotNone(valid_data)
        self.assertEqual(valid_data["account_id"], valid_account_id)
        self.assertIn("跳过无效条目", result.stdout)


class RepositorySafetyTests(unittest.TestCase):
    EMAIL_PATTERN = re.compile(
        r"(?<![A-Za-z0-9._%+-])"
        r"([A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}))"
        r"(?![A-Za-z0-9-])"
    )
    ALLOWED_EMAIL_DOMAINS = {"example.com"}

    def is_allowed_email_domain(self, domain):
        normalized_domain = domain.lower()
        return any(
            normalized_domain == allowed_domain or normalized_domain.startswith(f"{allowed_domain}-")
            for allowed_domain in self.ALLOWED_EMAIL_DOMAINS
        )

    def test_repository_only_contains_reserved_example_email_domains(self):
        unexpected_emails = []

        for path in iter_repo_text_files():
            content = path.read_text(encoding="utf-8")
            for match in self.EMAIL_PATTERN.finditer(content):
                domain = match.group(2).lower()
                if not self.is_allowed_email_domain(domain):
                    unexpected_emails.append(f"{path.relative_to(ROOT)}:{match.group(1)}")

        self.assertEqual(
            unexpected_emails,
            [],
            msg=f"仓库中发现非保留示例邮箱: {unexpected_emails}",
        )


if __name__ == "__main__":
    unittest.main()
