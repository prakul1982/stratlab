"""Round 69 (19 Oct 2026): every StratLab email as the owner gets it — the backend side, on the reviewer's own examples."""
from app import main  # noqa: F401  (loads the app's modules in their order)
from app import alerts, email_previews as E, mail_tokens, rules_watch


def test_an_alert_emails_manage_link_opens_the_page_where_it_was_chosen():
    # R69-002: "Manage emails" opened Settings → Alerts, which has no switch for advance tax, screens or price alerts
    assert alerts.manage_path("/alerts") == "/alerts"
    assert alerts.manage_path("/money/tax-tools?tab=advance") == "/money/tax-tools?tab=advance"
    assert alerts.manage_path("/trade/events") == "/trade/events"
    assert alerts.manage_path("/paper") is None and alerts.manage_path("/admin") is None      # Settings → Alerts holds these
    assert "Manage emails: https://stratlab.studio/alerts" in E.describe("stock_alert", full=True)["text"]
    assert "Manage emails: https://stratlab.studio/money/tax-tools?tab=advance" in E.describe("advance_tax", full=True)["text"]
    assert "Manage emails: https://stratlab.studio/research/screens" in E.describe("screens", full=True)["text"]


def test_the_paper_report_unsubscribes_only_from_itself(monkeypatch):
    # R69-003: its "Turn off alert emails" would have silenced every alert, reminder and admin note
    sent = {}
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, plain, html=None, headers=None: sent.update(plain=plain, headers=headers))
    monkeypatch.setattr(mail_tokens, "make", lambda uid, kind, what: f"{kind}-{what}")
    alerts.send_message("x@example.com", "StratLab daily report: India, Mon 19 Oct", "Body", "/paper", uid="u1", unsub="daily_report")
    assert "Turn off this report: " in sent["plain"] and "unsubscribe-daily_report" in sent["plain"]
    assert "unsubscribe-daily_report" in sent["headers"]["List-Unsubscribe"]
    assert alerts.NEWSLETTER_NAMES["daily_report"] == "the daily paper trading report"
    # every other alert keeps the one switch for alert emails
    alerts.send_message("x@example.com", "3 of your alerts fired", "Body", "/alerts", uid="u1")
    assert "Turn off alert emails: " in sent["plain"] and "unsubscribe-alert_emails" in sent["plain"]


def test_the_previews_list_every_email_sent():
    # R69-004: the paper report, the weekly admin summary and the US weekly brief weren't there
    kinds = E.registry()
    for k in ("daily_report", "weekly_admin", "market_weekly_us"):
        assert k in kinds and "error" not in E.describe(k)
    assert E.describe("daily_report")["subject"].startswith("StratLab daily report: India, ")      # R69-006: the subject names the day


def test_a_circular_listed_twice_under_two_subjects_counts_once_and_a_cut_bracket_goes():
    # R69-005: "5 rate or rule changes" listed CMTR76963.zip and CMPT76951.zip twice each
    assert rules_watch._whole("Listing of Corporate Bonds (") == "Listing of Corporate Bonds"
    assert rules_watch._whole("Changes (Phase 2) in lot size") == "Changes (Phase 2) in lot size"
