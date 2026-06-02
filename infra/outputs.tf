output "public_ip" {
  description = "Elastic IP — paste into the EC2_HOST GitHub repo secret"
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  value = aws_instance.app.id
}

output "ssh_command" {
  description = "Quick SSH check after first boot"
  value       = "ssh -i ${var.key_pem_output_path} ec2-user@${aws_eip.app.public_ip}"
}

output "private_key_path" {
  description = "Local path to the generated SSH private key — paste its contents into the EC2_SSH_KEY GitHub repo secret"
  value       = local_sensitive_file.private_key.filename
}
