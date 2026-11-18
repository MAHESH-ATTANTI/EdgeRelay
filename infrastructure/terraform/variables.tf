
variable "aws_region" {
  description = "AWS region for EdgeRelay"
  type        = string
  default     = "ap-south-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "ami_id" {
  description = "Ubuntu AMI ID"
  type        = string
  default     = "ami-09d8c1e69d114dbf7"
}

variable "vpc_id" {
  description = "Existing VPC ID"
  type        = string
  default     = "vpc-0ab50a15b3fbff548"
}

variable "subnet_id" {
  description = "Existing subnet ID"
  type        = string
  default     = "subnet-0ff5a436e30e35302"
}

variable "key_name" {
  description = "Existing EC2 key pair name"
  type        = string
  default     = "edgerelay-key"
}
