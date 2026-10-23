"""Bounded browser environment and fault scenarios for page_inspect.

This module is invoked by page_inspect.py, not a second CLI or evidence format.
No user-supplied JavaScript, paths, arbitrary browser destinations or file bodies.
"""
from __future__ import annotations

import math
import re
import time
import urllib.parse

CASES = ("display", "shortcut", "offline", "http-error", "latency", "permission", "upload", "download")
CHANNELS = ("chrome", "msedge")
TIMEZONES = ("UTC", "Asia/Tokyo", "America/New_York", "Europe/London")
LOCALES = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
VIEWPORT = re.compile(r"^([1-9][0-9]{1,3})x([1-9][0-9]{1,3})$")
EVENT_LIMIT = 30


def validate(args, api):
    """Validate before launch, without echoing untrusted input to output."""
    if args.channel and (args.browser != "chromium" or args.channel not in CHANNELS):
        raise api.InspectError("unsupported browser channel", "use chrome or msedge with chromium")
    match = VIEWPORT.fullmatch(args.viewport) if args.viewport else None
    if args.viewport and not match:
        raise api.InspectError("invalid viewport", "use WIDTHxHEIGHT, each dimension 200..4096")
    viewport = None
    if match:
        width, height = (int(part) for part in match.groups())
        if not (200 <= width <= 4096 and 200 <= height <= 4096):
            raise api.InspectError("viewport out of range", "each dimension must be 200..4096")
        viewport = {"width": width, "height": height}
    if args.locale and not LOCALES.fullmatch(args.locale):
        raise api.InspectError("invalid locale", "use e.g. ja-JP or en-US")
    if args.timezone and args.timezone not in TIMEZONES:
        raise api.InspectError("unsupported timezone", "choose one of UTC, Asia/Tokyo, America/New_York, Europe/London")
    if not math.isfinite(args.device_scale_factor) or not 0.5 <= args.device_scale_factor <= 4:
        raise api.InspectError("device scale factor out of range", "use a finite value from 0.5 to 4")
    if args.latency_ms < 0 or args.latency_ms > 2000:
        raise api.InspectError("latency out of range", "use 0..2000 milliseconds")
    if args.case == "permission" and args.permission not in ("notifications", "geolocation"):
        raise api.InspectError("unsupported permission", "use notifications or geolocation")
    api.loopback_target(args.target)
    return viewport


def safe_path(url, api):
    """Only output the path of approved loopback requests, never query or userinfo."""
    try:
        api.loopback_target(url)
        path = urllib.parse.urlsplit(url).path or "/"
        return path if path in ("/api/probe", "/scenario.txt", "/") else "[other_loopback]"
    except (api.InspectError, ValueError):
        return "[blocked]"


def context_configuration(args, api, devices, viewport):
    config = api.context_options(devices, args.browser, args.profile, args.headed)
    config["color_scheme"] = args.color_scheme
    config["reduced_motion"] = args.reduced_motion
    config["locale"] = args.locale
    config["timezone_id"] = args.timezone
    config["device_scale_factor"] = args.device_scale_factor
    if viewport:
        config.pop("no_viewport", None)
        config["viewport"] = viewport
    return config


def run_scenario(args, api):
    """Active, bounded scenario; assemble_observe and _section own the evidence contract."""
    viewport = validate(args, api)
    sync_playwright = api._playwright()
    playwright = sync_playwright().start()
    browser = None
    failure = None
    result = None
    try:
        try:
            browser = getattr(playwright, args.browser).launch(
                headless=not args.headed, **({"channel": args.channel} if args.channel else {})
            )
            options = context_configuration(args, api, playwright.devices, viewport)
            context = browser.new_context(**options, service_workers="block", accept_downloads=True)
            state = {"offline": False, "events": [], "truncated": False}

            def record(kind, path, status=None):
                if len(state["events"]) >= EVENT_LIMIT:
                    state["truncated"] = True
                    return
                row = {"kind": kind, "path": path}
                if status is not None:
                    row["status"] = int(status)
                state["events"].append(row)

            def guard(route):
                path = safe_path(route.request.url, api)
                if path == "[blocked]":
                    route.abort("blockedbyclient")
                elif state["offline"]:
                    route.abort("internetdisconnected")
                elif path == "/api/probe" and args.case == "http-error":
                    route.fulfill(status=503, content_type="text/plain", body="unavailable")
                elif path == "/api/probe" and args.case == "latency":
                    time.sleep(args.latency_ms / 1000)
                    route.fulfill(status=200, content_type="text/plain", body="ok")
                else:
                    response = route.fetch(max_redirects=0)
                    if 300 <= response.status < 400:
                        route.abort("blockedbyclient")
                    else:
                        route.fulfill(response=response)

            context.route("**/*", guard)
            page = context.new_page()
            page.set_default_timeout(8000)
            page.set_default_navigation_timeout(15000)
            page.on("requestfailed", lambda request: record("request_failed", safe_path(request.url, api)))
            page.on("response", lambda response: record(
                "http_error", safe_path(response.url, api), response.status
            ) if response.status >= 400 else None)
            page.goto(args.target, wait_until="load", timeout=15000)
            outcome = {"case": args.case}
            scenario_coverage = "complete"
            if args.case == "display":
                probe = page.locator("#scenario-display")
                outcome["computed"] = {
                    "color_scheme": probe.get_attribute("data-scheme"),
                    "reduced_motion": probe.get_attribute("data-motion"),
                    "locale": probe.get_attribute("data-locale"),
                    "timezone": probe.get_attribute("data-timezone"),
                    "dpr": probe.get_attribute("data-dpr"),
                }
            elif args.case == "shortcut":
                field = page.locator("#scenario-shortcut")
                field.click()
                page.keyboard.press("ControlOrMeta+A")
                page.keyboard.type("Z")
                outcome["select_all_replaced"] = field.input_value() == "Z"
                outcome["shortcut"] = "ControlOrMeta+A"
                page.keyboard.press("ControlOrMeta+Z")
                outcome["undo_restored"] = field.input_value() == "keyboard probe"
                redo_key = "ControlOrMeta+Shift+Z" if api.os_name() == "macOS" else "ControlOrMeta+Y"
                page.keyboard.press(redo_key)
                outcome["redo_applied"] = field.input_value() == "Z"
                outcome["redo_shortcut"] = redo_key
                page.keyboard.press("Tab")
                outcome["tab_focus_advanced"] = page.locator(":focus").first.get_attribute("id") == "scenario-fetch"
            elif args.case in ("offline", "http-error", "latency"):
                if args.case == "offline":
                    context.set_offline(True)
                    state["offline"] = True
                started = time.monotonic()
                page.locator("#scenario-fetch").click()
                probe = page.locator("#scenario-result")
                page.locator("#scenario-result[data-state='ok'], #scenario-result[data-state='error']").wait_for(state="attached")
                outcome["fetch_result"] = probe.get_attribute("data-state")
                if args.case == "latency":
                    outcome["delay_at_least_requested"] = (time.monotonic() - started) * 1000 >= args.latency_ms
                if args.case == "offline":
                    state["offline"] = False
                    context.set_offline(False)
            elif args.case == "permission":
                try:
                    if args.permission_state == "grant":
                        context.grant_permissions([args.permission], origin=urllib.parse.urlsplit(args.target).scheme + "://" + urllib.parse.urlsplit(args.target).netloc)
                        if args.permission == "geolocation":
                            context.set_geolocation({"latitude": 0, "longitude": 0})
                    else:
                        context.clear_permissions()
                    page.locator("#scenario-permission").click()
                    probe_id = "#scenario-permission-result" if args.permission == "notifications" else "#scenario-geolocation-result"
                    page.locator(probe_id + "[data-state]").wait_for(state="attached")
                    outcome["permission"] = args.permission
                    outcome["configured_state"] = args.permission_state
                    outcome["reported_state"] = page.locator(probe_id).get_attribute("data-state")
                    outcome["matches_requested"] = (args.permission_state != "grant" or outcome["reported_state"] == "granted")
                except Exception:
                    scenario_coverage = "unavailable"
                    outcome = {"case": args.case, "reason": "unsupported_or_failed"}
            elif args.case == "upload":
                page.locator("#scenario-upload").set_input_files({
                    "name": "probe.txt", "mimeType": "text/plain", "buffer": b"probe"
                })
                outcome["upload_accepted"] = page.locator("#scenario-upload-result").get_attribute("data-state") == "accepted"
                outcome["bytes"] = 5
                outcome["source"] = "in-memory-test-payload"
            elif args.case == "download":
                with page.expect_download(timeout=8000) as event:
                    page.locator("#scenario-download").click()
                download = event.value
                outcome["name_matches_fixture"] = download.suggested_filename == "scenario.txt"
                outcome["completed"] = download.failure() is None
                outcome["body"] = "not_read"
            effective_viewport = page.viewport_size or {}
            environment = api._environment(browser, args.browser, args.channel, args.headed, args.profile, effective_viewport)
            environment.update({
                "device_profile_emulated": args.profile != "desktop",
                "actual_host_os": api.os_name(),
                "color_scheme": args.color_scheme, "reduced_motion": args.reduced_motion,
                "locale": args.locale, "timezone": args.timezone,
                "device_scale_factor": args.device_scale_factor,
                "environment_source": "playwright:browser.new_context",
                "device_claim": "emulation_only",
            })
            environment["viewport"] = {
                "width": effective_viewport.get("width"), "height": effective_viewport.get("height")
            }
            settings = {
                "color_scheme": args.color_scheme, "reduced_motion": args.reduced_motion,
                "locale": args.locale, "timezone": args.timezone,
                "device_scale_factor": args.device_scale_factor, "viewport": environment["viewport"],
                "browser": args.browser, "channel": args.channel,
            }
            sections = {
                "scenario": api._section("playwright:bounded-scenario", scenario_coverage, outcome),
                "environment_settings": api._section("playwright:browser.new_context", "complete", settings),
                "network": api._section("playwright:response/requestfailed",
                    "truncated" if state["truncated"] else "complete_within_window",
                    {"items": state["events"], "event_limit": EVENT_LIMIT}),
                "dom": api._section(None, "not_requested"),
                "accessibility": api._section(None, "not_requested"),
                "console": api._section(None, "not_requested"),
                "storage": api._section(None, "not_requested"),
                "frames": api._section(None, "not_requested"),
            }
            result = api.assemble_observe(
                {"title": "", "elements": [], "child_frames": 0, "total": 0, "truncated": False},
                environment=environment, url=urllib.parse.urlsplit(args.target).scheme + "://" + urllib.parse.urlsplit(args.target).netloc + "/[fixture]",
                start=0, limit=1, sections=sections,
                limits={
                    "page_js_called": True, "navigation_runs_page_scripts": True,
                    "scenario_active": True, "source": "playwright",
                    "external_network": "blocked", "redirects": "blocked",
                    "secret_input_values": "not_recorded", "file_bodies": "not_recorded",
                    "os_scope": "host_and_emulated_browser; not a real mobile OS",
                },
            )
        except api.InspectError:
            raise
        except Exception as exc:
            raise api.InspectError(
                "scenario failed: " + type(exc).__name__,
                "verify the local fixture and installed browser; no browser exception text was stored",
                stage="inspect",
            ) from None
    except api.InspectError as exc:
        failure = exc
    return api._finish(playwright, browser, failure, result)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        prog="page_inspect_scenarios",
        description="Internal bounded scenario adapter; invoke 'page_inspect.py scenario' instead.",
    )
    parser.parse_args()
