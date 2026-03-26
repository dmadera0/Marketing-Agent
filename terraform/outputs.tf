output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.content_engine.id
}

output "public_ip" {
  description = "Elastic IP — point your DNS A record here"
  value       = aws_eip.content_engine.public_ip
}

output "api_url" {
  description = "Content Engine API base URL (HTTP — set up HTTPS via nginx)"
  value       = "http://${aws_eip.content_engine.public_ip}:8000"
}

output "ssh_command" {
  description = "SSH into the instance"
  value       = "ssh -i ~/.ssh/${var.key_pair_name}.pem ec2-user@${aws_eip.content_engine.public_ip}"
}

output "ssm_setup_hint" {
  description = "How to load secrets into SSM Parameter Store before first deploy"
  value       = <<-EOT
    Run these commands to populate secrets (replace values with your real keys):

      REGION=${var.aws_region}
      ENV=${var.environment}
      PREFIX=/buenavistaai/$ENV

      aws ssm put-parameter --name $PREFIX/ANTHROPIC_API_KEY      --value "sk-ant-..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/REVIEW_TOKEN_SECRET     --value "$(openssl rand -hex 32)" --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/MEDIUM_INTEGRATION_TOKEN --value "..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/WP_APP_PASSWORD          --value "..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/LINKEDIN_ACCESS_TOKEN    --value "..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/TWITTER_API_KEY          --value "..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/TWITTER_API_SECRET       --value "..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/TWITTER_ACCESS_TOKEN     --value "..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/TWITTER_ACCESS_TOKEN_SECRET --value "..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/FACEBOOK_PAGE_TOKEN      --value "..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/INSTAGRAM_ACCESS_TOKEN   --value "..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/SMTP_PASS                --value "..." --type SecureString --region $REGION
      aws ssm put-parameter --name $PREFIX/REVIEW_EMAIL             --value "you@buenavistaaisolutions.com" --type String --region $REGION
      aws ssm put-parameter --name $PREFIX/APP_BASE_URL             --value "https://content.buenavistaaisolutions.com" --type String --region $REGION
      aws ssm put-parameter --name $PREFIX/BLOG_BASE_URL            --value "https://www.buenavistaaisolutions.com/blog" --type String --region $REGION
  EOT
}
