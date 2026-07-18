# Remote state. The bucket + lock table come from ../../bootstrap (run once).
#
# Fill in the bucket name after `terraform apply` in bootstrap prints it, then:
#   terraform init
#
# Values here cannot be variables -- Terraform reads the backend block before
# variables exist. That is a Terraform constraint, not an oversight.

terraform {
  backend "s3" {
    # Account 005572111409. Create this bucket first via ../../bootstrap:
    #   terraform apply -var state_bucket_name=video-compiler-tfstate-005572111409
    bucket = "video-compiler-tfstate-005572111409"
    key    = "envs/dev/terraform.tfstate"
    region = "ap-south-1"

    dynamodb_table = "video-compiler-tf-lock"
    encrypt        = true
  }
}
