import json
import os
import random
import re
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
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def utc_now():
    return datetime.now(ZoneInfo("UTC"))


def api(path, method="GET", payload=None, prefer=None):
    headers = dict(HEADERS)
    if prefer:
        headers["Prefer"] = prefer
    response = requests.request(
        method,
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(
            f"Supabase {response.status_code}: {response.text[:500]}"
        )
    return response.json() if response.text else None


def update_scan_status(payload):
    api(
        "scan_status?id=eq.1",
        "PATCH",
        {**payload, "updated_at": utc_now().isoformat()},
    )


def upsert_alert(payload):
    api(
        "alert_state?on_conflict=source_id",
        "POST",
        payload,
        "resolution=merge-duplicates,return=minimal",
    )


def business_time():
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    return now.weekday() < 5 and 7 <= now.hour < 17


def source_is_due(source):
    value = source.get("next_check_at")
    if not value:
        return True
    return datetime.fromisoformat(value.replace("Z", "+00:00")) <= utc_now()


def send_push(source):
    public_key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    if not public_key or not private_key:
        return
    subscriptions = api("push_subscriptions?active=eq.true&select=*") or []
    payload = json.dumps({
        "title": "PS5 Pro Preisalarm",
        "body": f"{source['last_price']:.2f} € bei {source['providers']['name']} · verfügbar",
        "url": os.getenv("APP_URL", "https://tonywmn.github.io/PTD-PriceWatch/"),
        "tag": f"price-{source['id']}",
    })
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
                vapid_claims={"sub": "mailto:tony.weimann@icloud.com"},
            )
        except WebPushException as error:
            print(f"PUSH_ERROR {error}")


def blocked_reason(title, body):
    sample = f"{title} {body[:5000]}".lower()
    signals = {
        "captcha": "CAPTCHA",
        "access denied": "Access denied",
        "zugriff verweigert": "Zugriff verweigert",
        "unusual traffic": "Unusual traffic",
        "robot or human": "Bot-Prüfung",
        "enable javascript": "JavaScript-Hinweis",
        "datenschutzeinstellungen": "Consent-Seite",
    }
    for token, label in signals.items():
        if token in sample:
            return label
    return None


def scan_source(browser, source, products_by_id):
    checked_at = utc_now()
    next_at = checked_at + timedelta(minutes=random.randint(5, 10))
    provider = source["providers"]["name"]
    patch = {
        "last_checked_at": checked_at.isoformat(),
        "next_check_at": next_at.isoformat(),
    }
    context = browser.new_context(
        locale="de-DE",
        timezone_id="Europe/Berlin",
        viewport={"width": 1440, "height": 1100},
        extra_http_headers={"Accept-Language": "de-DE,de;q=0.9"},
    )
    page = context.new_page()
    try:
        page.goto(source["product_url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(random.randint(3500, 6000))
        body = page.locator("body").inner_text(timeout=20000)
        html = page.content()
        block = blocked_reason(page.title(), body)
        if block:
            result = None
            patch.update({
                "availability": "unknown",
                "status": f"Zugriff blockiert: {block}",
                "error_message": f"Final URL: {page.url}",
            })
        else:
            result = parse_text(provider, body, html)
            patch.update({
                "last_price": result.price,
                "availability": result.availability,
                "status": result.status,
                "error_message": None,
            })
            if result.validated:
                patch["last_success_at"] = checked_at.isoformat()
        api(f"product_sources?id=eq.{source['id']}", "PATCH", patch)
        if result:
            api("price_history", "POST", {
                "source_id": source["id"],
                "price": result.price,
                "availability": result.availability,
                "validated": result.validated,
                "checked_at": checked_at.isoformat(),
            })
            product = products_by_id.get(source["product_id"])
            alert = (
                product
                and result.validated
                and result.price is not None
                and result.price < float(product["alert_price"])
            )
            if alert:
                rows = api(f"alert_state?source_id=eq.{source['id']}&select=*") or []
                previous = rows[0] if rows else None
                if (
                    not previous
                    or previous.get("last_alert_price") != result.price
                    or not previous.get("alert_active")
                ):
                    send_push({**source, **patch, "last_price": result.price})
                upsert_alert({
                    "source_id": source["id"],
                    "last_alert_price": result.price,
                    "last_alert_at": checked_at.isoformat(),
                    "alert_active": True,
                })
            else:
                upsert_alert({"source_id": source["id"], "alert_active": False})
            print(
                f"RESULT {provider}: status={result.status}; price={result.price}; "
                f"availability={result.availability}; validated={result.validated}"
            )
        else:
            print(f"RESULT {provider}: blocked={block}")
    except Exception as error:
        patch.update({
            "availability": "unknown",
            "status": "Technischer Abruffehler",
            "error_message": str(error)[:500],
        })
        api(f"product_sources?id=eq.{source['id']}", "PATCH", patch)
        print(f"RESULT {provider}: exception={error}")
    finally:
        context.close()


def run_scan(selected, products_by_id):
    update_scan_status({
        "state": "running",
        "total_sources": len(selected),
        "completed_sources": 0,
        "current_provider": None,
        "started_at": utc_now().isoformat(),
        "finished_at": None,
        "error_message": None,
    })
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for index, source in enumerate(selected, start=1):
                update_scan_status({"current_provider": source["providers"]["name"]})
                scan_source(browser, source, products_by_id)
                update_scan_status({"completed_sources": index})
                time.sleep(random.uniform(1.0, 2.0))
            browser.close()
        update_scan_status({
            "state": "success",
            "current_provider": None,
            "finished_at": utc_now().isoformat(),
        })
    except Exception as error:
        update_scan_status({
            "state": "failed",
            "current_provider": None,
            "finished_at": utc_now().isoformat(),
            "error_message": str(error)[:500],
        })
        raise


def main():
    force = os.getenv("FORCE_SCAN", "false").lower() == "true"
    if not business_time() and not force:
        print("Outside configured business window")
        return
    products = api("products?active=eq.true&select=*") or []
    sources = api("product_sources?active=eq.true&select=*,providers(*)") or []
    selected = sources if force else [source for source in sources if source_is_due(source)]
    if not selected:
        print("No source due")
        return
    run_scan(selected, {item["id"]: item for item in products})


if __name__ == "__main__":
    main()
