"""Fill the placeholders in snowflake/01_account_setup.sql.

Values come from Terraform outputs (bucket, IAM role) and the public keys in
~/.snowflake/keys/. Writes build/01_account_setup.sql (gitignored), which you
paste into a Snowsight worksheet and run as ACCOUNTADMIN.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "snowflake" / "01_account_setup.sql"
OUT = ROOT / "build" / "01_account_setup.sql"
KEY_DIR = Path.home() / ".snowflake" / "keys"


def tf_output(name: str) -> str:
    return subprocess.run(
        ["terraform", f"-chdir={ROOT / 'infra' / 'terraform'}", "output", "-raw", name],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def public_key_body(user: str) -> str:
    """PEM public key without header/footer/newlines, as Snowflake expects."""
    pem = (KEY_DIR / f"{user}_rsa_key.pub").read_text()
    return "".join(line for line in pem.splitlines() if "-----" not in line)


def main() -> None:
    values = {
        "LAKE_BUCKET": tf_output("lake_bucket"),
        "SNOWFLAKE_ROLE_ARN": tf_output("snowflake_role_arn"),
        "LOADER_PUBLIC_KEY": public_key_body("olist_loader"),
        "DBT_PUBLIC_KEY": public_key_body("olist_dbt"),
    }
    sql = TEMPLATE.read_text()
    for key, value in values.items():
        sql = sql.replace("{{" + key + "}}", value)

    leftover = re.findall(r"\{\{\w+\}\}", sql)
    if leftover:
        sys.exit(f"Unfilled placeholders: {sorted(set(leftover))}")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(sql)
    print(f"Wrote {OUT}")
    print(f"  bucket: {values['LAKE_BUCKET']}\n  role:   {values['SNOWFLAKE_ROLE_ARN']}")


if __name__ == "__main__":
    main()
