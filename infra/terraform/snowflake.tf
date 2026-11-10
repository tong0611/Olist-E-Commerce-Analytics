# ---------------------------------------------------------------------------
# Role Snowflake assumes (via a STORAGE INTEGRATION) to read the lake.
#
# Two-step handshake:
#   1. apply with the variables below empty -> role exists, trusts only this
#      account (a harmless placeholder)
#   2. in Snowflake: CREATE STORAGE INTEGRATION ... then DESC INTEGRATION;
#      copy STORAGE_AWS_IAM_USER_ARN / STORAGE_AWS_EXTERNAL_ID into
#      terraform.tfvars and apply again -> only Snowflake's IAM user, presenting
#      the external id, can assume the role.
# ---------------------------------------------------------------------------

variable "snowflake_iam_user_arn" {
  description = "STORAGE_AWS_IAM_USER_ARN from DESC INTEGRATION (empty until the integration exists)"
  type        = string
  default     = ""
}

variable "snowflake_external_id" {
  description = "STORAGE_AWS_EXTERNAL_ID from DESC INTEGRATION"
  type        = string
  default     = ""
}

locals {
  snowflake_trust_ready = var.snowflake_iam_user_arn != "" && var.snowflake_external_id != ""
}

data "aws_iam_policy_document" "snowflake_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type = "AWS"
      identifiers = [
        local.snowflake_trust_ready
        ? var.snowflake_iam_user_arn
        : "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
      ]
    }
    dynamic "condition" {
      for_each = local.snowflake_trust_ready ? [1] : []
      content {
        test     = "StringEquals"
        variable = "sts:ExternalId"
        values   = [var.snowflake_external_id]
      }
    }
  }
}

resource "aws_iam_role" "snowflake" {
  name                 = "${var.project}-snowflake"
  description          = "Assumed by the Snowflake storage integration to read the data lake"
  assume_role_policy   = data.aws_iam_policy_document.snowflake_trust.json
  max_session_duration = 3600
}

# Read-only, raw/ zone only (processed/ gets added when Glue lands in Phase 4)
data "aws_iam_policy_document" "snowflake_read" {
  statement {
    sid       = "BucketLocation"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.lake.arn]
  }

  statement {
    sid       = "ListRawPrefix"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.lake.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*"]
    }
  }

  statement {
    sid       = "ReadRawObjects"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.lake.arn}/raw/*"]
  }
}

resource "aws_iam_role_policy" "snowflake" {
  name   = "lake-raw-read"
  role   = aws_iam_role.snowflake.id
  policy = data.aws_iam_policy_document.snowflake_read.json
}

output "snowflake_role_arn" {
  description = "Use as STORAGE_AWS_ROLE_ARN in the Snowflake storage integration"
  value       = aws_iam_role.snowflake.arn
}

output "snowflake_trust_configured" {
  value = local.snowflake_trust_ready
}
