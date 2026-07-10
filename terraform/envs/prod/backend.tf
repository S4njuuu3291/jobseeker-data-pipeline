terraform {
  backend "s3" {
    bucket  = "jobscraper-terraform-state-730335315755"
    key     = "terraform.tfstate"
    region  = "ap-southeast-1"
    encrypt = true
    # Uncomment line below AFTER first terraform apply (to create DynamoDB table)
    # Then run: terraform init
    use_lockfile = true
  }
}
