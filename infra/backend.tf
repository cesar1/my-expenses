terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
  }

  # Edit `bucket` to match the name you used when running infra/bootstrap.
  backend "s3" {
    bucket         = "expense-tracker-tf-state-870757819272"
    key            = "expense-tracker/main.tfstate"
    region         = "us-west-2"
    dynamodb_table = "expense-tracker-tf-lock"
    encrypt        = true
  }
}
