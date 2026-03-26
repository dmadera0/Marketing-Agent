###############################################################################
# BuenaVista AI Solutions — Content Engine Infrastructure
# Terraform >= 1.6  |  AWS Provider ~> 5.0
###############################################################################

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment to store state remotely (recommended for production)
  # backend "s3" {
  #   bucket = "buenavistaai-terraform-state"
  #   key    = "content-engine/terraform.tfstate"
  #   region = "us-west-2"
  # }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "BuenaVistaAI-ContentEngine"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

###############################################################################
# Data sources
###############################################################################

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Latest Amazon Linux 2023 AMI
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

###############################################################################
# SSM Parameter Store — all secrets stored here, never on disk
# Populate with:
#   aws ssm put-parameter --name /buenavistaai/prod/ANTHROPIC_API_KEY \
#     --value "sk-ant-..." --type SecureString --region us-west-2
###############################################################################

locals {
  ssm_prefix = "/buenavistaai/${var.environment}"
  # List every parameter name the EC2 instance needs read access to
  ssm_param_names = [
    "ANTHROPIC_API_KEY",
    "REVIEW_TOKEN_SECRET",
    "MEDIUM_INTEGRATION_TOKEN",
    "WP_APP_PASSWORD",
    "LINKEDIN_ACCESS_TOKEN",
    "TWITTER_API_KEY",
    "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN",
    "TWITTER_ACCESS_TOKEN_SECRET",
    "FACEBOOK_PAGE_TOKEN",
    "INSTAGRAM_ACCESS_TOKEN",
    "SMTP_PASS",
  ]
}

resource "aws_iam_policy" "ssm_read_secrets" {
  name        = "buenavistaai-ssm-read-secrets-${var.environment}"
  description = "Allow EC2 to read BuenaVista AI secrets from SSM Parameter Store"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = "arn:aws:ssm:${var.aws_region}:*:parameter${local.ssm_prefix}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = "*"
        Condition = {
          StringLike = {
            "kms:ViaService" = "ssm.${var.aws_region}.amazonaws.com"
          }
        }
      }
    ]
  })
}

###############################################################################
# Security groups
###############################################################################

resource "aws_security_group" "content_engine" {
  name        = "buenavistaai-content-engine-${var.environment}"
  description = "Content engine EC2 — HTTP/HTTPS inbound, all outbound"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH — restrict to your IP in production"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

###############################################################################
# IAM Role — EC2 → SSM Session Manager + Parameter Store read
###############################################################################

resource "aws_iam_role" "ec2_role" {
  name = "buenavistaai-content-engine-role-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ssm_secrets" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ssm_read_secrets.arn
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "buenavistaai-content-engine-profile-${var.environment}"
  role = aws_iam_role.ec2_role.name
}

###############################################################################
# EC2 Instance
###############################################################################

resource "aws_instance" "content_engine" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name
  vpc_security_group_ids = [aws_security_group.content_engine.id]

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    environment = var.environment
    aws_region  = var.aws_region
    ssm_prefix  = local.ssm_prefix
  }))

  metadata_options {
    http_tokens = "required"  # IMDSv2
  }

  tags = {
    Name = "buenavistaai-content-engine-${var.environment}"
  }
}

resource "aws_eip" "content_engine" {
  instance = aws_instance.content_engine.id
  domain   = "vpc"
}

###############################################################################
# CloudWatch — basic monitoring
###############################################################################

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "buenavistaai-cpu-high-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "CPU > 80% for 10 minutes"
  dimensions = {
    InstanceId = aws_instance.content_engine.id
  }
}
