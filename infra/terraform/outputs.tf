output "job_cache_queue_url" {
  description = "SQS queue URL for Apify cache batches (JOB_CACHE_SQS_URL)."
  value       = aws_sqs_queue.job_cache.url
}

output "job_cache_queue_arn" {
  description = "SQS queue ARN for IAM policies."
  value       = aws_sqs_queue.job_cache.arn
}

output "apify_cache_worker_lambda_arn" {
  description = "ARN of the hourly Apify cache worker Lambda."
  value       = aws_lambda_function.apify_cache_worker.arn
}

output "job_cache_writer_lambda_arn" {
  description = "ARN of the SQS consumer Lambda that writes job_cache rows."
  value       = aws_lambda_function.job_cache_writer.arn
}

output "alert_dispatcher_lambda_arn" {
  description = "ARN of the saved-search alert dispatcher Lambda."
  value       = aws_lambda_function.alert_dispatcher.arn
}

output "eventbridge_hourly_rule_arn" {
  description = "EventBridge rule ARN for the hourly Apify cache schedule, or null when disabled."
  value       = one(aws_cloudwatch_event_rule.apify_cache_hourly[*].arn)
}

output "eventbridge_daily_alert_rule_arn" {
  description = "EventBridge rule ARN for daily saved-search alerts."
  value       = aws_cloudwatch_event_rule.alert_daily.arn
}

output "eventbridge_weekly_alert_rule_arn" {
  description = "EventBridge rule ARN for weekly saved-search alerts."
  value       = aws_cloudwatch_event_rule.alert_weekly.arn
}

output "notification_scheduler_lambda_arn" {
  description = "ARN of the multi-purpose notification scheduler Lambda."
  value       = aws_lambda_function.notification_scheduler.arn
}

output "eventbridge_grace_tick_rule_arn" {
  description = "EventBridge rule ARN for the §7.6 grace-tick (every 15 minutes)."
  value       = aws_cloudwatch_event_rule.billing_grace_tick.arn
}

output "eventbridge_price_sync_rule_arn" {
  description = "EventBridge rule ARN for the nightly Stripe price-sync (§7.8)."
  value       = aws_cloudwatch_event_rule.billing_price_sync.arn
}

output "eventbridge_notification_dispatch_rule_arn" {
  description = "EventBridge rule ARN for the every-5-minute notification dispatch."
  value       = aws_cloudwatch_event_rule.notify_dispatch.arn
}
