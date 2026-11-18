
# EdgeRelay - Terraform Infrastructure

## Overview

This directory contains Terraform configuration used to manage the existing AWS infrastructure for the EdgeRelay project.

Terraform is used to define, import, and verify AWS resources through Infrastructure as Code (IaC).

## Technology Stack

- Terraform
- AWS
- AWS Provider
- Amazon EC2
- Amazon VPC
- AWS IAM

## AWS Configuration

- Region: ap-south-1
- EC2 Instance: EdgeRelay-Server
- Instance Type: t3.small
- Operating System: Ubuntu 24.04 LTS
- Security Group: EdgeRelay-SG
- IAM Role: EdgeRelay-EC2-SSM-Role

## Project Structure

```text
terraform/
├── .terraform.lock.hcl
├── provider.tf
├── variables.tf
├── main.tf
├── iam.tf
├── outputs.tf
└── README.md
```

## Terraform Files

| File | Purpose |
|---|---|
| provider.tf | AWS provider configuration |
| variables.tf | Reusable configuration variables |
| main.tf | EC2 instance and security group |
| iam.tf | IAM role and instance profile |
| outputs.tf | Infrastructure output values |
| .terraform.lock.hcl | Provider version and dependency lock |

## Managed AWS Resources

1. EC2 Instance
2. EC2 Security Group
3. IAM Role
4. IAM Instance Profile
5. IAM Role Policy Attachment

## Terraform Setup

Initialize Terraform:

```bash
terraform init
```

Format configuration:

```bash
terraform fmt
```

Validate configuration:

```bash
terraform validate
```

Review infrastructure changes:

```bash
terraform plan
```

Display outputs:

```bash
terraform output
```

## Importing Existing Resources

Existing AWS resources were imported into Terraform state instead of creating duplicate infrastructure.

Resources imported:

- EC2 Instance
- Security Group
- IAM Role
- IAM Instance Profile
- IAM Role Policy Attachment

## Verification

The Terraform configuration was validated successfully.

The final Terraform plan reported:

```text
No changes. Your infrastructure matches the configuration.
```

The output-only apply completed with:

```text
Resources: 0 added, 0 changed, 0 destroyed.
```

## State File Security

Terraform state files contain infrastructure information and must not be committed to Git.

The following files and directories are excluded through the root `.gitignore`:

- .terraform/
- terraform.tfstate
- terraform.tfstate.backup

The provider lock file `.terraform.lock.hcl` is tracked in Git.

## Important Notes

- Existing AWS infrastructure was imported and verified.
- No duplicate EC2 instance was created.
- The existing EC2 instance was not recreated.
- Review every Terraform plan before applying changes.
- Never commit AWS credentials or Terraform state files.
- Keep a secure backup of Terraform state.
