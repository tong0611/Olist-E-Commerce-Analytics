# ---------------------------------------------------------------------------
# Data lake bucket
#   raw/         - exact copies of source extracts (Parquet + manifests)
#   processed/   - cleaned output of the Glue jobs (Phase 4)
#   quarantine/  - records that failed validation (Phase 3)
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  # Bucket names are global, so include the account id to make it unique
  lake_bucket_name = "${var.project}-lake-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket" "lake" {
  bucket = local.lake_bucket_name
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    object_ownership = "BucketOwnerEnforced" # disables ACLs entirely
  }
}

resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled" # recover from bad overwrites / accidental deletes
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3: free, unlike KMS
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "raw-to-infrequent-access"
    status = "Enabled"
    filter {
      and {
        prefix                   = "raw/"
        object_size_greater_than = 131072 # IA bills small objects as 128 KB, so skip them
      }
    }
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }

  rule {
    id     = "expire-quarantine"
    status = "Enabled"
    filter {
      prefix = "quarantine/"
    }
    expiration {
      days = 90
    }
  }

  depends_on = [aws_s3_bucket_versioning.lake]
}

# Reject any request that isn't over HTTPS
data "aws_iam_policy_document" "lake_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.lake.arn,
      "${aws_s3_bucket.lake.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "lake" {
  bucket     = aws_s3_bucket.lake.id
  policy     = data.aws_iam_policy_document.lake_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.lake]
}
