#!/usr/bin/env python3
"""Regenerate app.STREAMING_PRICES and app.MUSIC_PRICES from the providers' own pages.

Dev-only helper -- never imported by app.py. The landing page reads a baked-in
constant so it has no runtime network dependency, and a provider blocking or
redesigning a page can never break the site.

Usage:
    python scripts/refresh_streaming_prices.py

Fetches one page per service (a single request each, no retries) and prints a
paste-ready block. It never edits app.py: read the output, spot-check it against
the provider's page, then paste it in and commit.

Each plan has its own regex, anchored on the plan's name or checkout code rather
than on "any dollar amount", because every one of these pages also advertises
bundles, annual prices, add-ons and student discounts. When a provider reworks
its page the regex stops matching and the plan is reported as "!!" -- that is
the intended failure. Look the price up by hand and fix the pattern; do not
loosen it until it matches something.
"""

import html
import re
import sys
import urllib.request
from datetime import date

# A bare Python User-Agent gets 403s from several of these hosts.
USER_AGENT = "Mozilla/5.0 (compatible; expense-tracker-price-check/1.0; one-off dev script)"

P = r"(\d{1,2}\.\d{2})"

# Anything outside this range is a mis-parse (an annual price, a bundle, a
# trial), not a monthly plan.
MIN_PRICE, MAX_PRICE = 1.00, 50.00

# (service, link shown on the landing page, page scraped, [(plan, regex), ...])
#
# Patterns run against the page with tags removed and whitespace collapsed.
# <script> bodies are kept on purpose: Hulu and Peacock only carry their prices
# in the JSON the page hydrates from.
VIDEO = [
    (
        "Netflix",
        "https://www.netflix.com/",
        "https://help.netflix.com/en/node/24926",
        [
            ("Standard with ads", r"Standard with ads\s*:\s*\$" + P + r"\s*/\s*month"),
            ("Standard", r"Standard\s*:\s*\$" + P + r"\s*/\s*month"),
            ("Premium", r"Premium\s*:\s*\$" + P + r"\s*/\s*month"),
        ],
    ),
    (
        "Disney+",
        "https://www.disneyplus.com/",
        "https://www.disneyplus.com/",
        [
            ("With ads", r"Disney\+ \(With Ads\) for the price of \$" + P + r"\s*/\s*month"),
            ("Premium (no ads)", r"Disney\+ \(No Ads\*?\) for the price of \$" + P + r"\s*/\s*month"),
        ],
    ),
    (
        "Hulu",
        "https://www.hulu.com/",
        "https://www.hulu.com/welcome",
        [
            ("With ads", r"\$" + P + r"[^{}]{0,120}pref=hulu_basic"),
            ("No ads", r"\$" + P + r"[^{}]{0,120}pref=hulu_premium"),
        ],
    ),
    (
        "HBO Max",
        "https://www.hbomax.com/",
        "https://help.hbomax.com/us/Answer/Detail/000002547",
        [
            ("Basic with ads", r"Basic with Ads[\s:\u2013\u2014-]*\$" + P + r"\s*/\s*month"),
            ("Standard", r"Standard[\s:\u2013\u2014-]*\$" + P + r"\s*/\s*month"),
            ("Premium", r"Premium[\s:\u2013\u2014-]*\$" + P + r"\s*/\s*month"),
        ],
    ),
    (
        "Prime Video",
        "https://www.primevideo.com/",
        "https://www.amazon.com/gp/help/customer/display.html?nodeId=G34EUPKVMYFW8N2U",
        [
            ("Prime Video only", r"Prime Video membership is \$" + P + r" per month"),
            ("With Amazon Prime", r"Amazon Prime membership pricing:\s*\$" + P + r" per month"),
        ],
    ),
    (
        "Apple TV",
        "https://tv.apple.com/",
        "https://www.apple.com/apple-tv/",
        [
            ("Monthly", r"monthly subscription is just \$" + P + r"\s*per month"),
        ],
    ),
    (
        "Peacock",
        "https://www.peacocktv.com/",
        "https://www.peacocktv.com/",
        [
            ("Select", r'"\$' + P + r'/month","ctaHref":"/checkout\?product(?:\[\]|%5B%5D)=SELECT_MONTH_SUBS"'),
            ("Premium", r'"\$' + P + r'/month","ctaHref":"/checkout\?product(?:\[\]|%5B%5D)=D2C_SUBSCRIPTION_MONTH"'),
            ("Premium Plus", r'"\$' + P + r'/month","ctaHref":"/checkout\?product(?:\[\]|%5B%5D)=PREMIUM_PLUS_MONTH_SUBS"'),
        ],
    ),
    (
        "Paramount+",
        "https://www.paramountplus.com/",
        "https://www.paramountplus.com/",
        [
            # The plan table reads "Paramount+ Premium Paramount+ Essential Price $X /mo $Y /mo".
            ("Essential", r"Paramount\+ Premium Paramount\+ Essential Price \$[\d.]+\s*/mo \$" + P + r"\s*/mo"),
            ("Premium", r"Paramount\+ Premium Paramount\+ Essential Price \$" + P + r"\s*/mo"),
        ],
    ),
]
# Spotify's plan cards live in page JSON keyed by planId; the tempered dot stops a
# missing price from being filled in from the next plan's card.
SPOTIFY = r'"planId":"%s"(?:(?!"planId").){0,2500}?\$' + P + r" / month"
YT_MUSIC = r'"text":"%s"\}\]\},"subtitle":\{"runs":\[.{0,160}?\$' + P + r"[\u2060\s]*/[\u2060\s]*month"

MUSIC = [
    (
        "Spotify",
        "https://www.spotify.com/us/premium/",
        "https://www.spotify.com/us/premium/",
        [
            ("Premium Individual", SPOTIFY % "PREMIUM_INDIVIDUAL"),
            ("Premium Duo", SPOTIFY % "PREMIUM_DUO"),
            ("Premium Family", SPOTIFY % "PREMIUM_FAMILY"),
        ],
    ),
    (
        "Apple Music",
        "https://www.apple.com/apple-music/",
        "https://www.apple.com/apple-music/",
        [
            ("Individual", r"Individual \$" + P + r"\s*/\s*month"),
            ("Family", r"Family \$" + P + r"\s*/\s*month"),
        ],
    ),
    (
        "Tidal",
        "https://tidal.com/",
        # tidal.com itself sits behind a bot challenge; the help centre does not.
        "https://support.tidal.com/hc/en-us/articles/115003662825-Subscription-Types",
        [
            ("Individual", r"Tidal Individual: \$" + P + r" USD/month"),
            ("Family", r"Tidal Family: \$" + P + r" USD/month"),
        ],
    ),
    (
        "Amazon Music Unlimited",
        "https://www.amazon.com/music/unlimited",
        "https://www.amazon.com/music/unlimited",
        [
            ("Individual", r"Auto-renews at \$" + P + r"/mo\. after \(\$[\d.]+/mo\. for Prime members\)"),
            ("Individual, Prime members", r"\(\$" + P + r"/mo\. for Prime members\)"),
        ],
    ),
    (
        "YouTube Music Premium",
        "https://music.youtube.com/",
        "https://www.youtube.com/musicpremium",
        [
            ("Individual", YT_MUSIC % "Individual"),
            ("Family", YT_MUSIC % "Family"),
        ],
    ),
]

# (constant name in app.py, services)
GROUPS = [("STREAMING_PRICES", VIDEO), ("MUSIC_PRICES", MUSIC)]


def fetch_text(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text)


def scrape(source, patterns):
    """Return ([(plan, price), ...], [problem, ...]) for one service."""
    try:
        text = fetch_text(source)
    except Exception as exc:  # network error, 403, captcha redirect, ...
        return [], [f"fetch failed ({exc})"]

    plans, problems = [], []
    for plan, pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            problems.append(f'plan "{plan}" not found')
            continue
        price = float(match.group(1))
        if not MIN_PRICE <= price <= MAX_PRICE:
            problems.append(f'plan "{plan}" parsed as ${price:.2f}, outside the sane range')
            continue
        plans.append((plan, price))
    return plans, problems


def main():
    failed = False
    out = [f'STREAMING_PRICES_AS_OF = "{date.today().isoformat()}"']
    for constant, services in GROUPS:
        out.append(f"{constant} = [")
        for service, link, source, patterns in services:
            plans, problems = scrape(source, patterns)
            for problem in problems:
                failed = True
                print(f"!! {service}: {problem} -- check {source} by hand", file=sys.stderr)

            out.append(f'    {{"service": "{service}", "url": "{link}", "plans": [')
            for plan, price in plans:
                out.append(f'        {{"name": "{plan}", "price": {price:.2f}}},')
            if problems:
                out.append(f"        # INCOMPLETE -- see the !! lines above; check {source}")
            out.append("    ]},")
        out.append("]")

    print("\n".join(out))

    if failed:
        print(
            "\nSome plans could not be read. Do not paste the block as-is: fill the gaps\n"
            "by hand from the pages named above, or keep the old value for that service.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
