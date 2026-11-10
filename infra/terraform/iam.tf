# ---------------------------------------------------------------------------
# Ingestion role: least-privilege identity the extractor runs as.
#
# It's a ROLE (temporary credentials via sts:AssumeRole), not an IAM user
# with long-lived access keys, so no secrets end up in Terraform state.
# Your admin profile assumes it through ~/.aws/config (see outputs).
# Later phases add separate roles for Lambda, Glue and Snowflake.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ingestion_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_iam_role" "ingestion" {
  name                 = "${var.project}-ingestion"
  description          = "Writes source extracts into the raw zone of the data lake"
  assume_role_policy   = data.aws_iam_policy_document.ingestion_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "ingestion" {
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
    sid       = "ReadWriteRawZone"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.lake.arn}/raw/*"]
  }
}

resource "aws_iam_role_policy" "ingestion" {
  name   = "raw-zone-write"
  role   = aws_iam_role.ingestion.id
  policy = data.aws_iam_policy_document.ingestion.json
}
