#!/usr/bin/env python3
"""
Martin Bone Bridge Pins restock watcher.
Checks every color, prints the status of each, and sends a phone alert
(ntfy) when a color in WATCH goes from out of stock to in stock.

  python martin_watch.py            normal check
  python martin_watch.py --test     send a test push only
  python martin_watch.py --simulate pretend the first WATCH color restocked
"""
import argparse
import json
import pathlib
import re

import requests
from playwright.sync_api import sync_playwright

URL = "https://www.martinguitar.com/gear-accessories/parts/bridge-end-pins/bone-bridge-pins.html"
COLORS = ["Paua Inlay", "Black Inlay", "Faux Tortoise Inlay"]
WATCH = ["Paua Inlay"]                       # color(s) you want alerts for
NTFY_TOPIC = "delano-restock-CHANGE-ME-8472"  # same channel your phone is on
STATE = pathlib.Path(__file__).with_name("martin_state.json")
OUT = re.compile(r"out\s*of\s*stock|sold\s*out|unavailable|back\s*order|not\s*available", re.I)


def any_visible(locator):
    return any(el.is_visible() for el in locator.all())


def check():
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"))
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(f"select option:has-text('{COLORS[0]}')", state="attached", timeout=45000)

        for color in COLORS:
            select = page.locator(f"select:has(option:has-text('{color}'))").first
            opt = select.locator("option", has_text=color).first
            opt_text = opt.inner_text().strip()
            opt_disabled = opt.is_disabled() or "unselectable" in (opt.get_attribute("class") or "")

            select.select_option(value=opt.get_attribute("value"))
            page.wait_for_timeout(3500)  # let the page update stock info

            root = page.locator(".product-detail").first
            if root.count() == 0:
                root = page
            avail = " | ".join(t.strip() for t in root.locator(
                ".availability-msg, .availability").all_inner_texts() if t.strip())
            atc = root.locator("button.add-to-cart, button.add-to-cart-global")
            atc_ok = any(el.is_visible() and el.is_enabled() for el in atc.all())
            notify = any_visible(root.get_by_text("Get notified when this item is back in stock"))

            in_stock = (not opt_disabled and atc_ok and not notify
                        and not OUT.search(avail) and not OUT.search(opt_text))
            results[color] = in_stock
            print(f"{color}: option='{opt_text}' disabled={opt_disabled} "
                  f"availability='{avail}' add_to_cart={atc_ok} notify_form={notify} "
                  f"-> in_stock={in_stock}")

        browser.close()
    return results


def notify(msg):
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=msg.encode(),
                  headers={"Title": "Martin restock", "Click": URL, "Priority": "high"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--simulate", action="store_true")
    args = ap.parse_args()

    if args.test:
        notify("Test alert from martin_watch.py. Notifications are working.")
        print("Test push sent.")
        return

    try:
        now = check()
    except Exception as e:
        print("Check failed, skipping this run:", str(e).splitlines()[0])
        return

    prev = json.loads(STATE.read_text()) if STATE.exists() else {}
    if args.simulate:
        now[WATCH[0]] = True
        prev[WATCH[0]] = False

    alerts = [f"{c} bone bridge pins are back in stock" for c in WATCH
              if now.get(c) and not prev.get(c)]
    if alerts:
        notify("\n".join(alerts))
    print("alerts:", alerts or "none")
    if not args.simulate:
        STATE.write_text(json.dumps(now))


if __name__ == "__main__":
    main()
