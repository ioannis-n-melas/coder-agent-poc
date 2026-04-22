"""Billing hard-cap kill-switch.

Triggered by a Pub/Sub message from a google_billing_budget resource.
When the message indicates that costAmount >= budgetAmount (spend has
reached 100% of the configured hard cap), this function iterates every
project attached to the triggering billing account and calls
UpdateProjectBillingInfo to disable billing on each one.

Environment variables (set by Terraform):
  PROJECT_ID         - GCP project ID of the function's host project.
  BILLING_ACCOUNT_ID - Billing account ID (e.g. XXXXXX-XXXXXX-XXXXXX).
  DRY_RUN            - Set to "true" to log intent without disabling billing.

Recovery:
  gcloud billing projects link PROJECT_ID --billing-account=ACCOUNT_ID
  or via the Cloud Console: Billing -> My projects -> Re-enable.

See ADR-0015 for design rationale, alternatives, and blast-radius warning.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import functions_framework
from google.cloud import billing_v1

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_BILLING_ACCOUNT_ID = os.environ["BILLING_ACCOUNT_ID"]
_DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


@functions_framework.cloud_event
def disable_billing_on_budget_alert(cloud_event: Any) -> None:
    """Entry point called by Cloud Functions gen2 on each Pub/Sub message.

    The Budget notification schema (v1.0) is documented at:
    https://cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications
    """
    # Decode Pub/Sub message data.
    pubsub_data_b64: str = cloud_event.data["message"]["data"]
    pubsub_data: bytes = base64.b64decode(pubsub_data_b64)
    notification: dict = json.loads(pubsub_data.decode("utf-8"))

    cost_amount: float = float(notification.get("costAmount", 0))
    budget_amount: float = float(notification.get("budgetAmount", 1))
    budget_name: str = notification.get("budgetDisplayName", "<unknown>")
    currency_code: str = notification.get("currencyCode", "?")

    logger.info(
        "Budget notification received: budget=%r cost=%s%s budget=%s%s",
        budget_name,
        currency_code,
        cost_amount,
        currency_code,
        budget_amount,
    )

    if cost_amount < budget_amount:
        logger.info(
            "Cost (%s%s) is below budget (%s%s). No action taken.",
            currency_code,
            cost_amount,
            currency_code,
            budget_amount,
        )
        return

    logger.warning(
        "KILL SWITCH TRIGGERED: cost %s%s >= budget %s%s for %r. "
        "Disabling billing on all projects attached to billing account %s.",
        currency_code,
        cost_amount,
        currency_code,
        budget_amount,
        budget_name,
        _BILLING_ACCOUNT_ID,
    )

    if _DRY_RUN:
        logger.warning(
            "DRY_RUN=true — would disable billing but taking no action. "
            "Set DRY_RUN=false in the function env vars to arm the kill switch."
        )
        return

    _disable_billing_for_all_projects()


def _disable_billing_for_all_projects() -> None:
    """Iterate projects on the billing account and disable billing on each."""
    client = billing_v1.CloudBillingClient()
    billing_account_name = f"billingAccounts/{_BILLING_ACCOUNT_ID}"

    project_billing_infos = client.list_project_billing_info(
        name=billing_account_name
    )

    disabled: list[str] = []
    errors: list[str] = []

    for pbi in project_billing_infos:
        project_id = pbi.project_id
        if not pbi.billing_enabled:
            logger.info("Project %s: billing already disabled, skipping.", project_id)
            continue

        logger.warning("Disabling billing on project: %s", project_id)
        try:
            client.update_project_billing_info(
                name=f"projects/{project_id}",
                project_billing_info=billing_v1.ProjectBillingInfo(
                    billing_account_name="",  # empty string disables billing
                ),
            )
            disabled.append(project_id)
            logger.warning("Billing disabled on project: %s", project_id)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to disable billing on project %s: %s", project_id, exc
            )
            errors.append(project_id)

    logger.warning(
        "Kill switch complete. Disabled: %s. Errors: %s.",
        disabled,
        errors,
    )

    if errors:
        # Raise so Cloud Functions marks the invocation as failed and
        # (if retry policy is enabled) retries. With RETRY_POLICY_DO_NOT_RETRY
        # this is just for observability.
        raise RuntimeError(
            f"Failed to disable billing on projects: {errors}. "
            "Check function logs and disable manually via the console."
        )
