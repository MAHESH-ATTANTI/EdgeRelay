resource "aws_iam_role" "edgerelay_ec2" {
  name                 = "EdgeRelay-EC2-SSM-Role"
  description          = "Allows EC2 instances to call AWS services on your behalf."
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_instance_profile" "edgerelay_ec2" {
  name = "EdgeRelay-EC2-SSM-Role"
  role = aws_iam_role.edgerelay_ec2.name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.edgerelay_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"

  lifecycle {
    prevent_destroy = true
  }
}
