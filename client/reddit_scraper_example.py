"""
copy into your reddit scraper project.
reports domain stats to telegramvps hub — NOT server cpu/ram.
"""

import time
import requests

API = "http://127.0.0.1:8787/report"
PROJECT = "reddit-scraper"


def report(status="running", step="", current=0, total=0, message="", **extra):
    payload = {
        "project_id": PROJECT,
        "status": status,
        "step": step,
        "current_item": current,
        "total_items": total,
        "message": message,
    }
    payload.update(extra)
    if total > 0:
        payload["progress"] = min(100.0, round(current / total * 100, 1))
    try:
        requests.post(API, json=payload, timeout=2)
    except Exception:
        pass


def scrape_subreddit(subreddit, max_pages=10):
    report(status="running", step="init", started_at=time.time(), subreddit=subreddit)
    posts_new = posts_dup = 0
    rate_limits = 0

    try:
        for page in range(1, max_pages + 1):
            # your fetch logic here
            time.sleep(0.5)  # placeholder
            posts_new += 10
            report(
                step="crawl",
                current=page,
                total=max_pages,
                message=f"r/{subreddit} · page {page}",
                posts_new=posts_new,
                posts_dup=posts_dup,
                rate_limit_waits=rate_limits,
                last_http_status=200,
            )
        report(
            status="completed",
            verdict="OK",
            summary=f"sub=r/{subreddit}\nnew={posts_new}\ndup={posts_dup}\nrate_limits={rate_limits}",
            completed_at=time.time(),
        )
    except Exception as e:
        report(status="failed", error=str(e), failed_at=time.time())
        raise


if __name__ == "__main__":
    scrape_subreddit("FreeGameFindings", max_pages=3)