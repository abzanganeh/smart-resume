variable "aws_region" {
  description = "AWS region for all job-search infra resources."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment tag (staging, production, etc.)."
  type        = string
  default     = "staging"
}

variable "postgres_url" {
  description = "PostgreSQL connection URL for Lambda functions (postgresql://…)."
  type        = string
  sensitive   = true
}

variable "apify_api_token" {
  description = "Apify API token for the Google Jobs scraper actor."
  type        = string
  sensitive   = true
}

variable "apify_actor_id" {
  description = "Apify actor ID for Google Jobs scraping."
  type        = string
  default     = "automation-lab/google-jobs-scraper"
}

variable "job_cache_ttl_common_seconds" {
  description = "TTL for commonly cached job rows."
  type        = number
  default     = 3600
}

variable "lambda_apify_cache_worker_zip" {
  description = "Path to the apify_cache_worker deployment package (.zip)."
  type        = string
  default     = "build/apify_cache_worker.zip"
}

variable "lambda_job_cache_writer_zip" {
  description = "Path to the job_cache_writer deployment package (.zip)."
  type        = string
  default     = "build/job_cache_writer.zip"
}

variable "lambda_alert_dispatcher_zip" {
  description = "Path to the alert_dispatcher deployment package (.zip)."
  type        = string
  default     = "build/alert_dispatcher.zip"
}

variable "lambda_notification_scheduler_zip" {
  description = "Path to the notification_scheduler deployment package (.zip)."
  type        = string
  default     = "build/notification_scheduler.zip"
}

variable "lambda_career_page_poller_zip" {
  description = "Path to the career_page_poller deployment package (.zip)."
  type        = string
  default     = "build/career_page_poller.zip"
}

variable "lambda_career_matcher_zip" {
  description = "Path to the career_matcher deployment package (.zip)."
  type        = string
  default     = "build/career_matcher.zip"
}

variable "lambda_career_poll_worker_zip" {
  description = "Path to the career_poll_worker deployment package (.zip)."
  type        = string
  default     = "build/career_poll_worker.zip"
}

variable "career_poll_worker_concurrency" {
  description = "Reserved concurrent executions for one-company poll workers."
  type        = number
  default     = 10
}

variable "stripe_secret_key" {
  description = "Stripe secret key consumed by the price-sync drift detector."
  type        = string
  sensitive   = true
  default     = ""
}

variable "resend_api_key" {
  description = "Resend API key consumed by the notification dispatcher."
  type        = string
  sensitive   = true
  default     = ""
}

variable "lambda_runtime" {
  description = "Python runtime for Lambda functions."
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout_seconds" {
  description = "Default Lambda timeout in seconds."
  type        = number
  default     = 300
}

variable "lambda_memory_mb" {
  description = "Default Lambda memory in MB."
  type        = number
  default     = 512
}
