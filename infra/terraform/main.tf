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

# ---------------------------------------------------------------------------
# Lambda — notification scheduler (Step 31 + Step 37 hardening)
#
# Multi-purpose worker driven by EventBridge.  The ``schedule`` field
# in the event payload selects which workflow runs:
#
# - dispatch_notifications  (every 5 minutes) — fan out pending outbox rows
# - grace_tick              (every 15 minutes) — §7.6 state machine
# - stripe_price_sync       (nightly 03:00 UTC) — §7.8 drift detector
# - closure_tick            (hourly) — §19.6 account closure reminders + deletions
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "notification_scheduler" {
  function_name    = "${local.name_prefix}-notification-scheduler"
  role             = aws_iam_role.job_lambda.arn
  handler          = "handler.handler"
  runtime          = var.lambda_runtime
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb
  filename         = var.lambda_notification_scheduler_zip
  source_code_hash = filebase64sha256(var.lambda_notification_scheduler_zip)

  environment {
    variables = {
      DATABASE_URL          = var.postgres_url
      STRIPE_SECRET_KEY     = var.stripe_secret_key
      RESEND_API_KEY        = var.resend_api_key
      AWS_REGION            = var.aws_region
      APP_ENV               = var.environment
    }
  }

  tags = local.common_tags
}

# dispatch_notifications — every 5 minutes
resource "aws_cloudwatch_event_rule" "notify_dispatch" {
  name                = "${local.name_prefix}-notify-dispatch"
  description         = "Notification outbox dispatcher (every 5 minutes)"
  schedule_expression = "rate(5 minutes)"
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "notify_dispatch" {
  rule      = aws_cloudwatch_event_rule.notify_dispatch.name
  target_id = "notification-dispatch"
  arn       = aws_lambda_function.notification_scheduler.arn
  input     = jsonencode({ schedule = "dispatch_notifications" })
}

resource "aws_lambda_permission" "notify_dispatch" {
  statement_id  = "AllowEventBridgeNotifyDispatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notification_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.notify_dispatch.arn
}

# grace_tick — every 15 minutes (§7.6)
resource "aws_cloudwatch_event_rule" "billing_grace_tick" {
  name                = "${local.name_prefix}-billing-grace-tick"
  description         = "Billing grace-period state machine tick (§7.6)"
  schedule_expression = "rate(15 minutes)"
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "billing_grace_tick" {
  rule      = aws_cloudwatch_event_rule.billing_grace_tick.name
  target_id = "grace-tick"
  arn       = aws_lambda_function.notification_scheduler.arn
  input     = jsonencode({ schedule = "grace_tick" })
}

resource "aws_lambda_permission" "billing_grace_tick" {
  statement_id  = "AllowEventBridgeGraceTick"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notification_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.billing_grace_tick.arn
}

# stripe_price_sync — nightly (§7.8)
resource "aws_cloudwatch_event_rule" "billing_price_sync" {
  name                = "${local.name_prefix}-billing-price-sync"
  description         = "Nightly Stripe → PlanConfig drift detector (§7.8)"
  schedule_expression = "cron(0 3 * * ? *)" # 03:00 UTC daily
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "billing_price_sync" {
  rule      = aws_cloudwatch_event_rule.billing_price_sync.name
  target_id = "price-sync"
  arn       = aws_lambda_function.notification_scheduler.arn
  input     = jsonencode({ schedule = "stripe_price_sync" })
}

resource "aws_lambda_permission" "billing_price_sync" {
  statement_id  = "AllowEventBridgePriceSync"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notification_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.billing_price_sync.arn
}

# closure_tick — hourly (§19.6)
resource "aws_cloudwatch_event_rule" "account_closure_tick" {
  name                = "${local.name_prefix}-account-closure-tick"
  description         = "Account closure day-23 reminders and due deletions (§19.6)"
  schedule_expression = "rate(1 hour)"
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "account_closure_tick" {
  rule      = aws_cloudwatch_event_rule.account_closure_tick.name
  target_id = "closure-tick"
  arn       = aws_lambda_function.notification_scheduler.arn
  input     = jsonencode({ schedule = "closure_tick" })
}

resource "aws_lambda_permission" "account_closure_tick" {
  statement_id  = "AllowEventBridgeClosureTick"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notification_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.account_closure_tick.arn
}

# unverified_cleanup — daily (§18.2)
resource "aws_cloudwatch_event_rule" "unverified_account_cleanup" {
  name                = "${local.name_prefix}-unverified-account-cleanup"
  description         = "Suspend email accounts unverified after cleanup window (§18.2)"
  schedule_expression = "cron(0 4 * * ? *)"
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "unverified_account_cleanup" {
  rule      = aws_cloudwatch_event_rule.unverified_account_cleanup.name
  target_id = "unverified-cleanup"
  arn       = aws_lambda_function.notification_scheduler.arn
  input     = jsonencode({ schedule = "unverified_cleanup" })
}

resource "aws_lambda_permission" "unverified_account_cleanup" {
  statement_id  = "AllowEventBridgeUnverifiedCleanup"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notification_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.unverified_account_cleanup.arn
}

# ---------------------------------------------------------------------------
# Career Watch — page poller + matcher (pricing milestone slices 16–17)
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "career_watch_dlq" {
  name                      = "${local.name_prefix}-career-watch-dlq"
  message_retention_seconds = 1209600
  tags                      = local.common_tags
}

resource "aws_sqs_queue" "career_watch" {
  name                       = "${local.name_prefix}-career-watch"
  visibility_timeout_seconds = var.lambda_timeout_seconds * 2
  receive_wait_time_seconds  = 10
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.career_watch_dlq.arn
    maxReceiveCount     = 3
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy" "job_lambda_career_watch_sqs" {
  name = "${local.name_prefix}-career-watch-sqs"
  role = aws_iam_role.job_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility",
      ]
      Resource = [
        aws_sqs_queue.career_watch.arn,
        aws_sqs_queue.career_watch_dlq.arn,
      ]
    }]
  })
}

resource "aws_lambda_function" "career_page_poller" {
  function_name    = "${local.name_prefix}-career-page-poller"
  role             = aws_iam_role.job_lambda.arn
  handler          = "handler.handler"
  runtime          = var.lambda_runtime
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb
  filename         = var.lambda_career_page_poller_zip
  source_code_hash = filebase64sha256(var.lambda_career_page_poller_zip)

  environment {
    variables = {
      DATABASE_URL                      = var.postgres_url
      CAREER_WATCH_SCHEDULER_BATCH      = "200"
      CAREER_WATCH_SQS_URL              = aws_sqs_queue.career_watch.url
      GLOBAL_POLL_INTERVAL_TIER_1_MINUTES = "15"
      GLOBAL_POLL_INTERVAL_TIER_2_MINUTES = "30"
      GLOBAL_POLL_INTERVAL_TIER_3_MINUTES = "45"
      AWS_REGION                        = var.aws_region
    }
  }

  tags = local.common_tags
}

resource "aws_lambda_function" "career_poll_worker" {
  function_name                    = "${local.name_prefix}-career-poll-worker"
  role                             = aws_iam_role.job_lambda.arn
  handler                          = "handler.handler"
  runtime                          = var.lambda_runtime
  timeout                          = 60
  memory_size                      = var.lambda_memory_mb
  filename                         = var.lambda_career_poll_worker_zip
  source_code_hash                 = filebase64sha256(var.lambda_career_poll_worker_zip)
  reserved_concurrent_executions   = var.career_poll_worker_concurrency

  environment {
    variables = {
      DATABASE_URL = var.postgres_url
      AWS_REGION   = var.aws_region
    }
  }

  tags = local.common_tags
}

resource "aws_lambda_event_source_mapping" "career_poll_worker_sqs" {
  event_source_arn = aws_sqs_queue.career_watch.arn
  function_name    = aws_lambda_function.career_poll_worker.arn
  batch_size       = 1
  function_response_types = ["ReportBatchItemFailures"]
}

resource "aws_lambda_function" "career_matcher" {
  function_name    = "${local.name_prefix}-career-matcher"
  role             = aws_iam_role.job_lambda.arn
  handler          = "handler.handler"
  runtime          = var.lambda_runtime
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb
  filename         = var.lambda_career_matcher_zip
  source_code_hash = filebase64sha256(var.lambda_career_matcher_zip)

  environment {
    variables = {
      DATABASE_URL              = var.postgres_url
      CAREER_WATCH_MIN_SCORE    = "0.25"
      CAREER_WATCH_MATCH_BATCH  = "200"
    }
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_event_rule" "career_page_poller" {
  name                = "${local.name_prefix}-career-page-poller"
  description         = "Poll watched company career pages (5 min floor for Plus/Premium watchers)"
  schedule_expression = "rate(5 minutes)"
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "career_page_poller" {
  rule      = aws_cloudwatch_event_rule.career_page_poller.name
  target_id = "career-page-poller"
  arn       = aws_lambda_function.career_page_poller.arn
}

resource "aws_lambda_permission" "career_page_poller" {
  statement_id  = "AllowEventBridgeCareerPagePoller"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.career_page_poller.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.career_page_poller.arn
}

resource "aws_cloudwatch_event_rule" "career_matcher" {
  name                = "${local.name_prefix}-career-matcher"
  description         = "Match career watch jobs to user keywords"
  schedule_expression = "rate(15 minutes)"
  tags                = local.common_tags
}

resource "aws_cloudwatch_event_target" "career_matcher" {
  rule      = aws_cloudwatch_event_rule.career_matcher.name
  target_id = "career-matcher"
  arn       = aws_lambda_function.career_matcher.arn
}

resource "aws_lambda_permission" "career_matcher" {
  statement_id  = "AllowEventBridgeCareerMatcher"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.career_matcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.career_matcher.arn
}
