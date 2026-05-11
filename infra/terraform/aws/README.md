# AWS Terraform Scaffold (Phase 1)

This stack provisions a pilot-safe baseline for Neraium:
- VPC with public (ALB) and private (ECS tasks) subnets
- Internet-facing ALB with `/api/ready` target health checks
- ECR repository for backend image
- ECS Fargate cluster/service/task definition
- CloudWatch log group (30-day retention)
- Secrets Manager injection for `NERAIUM_API_TOKEN`
- Optional Route53 alias + ACM TLS listener

## Usage
1. `cd infra/terraform/aws`
2. Copy `terraform.tfvars.example` to `terraform.tfvars` and fill values.
3. `terraform init`
4. `terraform plan`
5. `terraform apply`

## Notes
- This is a production baseline scaffold; tune IAM least privilege, WAF/rate limits, NAT strategy, and autoscaling before customer rollout.
- Backend image tag is controlled by `backend_image_tag`; integrate with CI image publishing.
