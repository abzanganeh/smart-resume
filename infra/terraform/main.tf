terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "smart-resume-${var.environment}-jobs"
  common_tags = {
    Project     = "smart-resume"
    Environment = var.environment
    Component   = "job-search"
  }
}

# ---------------------------------------------------------------------------
# SQS — decouple Apify fetch from PostgreSQL writes
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "job_cache_dlq" {
  name                      = "${local.name_prefix}-cache-dlq"
  message_retention_seconds = 1209600 # 14 days
  tags                      = local.common_tags
}

resource "aws_sqs_queue" "job_cache" {
  name                       = "${local.name_prefix}-cache"
  visibility_timeout_seconds = var.lambda_timeout_seconds * 2
  receive_wait_time_seconds  = 10
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.job_cache_dlq.arn
    maxReceiveCount     = 3
  })
  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# IAM — shared Lambda execution role
# ---------------------------------------------------------------------------

resource "aws_iam_role" "job_lambda" {
  name = "${local.name_prefix}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "job_lambda_basic" {
  role       = aws_iam_role.job_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "job_lambda_sqs" {
  name = "${local.name_prefix}-sqs"
  role = aws_iam_role.job_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility",
        ]
        Resource = [
          aws_sqs_queue.job_cache.arn,
          aws_sqs_queue.job_cache_dlq.arn,
        ]
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# Lambda — apify cache worker (EventBridge hourly)
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "apify_cache_worker" {
  function_name = "${local.name_prefix}-apify-cache"
  role          = aws_iam_role.job_lambda.arn
  handler       = "handler.handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout_seconds
  memory_size   = var.lambda_memory_mb
  filename      = var.lambda_apify_cache_worker_zip
  source_code_hash = filebase64sha256(var.lambda_apify_cache_worker_zip)

  environment {
    variables = {
      POSTGRES_URL      = var.postgres_url
      APIFY_API_TOKEN   = var.apify_api_token
      APIFY_ACTOR_ID    = var.apify_actor_id
      JOB_CACHE_SQS_URL = aws_sqs_queue.job_cache.url
      AWS_REGION        = var.aws_region
    }
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_event_rule" "apify_cache_hourly" {
  name                = "${local.name_prefix}-apify-hourly"
  description         = "Hourly Apify Google Jobs cache refresh"
  schedule_expression = "rate(1 hour)"
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "apify_cache_hourly" {
  rule      = aws_cloudwatch_event_rule.apify_cache_hourly.name
  target_id = "apify-cache-worker"
  arn       = aws_lambda_function.apify_cache_worker.arn
}

resource "aws_lambda_permission" "apify_cache_hourly" {
  statement_id  = "AllowEventBridgeApifyHourly"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.apify_cache_worker.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.apify_cache_hourly.arn
}

# ---------------------------------------------------------------------------
# Lambda — job cache writer (SQS trigger)
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "job_cache_writer" {
  function_name = "${local.name_prefix}-cache-writer"
  role          = aws_iam_role.job_lambda.arn
  handler       = "handler.handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout_seconds
  memory_size   = var.lambda_memory_mb
  filename      = var.lambda_job_cache_writer_zip
  source_code_hash = filebase64sha256(var.lambda_job_cache_writer_zip)

  environment {
    variables = {
      POSTGRES_URL                  = var.postgres_url
      JOB_CACHE_TTL_COMMON_SECONDS  = tostring(var.job_cache_ttl_common_seconds)
      AWS_REGION                    = var.aws_region
    }
  }

  tags = local.common_tags
}

resource "aws_lambda_event_source_mapping" "job_cache_sqs" {
  event_source_arn = aws_sqs_queue.job_cache.arn
  function_name    = aws_lambda_function.job_cache_writer.arn
  batch_size       = 5
  function_response_types = ["ReportBatchItemFailures"]
}

# ---------------------------------------------------------------------------
# Lambda — alert dispatcher (EventBridge daily + weekly)
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "alert_dispatcher" {
  function_name = "${local.name_prefix}-alert-dispatcher"
  role          = aws_iam_role.job_lambda.arn
  handler       = "handler.handler"
  runtime       = var.lambda_runtime
  timeout       = 120
  memory_size   = var.lambda_memory_mb
  filename      = var.lambda_alert_dispatcher_zip
  source_code_hash = filebase64sha256(var.lambda_alert_dispatcher_zip)

  environment {
    variables = {
      POSTGRES_URL = var.postgres_url
      AWS_REGION   = var.aws_region
    }
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_event_rule" "alert_daily" {
  name                = "${local.name_prefix}-alerts-daily"
  description         = "Daily saved-search job alerts"
  schedule_expression = "cron(0 8 * * ? *)" # 08:00 UTC daily
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "alert_daily" {
  rule      = aws_cloudwatch_event_rule.alert_daily.name
  target_id = "alert-dispatcher-daily"
  arn       = aws_lambda_function.alert_dispatcher.arn
  input     = jsonencode({ schedule = "daily" })
}

resource "aws_lambda_permission" "alert_daily" {
  statement_id  = "AllowEventBridgeAlertDaily"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.alert_dispatcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.alert_daily.arn
}

resource "aws_cloudwatch_event_rule" "alert_weekly" {
  name                = "${local.name_prefix}-alerts-weekly"
  description         = "Weekly saved-search job alerts"
  schedule_expression = "cron(0 8 ? * MON *)" # Monday 08:00 UTC
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "alert_weekly" {
  rule      = aws_cloudwatch_event_rule.alert_weekly.name
  target_id = "alert-dispatcher-weekly"
  arn       = aws_lambda_function.alert_dispatcher.arn
  input     = jsonencode({ schedule = "weekly" })
}

resource "aws_lambda_permission" "alert_weekly" {
  statement_id  = "AllowEventBridgeAlertWeekly"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.alert_dispatcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.alert_weekly.arn
}
