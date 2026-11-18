
output "ec2_instance_id" {
  description = "EdgeRelay EC2 instance ID"
  value       = aws_instance.edgerelay.id
}

output "ec2_private_ip" {
  description = "EdgeRelay EC2 private IP"
  value       = aws_instance.edgerelay.private_ip
}

output "security_group_id" {
  description = "EdgeRelay security group ID"
  value       = aws_security_group.edgerelay.id
}

output "iam_role_arn" {
  description = "EdgeRelay EC2 IAM role ARN"
  value       = aws_iam_role.edgerelay_ec2.arn
}
