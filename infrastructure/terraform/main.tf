resource "aws_security_group" "edgerelay" {
  name        = "EdgeRelay-SG"
  description = "Security group for EdgeRelay server"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["128.185.168.201/32"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_instance" "edgerelay" {
  ami                  = var.ami_id
  instance_type        = var.instance_type
  key_name             = var.key_name
  subnet_id            = var.subnet_id
  iam_instance_profile = "EdgeRelay-EC2-SSM-Role"

  vpc_security_group_ids = [
    aws_security_group.edgerelay.id
  ]

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 20
    iops                  = 3000
    throughput            = 125
    encrypted             = false
    delete_on_termination = true
  }

  tags = {
    Name = "EdgeRelay-Server"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [ami]
  }
}
