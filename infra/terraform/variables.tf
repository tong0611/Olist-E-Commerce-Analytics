variable "project" {
  description = "Prefix for all resource names"
  type        = string
  default     = "olist-pipeline"
}

variable "aws_region" {
  description = "AWS region for all resources (use the same region for Snowflake later to avoid transfer costs)"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Local AWS CLI profile Terraform runs as (an admin profile, NOT the pipeline role)"
  type        = string
  default     = "olist-admin"
}

variable "budget_limit_usd" {
  description = "Monthly cost budget; you get emailed at 80% actual and 100% forecasted spend"
  type        = number
  default     = 10
}

variable "alert_email" {
  description = "Email address for budget alerts (set it in terraform.tfvars, which is gitignored)"
  type        = string
}
