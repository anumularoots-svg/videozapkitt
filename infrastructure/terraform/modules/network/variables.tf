variable "project" {
  description = "Project name, used as a resource name prefix."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, prod)."
  type        = string
}

variable "aws_region" {
  description = "AWS region."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "AZs to spread subnets across. Two is the minimum for RDS."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "At least 2 AZs are required -- RDS subnet groups demand it."
  }
}

variable "single_nat_gateway" {
  description = "One NAT for the whole VPC (dev, ~$32/mo) vs one per AZ (prod, HA)."
  type        = bool
  default     = true
}
