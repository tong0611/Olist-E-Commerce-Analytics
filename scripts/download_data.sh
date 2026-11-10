#!/usr/bin/env bash
# Download the Olist dataset from Kaggle into data/source/.
#
# Auth: a Kaggle API token (kaggle.com -> Settings -> API -> Create New Token),
# either in $KAGGLE_API_TOKEN or saved to ~/.kaggle/access_token.
# Uses Kaggle's REST API directly, because the kaggle CLI versions that
# support the new KGAT_ tokens need Python 3.10+.
set -euo pipefail
cd "$(dirname "$0")/.."

TOKEN="${KAGGLE_API_TOKEN:-$(cat ~/.kaggle/access_token 2>/dev/null || true)}"
if [[ -z "$TOKEN" ]]; then
  echo "No Kaggle token: set KAGGLE_API_TOKEN or create ~/.kaggle/access_token" >&2
  exit 1
fi

mkdir -p data/source
curl -L --fail --progress-bar -o data/source/olist.zip \
  -H "Authorization: Bearer ${TOKEN}" \
  https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce
unzip -o -q data/source/olist.zip -d data/source
rm data/source/olist.zip
ls -lh data/source
