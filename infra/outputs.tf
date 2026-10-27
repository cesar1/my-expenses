output "public_ip" {
  description = "Elastic IP the app is served on"
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  value = aws_instance.host.id
}

output "data_volume_id" {
  description = "EBS volume holding expenses.db"
  value       = aws_ebs_volume.data.id
}

output "ssm_shell_command" {
  description = "Open a shell on the box over SSM"
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.host.id}"
}
