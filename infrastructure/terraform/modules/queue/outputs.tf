output "video_queue_url" {
  value = aws_sqs_queue.video.id
}

output "video_queue_arn" {
  value = aws_sqs_queue.video.arn
}

output "video_queue_name" {
  description = "The CloudWatch dimension the GPU ASG scales on."
  value       = aws_sqs_queue.video.name
}

output "video_dlq_url" {
  value = aws_sqs_queue.video_dlq.id
}

output "video_dlq_arn" {
  value = aws_sqs_queue.video_dlq.arn
}
