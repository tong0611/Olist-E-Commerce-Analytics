output "lake_bucket" {
  description = "Put this in .env as S3_BUCKET"
  value       = aws_s3_bucket.lake.bucket
}

output "ingestion_role_arn" {
  value = aws_iam_role.ingestion.arn
}

output "aws_config_snippet" {
  description = "Append to ~/.aws/config, then set AWS_PROFILE=olist-ingestion in .env"
  value       = <<-EOT
    [profile olist-ingestion]
    role_arn       = ${aws_iam_role.ingestion.arn}
    source_profile = ${var.aws_profile}
    region         = ${var.aws_region}
  EOT
}
