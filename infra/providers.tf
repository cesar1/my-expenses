provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "expense-tracker"
      ManagedBy = "terraform"
    }
  }
}
