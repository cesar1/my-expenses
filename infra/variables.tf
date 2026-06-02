variable "region" {
  type    = string
  default = "us-west-2"
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "ssh_cidr" {
  type        = string
  description = "CIDR allowed to SSH to the instance. Use your home IP /32 — find it at https://checkip.amazonaws.com."
}

variable "github_repo_url" {
  type        = string
  description = "HTTPS URL of the GitHub repo to clone on first boot. Must be public or accessible without auth."
  default     = "https://github.com/cesar1/my-expenses.git"
}

variable "key_pem_output_path" {
  type        = string
  description = "Local path (relative to infra/) where the generated SSH private key is written."
  default     = "./.ssh/expense-tracker.pem"
}
