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

variable "snapshot_retention_count" {
  type        = number
  description = "How many daily DLM snapshots of the app volume to keep. Snapshots are incremental, so each extra day costs only the changed blocks."
  default     = 7
}

variable "snapshot_time_utc" {
  type        = string
  description = "UTC start time for the daily snapshot window, HH:MM. DLM starts within an hour of this. Default is 09:00 UTC (02:00 US Pacific)."
  default     = "09:00"
}
