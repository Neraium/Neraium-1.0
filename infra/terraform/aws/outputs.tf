output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "alb_dns_name" {
  value = aws_lb.api.dns_name
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.backend.name
}

output "api_url" {
  value = var.api_domain_name != "" ? "https://${var.api_domain_name}" : "http://${aws_lb.api.dns_name}"
}
