import json
import os
import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright
from pywebpush import WebPushException, webpush

from parsers import parse_text

SUPABASE_URL = os.environ["SUPABASE_URL"].strip().rstrip("/")
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"].strip()

HEADERS = {
    "apikey": SUPABASE_SECRET_KEY,
    "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def api(path, method="GET", payload=None):
    response = requests.request(
        method,
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json() if response.text else None


def upsert_alert(payload):
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/alert_state?on_conflict=source_id",
        headers={
            **HEADERS,
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()


def business_time():
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    return now.weekday() < 5 and 7 <= now.hour < 17


def source_is_due(source):
    next_check_at = source.get("next_check_at")

    if not next_check_at:
        return True

    next_check = datetime.fromisoformat(
        next_check_at.replace("Z", "+00:00")
    )

    return next_check <= datetime.now(ZoneInfo("UTC"))


def deactivate_push_subscription(endpoint):
    encoded_endpoint = requests.utils.quote(endpoint, safe="")

    api(
        f"push_subscriptions?endpoint=eq.{encoded_endpoint}",
        "PATCH",
        {"active": False},
    )


def send_push_notification(product, source):
    subscriptions = (
        api("push_subscriptions?active=eq.true&select=*") or []
    )

    public_key = os.getenv("VAPID_PUBLIC_KEY")
    private_key = os.getenv("VAPID_PRIVATE_KEY")

    if not public_key or not private_key:
        print("VAPID keys missing. Push notification skipped.")
        return

    app_url = os.getenv(
        "APP_URL",
        "https://tonywmn.github.io/PTD-PriceWatch/",
    )

    payload = json.dumps(
        {
            "title": "PS5 Pro Preisalarm",
            "body": (
                f"{source['last_price']:.2f} € bei "
                f"{source['providers']['name']} · verfügbar"
            ),
            "url": app_url,
            "tag": f"price-{source['id']}",
        }
    )

    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription["endpoint"],
                    "keys": {
                        "p256dh": subscription["p256dh"],
                        "auth": subscription["auth"],
                    },
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={
                    "sub": "mailto:tony.weimann@icloud.com"
                },
            )
        except WebPushException as error:
            status_code = getattr(error.response, "status_code", 0)

            if status_code in (404, 410):
                deactivate_push_subscription(
                    subscription["endpoint"]
                )
            else:
                print(
                    "Push delivery failed:",
                    str(error),
                )


def update_source(source_id, payload):
    api(
        f"product_sources?id=eq.{source_id}",
        "PATCH",
        payload,
    )


def record_history(source_id, result, checked_at):
    api(
        "price_history",
        "POST",
        {
            "source_id": source_id,
            "price": result.price,
            "availability": result.availability,
            "validated": result.validated,
            "checked_at": checked_at.isoformat(),
        },
    )


def process_alert(product, source, result, patch, checked_at):
    if (
        product
        and result.validated
        and result.price is not None
        and result.price < float(product["alert_price"])
    ):
        existing_rows = api(
            f"alert_state?source_id=eq.{source['id']}&select=*"
        ) or []
        existing = existing_rows[0] if existing_rows else None

        should_alert = (
            not existing
            or existing.get("last_alert_price") != result.price
            or not existing.get("alert_active")
        )

        if should_alert:
            send_push_notification(
                product,
                {
                    **source,
                    **patch,
                    "last_price": result.price,
                },
            )

        upsert_alert(
            {
                "source_id": source["id"],
                "last_alert_price": result.price,
                "last_alert_at": checked_at.isoformat(),
                "alert_active": True,
            }
        )
    else:
        upsert_alert(
            {
                "source_id": source["id"],
                "alert_active": False,
            }
        )


def scan_source(browser, source, products_by_id):
    checked_at = datetime.now(ZoneInfo("UTC"))
    next_check_at = checked_at + timedelta(
        minutes=random.randint(5, 10)
    )

    patch = {
        "last_checked_at": checked_at.isoformat(),
        "next_check_at": next_check_at.isoformat(),
    }

    page = browser.new_page(
        locale="de-DE",
        viewport={"width": 1440, "height": 1000},
    )

    try:
        page.goto(
            source["product_url"],
            wait_until="domcontentloaded",
            timeout=45000,
        )
        page.wait_for_timeout(random.randint(1800, 3500))

        body_text = page.locator("body").inner_text(timeout=15000)
        page_html = page.content()

        result = parse_text(
            source["providers"]["name"],
            body_text,
            page_html,
        )

        patch.update(
            {
                "last_price": result.price,
                "availability": result.availability,
                "status": result.status,
                "error_message": None,
            }
        )

        if result.validated:
            patch["last_success_at"] = checked_at.isoformat()

        update_source(source["id"], patch)
        record_history(source["id"], result, checked_at)

        product = products_by_id.get(source["product_id"])
        process_alert(
            product,
            source,
            result,
            patch,
            checked_at,
        )

        print(
            f"{source['providers']['name']}: "
            f"{result.status}, price={result.price}, "
            f"availability={result.availability}"
        )

    except Exception as error:
        patch.update(
            {
                "status": "Abruffehler",
                "availability": "unknown",
                "error_message": str(error)[:500],
            }
        )
        update_source(source["id"], patch)
        print(
            f"{source['providers']['name']}: Abruffehler: {error}"
        )

    finally:
        page.close()


def main():
    force_scan = (
        os.getenv("FORCE_SCAN", "false").lower() == "true"
    )

    if not business_time() and not force_scan:
        print("Outside configured business window")
        return

    products = api(
        "products?active=eq.true&select=*"
    ) or []

    sources = api(
        "product_sources?active=eq.true&select=*,providers(*)"
    ) or []

    products_by_id = {
        product["id"]: product for product in products
    }

    if force_scan:
        sources_to_scan = sources
    else:
        sources_to_scan = [
            source for source in sources if source_is_due(source)
        ]

    if not sources_to_scan:
        print("No source due")
        return

    print(
        f"Scanning {len(sources_to_scan)} source(s); "
        f"force_scan={force_scan}"
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        for source in sources_to_scan:
            scan_source(browser, source, products_by_id)
            time.sleep(random.uniform(1.1, 2.4))

        browser.close()


if __name__ == "__main__":
    main()
