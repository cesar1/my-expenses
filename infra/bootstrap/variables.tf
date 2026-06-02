variable "region" {
  type    = string
  default = "us-west-2"
}

variable "state_bucket_name" {
  type        = string
  description = "S3 bucket for Terraform state. Must be globally unique across all AWS accounts."
}

variable "lock_table_name" {
  type    = string
  default = "expense-tracker-tf-lock"
}
