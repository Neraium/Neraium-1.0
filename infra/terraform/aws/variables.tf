variable "project_name" {
  type        = string
  description = "Project slug used for resource naming."
  default     = "neraium"
}

variable "environment" {
  type        = string
  description = "Environment name (dev/staging/prod)."
  default     = "prod"
}

variable "aws_region" {
  type        = string
  description = "AWS region."
  default     = "us-east-2"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for VPC."
  default     = "10.40.0.0/16"
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "Public subnet CIDRs for ALB."
  default     = ["10.40.0.0/20", "10.40.16.0/20"]
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "Private subnet CIDRs for ECS services."
  default     = ["10.40.128.0/20", "10.40.144.0/20"]
}

variable "availability_zones" {
  type        = list(string)
  description = "Availability zones aligned with subnet lists."
  default     = ["us-east-2a", "us-east-2b"]
}

variable "backend_image_tag" {
  type        = string
  description = "Backend container image tag in ECR."
  default     = "latest"
}

variable "backend_container_port" {
  type        = number
  description = "Backend container port."
  default     = 80
}

variable "backend_cpu" {
  type        = number
  description = "Fargate task CPU units."
  default     = 512
}

variable "backend_memory" {
  type        = number
  description = "Fargate task memory (MiB)."
  default     = 1024
}

variable "backend_desired_count" {
  type        = number
  description = "Desired ECS service task count."
  default     = 2
}

variable "api_token_secret_arn" {
  type        = string
  description = "AWS Secrets Manager ARN containing NERAIUM_API_TOKEN value."
}

variable "hosted_zone_id" {
  type        = string
  description = "Route53 hosted zone ID for optional DNS record."
  default     = ""
}

variable "api_domain_name" {
  type        = string
  description = "Optional custom API domain (e.g. api.neraium.com)."
  default     = ""
}

variable "certificate_arn" {
  type        = string
  description = "Optional ACM certificate ARN for HTTPS listener."
  default     = ""
}

variable "enable_nat_gateway" {
  type        = bool
  description = "Whether to create NAT gateway for private subnet egress."
  default     = true
}

variable "enable_waf" {
  type        = bool
  description = "Whether to attach WAFv2 to ALB."
  default     = true
}

variable "waf_rate_limit" {
  type        = number
  description = "Per-5-minute IP rate limit for ALB requests."
  default     = 2000
}

variable "autoscaling_min_capacity" {
  type        = number
  description = "ECS service autoscaling min tasks."
  default     = 2
}

variable "autoscaling_max_capacity" {
  type        = number
  description = "ECS service autoscaling max tasks."
  default     = 8
}

variable "autoscaling_cpu_target_percent" {
  type        = number
  description = "Target CPU utilization for ECS scaling."
  default     = 60
}
