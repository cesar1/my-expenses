variable "region" {
  type    = string
  default = "us-west-2"
}

variable "availability_zone" {
  type        = string
  description = "AZ for the instance and the data volume. They must match -- an EBS volume only attaches within its own AZ -- so changing this means moving the data volume via a snapshot first."
  default     = "us-west-2d"
}

variable "instance_type" {
  type        = string
  description = "Must be arm64 (Graviton) to match the Ubuntu arm64 AMI lookup in main.tf."
  default     = "t4g.medium"
}

variable "key_name" {
  type        = string
  description = "Existing EC2 key pair for break-glass SSH. Changing it replaces the instance."
  default     = "oreo"
}

variable "ssh_cidr" {
  type        = string
  description = "CIDR allowed to SSH to the instance, e.g. your home IP /32 (https://checkip.amazonaws.com). Null (the default) keeps port 22 closed; use SSM instead."
  default     = null
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
