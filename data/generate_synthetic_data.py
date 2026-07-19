#!/usr/bin/env python3
"""
Generate synthetic customer research data for DiscoveryOS.
Pure Python, no API calls, no external dependencies beyond stdlib.
"""

import json
import os
from datetime import datetime, timedelta
import random


def generate_synthetic_data():
    """Generate and save sources.json."""
    
    recurring_problems = {
        "export_timeout": {
            "enterprise_formal": (
                "Bulk export operations time out on datasets exceeding 40k rows. "
                "Our analysts need to export quarterly data for compliance reporting, "
                "but the system times out consistently. We end up using manual workarounds."
            ),
            "smb_casual": (
                "The download thing just spins forever and never finishes, so annoying. "
                "I try to get my data out and it's broken every time."
            ),
            "enterprise_technical": (
                "When I try to export more than 50k rows, it hangs indefinitely. "
                "No timeout notification, no error message—it just never completes."
            ),
            "survey_export": "Export feature needs better handling of large datasets.",
        },
        "integration_silent_failure": {
            "enterprise_formal": (
                "Integration with Salesforce syncs intermittently and fails silently. "
                "Our sales team relies on real-time data, but they don't realize sync is broken "
                "until hours later when discrepancies appear."
            ),
            "free_casual": (
                "Connected my Slack but it just doesn't work. I got a success message but nothing happens."
            ),
            "interview_integration": (
                "We tried connecting HubSpot through Zapier. It seemed to work but then "
                "stopped syncing data without any warning. No error, no notification."
            ),
            "support_integration": "Ticket: Zapier integration stopped working silently.",
        },
        "onboarding_friction": {
            "enterprise_formal": (
                "New team member onboarding requires extensive IT involvement. "
                "The setup wizard doesn't accommodate strict permission rules. "
                "IT spends 2-3 hours per employee for what should be 15 minutes."
            ),
            "free_casual": (
                "I signed up and had no idea what to do. Clicked around for 20 minutes looking for features."
            ),
            "survey_onboarding": "Setup process should be simpler for new users.",
            "interview_onboarding": "The initial setup is confusing without guidance.",
        },
        "dashboard_performance": {
            "enterprise_formal": (
                "Dashboard responsiveness degrades significantly with large historical datasets. "
                "Loading a year of daily aggregated data can take 30-45 seconds."
            ),
            "smb_casual": (
                "The dashboard is super slow. Takes like 30 seconds to load my reports."
            ),
            "interview_perf": (
                "When I open my year-to-date report it takes forever to render. "
                "It's just expected that we wait 30-45 seconds."
            ),
            "survey_perf": "Dashboard performance could be improved.",
        },
        "support_response_time": {
            "enterprise_formal": (
                "Support response times have degraded to 24-48 hours for non-critical issues. "
                "Our Enterprise SLA promises 4 hours; we're consistently missing that target."
            ),
            "survey_support": "Support took too long to respond to our issues.",
            "interview_support": (
                "Response times seem to have gotten worse over the last quarter."
            ),
            "ticket_support": "Ticket: Support response time exceeds SLA.",
        },
        "billing_confusion": {
            "enterprise_formal": (
                "Our finance team can't reconcile charges with seat count and feature usage. "
                "Invoice doesn't match our understanding of the pricing model."
            ),
            "free_casual": (
                "I got charged and I don't even know why. The pricing page is confusing."
            ),
            "survey_billing": "Billing model is unclear and hard to predict.",
            "interview_billing": "It's hard to understand what we're paying for.",
        },
        "no_templates": {
            "smb_casual": (
                "I have to build the same reports every month from scratch. "
                "Would be amazing if there were saved templates."
            ),
            "interview_templates": (
                "Our finance team runs the same weekly report every Monday. "
                "A template feature would save us 3-4 hours a week."
            ),
            "survey_templates": "Save/reuse report templates would be helpful.",
        },
        "data_security": {
            "enterprise_formal": (
                "Our data privacy officer requires more granular audit logs. "
                "Current logs don't meet HIPAA compliance standards."
            ),
            "survey_security": "More security and compliance features would be helpful.",
            "interview_security": "We need better data privacy controls.",
        },
        "data_accuracy": {
            "enterprise_formal": (
                "Aggregated revenue figures in the dashboard don't reconcile with our "
                "source-of-truth data warehouse. We've measured a 2-4% discrepancy on "
                "rolled-up metrics, which undermines executive trust in the numbers."
            ),
            "smb_casual": (
                "The numbers just don't add up. My total on the dashboard is different "
                "from what I get when I add it up myself, so I don't really trust it."
            ),
            "interview_accuracy": (
                "We keep finding cases where the summary total doesn't match the detail "
                "rows underneath it. Nobody can explain the gap, so we double-check in Excel."
            ),
            "ticket_accuracy": "Ticket: Dashboard totals don't match exported detail data.",
        },
        "mobile_access": {
            "enterprise_formal": (
                "Our field leadership needs to review KPIs during travel, but the product "
                "is effectively desktop-only. The responsive web view is unusable on a phone."
            ),
            "free_casual": (
                "There's no app? I just want to glance at my numbers on my phone but the "
                "website is a mess on mobile, everything's tiny and cut off."
            ),
            "survey_mobile": "A native mobile app would be a huge improvement.",
            "interview_mobile": "Checking reports on the go is basically impossible right now.",
        },
        "permissions_rbac": {
            "enterprise_formal": (
                "Role-based access control is too coarse. We can't restrict specific "
                "dashboards to specific departments, so finance data is visible to everyone "
                "with a login, which fails our internal access-control policy."
            ),
            "smb_casual": (
                "I can't stop my interns from seeing the money stuff. It's all or nothing "
                "for who sees what, which is not great."
            ),
            "survey_permissions": "Need finer-grained permissions per dashboard or report.",
            "interview_permissions": "Everyone on the team sees everything; we need proper roles.",
        },
        "api_rate_limits": {
            "enterprise_formal": (
                "The public API's rate limits are undocumented and far too low for our "
                "nightly ETL job, which pulls metrics for 200 accounts. We hit 429s "
                "constantly and there's no way to request a higher tier."
            ),
            "interview_api": (
                "Our engineers wired up the API but it throttles us so aggressively the "
                "sync never finishes in the batch window. We had to add ugly retry loops."
            ),
            "survey_api": "API rate limits are too restrictive for programmatic use.",
            "ticket_api": "Ticket: Frequent 429 rate-limit errors on the reporting API.",
        },
        "alerting_gaps": {
            "enterprise_formal": (
                "There's no proactive alerting. When a key metric crosses a threshold or a "
                "data pipeline stalls, we only find out when someone happens to open the "
                "dashboard. We need push notifications for anomalies."
            ),
            "free_casual": (
                "I wish it would just tell me when something's wrong instead of me having "
                "to remember to log in and check every day."
            ),
            "survey_alerting": "Threshold-based alerts and notifications would help a lot.",
            "interview_alerting": "We're always reacting late because nothing notifies us.",
        },
        "collaboration_sharing": {
            "enterprise_formal": (
                "Sharing a report externally with a client requires giving them a full "
                "seat, which is a licensing and security problem. There's no read-only "
                "shareable link with an expiry."
            ),
            "smb_casual": (
                "I just want to send my boss a link to the report but I can't, I have to "
                "screenshot everything and paste it into an email. So clunky."
            ),
            "survey_sharing": "Easier report sharing with stakeholders is badly needed.",
            "interview_sharing": "Getting a report in front of someone outside the tool is painful.",
        },
    }
    
    segments = ["Enterprise", "Mid-Market", "SMB", "Free"]
    customers = [
        "Dana Park", "Alex Chen", "Jordan Rivera", "Casey Matthews", "Morgan Blake",
        "Taylor Kim", "Riley Johnson", "Sam Cohen", "Casey Davis", "Morgan Hayes",
        "Alex Thompson", "Jordan Long", "Dana Wilson", "Sam Martin", "Riley Anderson",
        "Taylor Brown", "Morgan Young", "Casey Foster", "Alex Miller", "Jordan Taylor",
        "Pat Wilson", "Jamie Lee", "Morgan Smith", "Casey Young", "Alex Davis"
    ]
    
    sources = []
    source_id_counter = 1
    
    # Generate variations for each recurring problem
    for problem_key, variations in recurring_problems.items():
        for variant_key, text in variations.items():
            if variant_key.startswith("enterprise"):
                segment = "Enterprise"
            elif variant_key.startswith("smb"):
                segment = "SMB"
            elif variant_key.startswith("free"):
                segment = "Free"
            else:
                segment = random.choice(segments)
            source_type = "interview"
            
            if "casual" in variant_key or "survey" in variant_key:
                source_type = random.choice(["survey", "support_ticket"])
            elif "formal" in variant_key or "technical" in variant_key:
                source_type = "interview"
            elif "ticket" in variant_key or "support" in variant_key:
                source_type = "support_ticket"
            
            if segment == "Enterprise":
                source_type = random.choice(["interview", "interview", "survey"])
            elif segment == "Free":
                source_type = random.choice(["survey", "support_ticket"])
            
            date = (datetime.now() - timedelta(days=random.randint(1, 90))).strftime("%Y-%m-%d")
            
            sources.append({
                "id": f"src_{source_id_counter:03d}",
                "source_type": source_type,
                "customer_name": random.choice(customers),
                "segment": segment,
                "date": date,
                "text": text
            })
            source_id_counter += 1
    
    # Add more standalone sources for breadth/realism.
    standalone = [
        ("Enterprise", "interview", "Mobile app is needed. Our team works remotely and needs to check reports on the go."),
        ("SMB", "survey", "Performance issues with large datasets."),
        ("Mid-Market", "support_ticket", "Ticket: Dark mode would reduce eye strain."),
        ("Enterprise", "interview", "Need better audit logging for compliance."),
        ("Free", "survey", "Learning curve is steep. More tutorials would help new users."),
        ("SMB", "interview", "Our biggest pain is we can't easily share reports with stakeholders."),
        ("Enterprise", "survey", "Need real-time alerts for data sync failures."),
        ("Mid-Market", "interview", "Third-party integrations break frequently."),
        ("Free", "support_ticket", "Ticket: Feature requests for bulk import functionality."),
        ("SMB", "interview", "Reporting interface is hard to navigate."),
        ("Enterprise", "survey", "Data export reliability is critical for our operations."),
        ("Mid-Market", "survey", "Would like better data visualization options."),
        ("Free", "interview", "API documentation could be more comprehensive."),
        ("Enterprise", "support_ticket", "Ticket: Scaling issues with concurrent users."),
        ("SMB", "support_ticket", "Ticket: Integration with Google Sheets needed."),
        ("Mid-Market", "interview", "Custom report scheduling would be very helpful."),
        ("Enterprise", "interview", "Need GDPR compliance improvements."),
        ("Free", "survey", "Free tier limitations are too restrictive."),
        ("Mid-Market", "interview", "We'd love saved filter presets so we stop rebuilding the same view."),
        ("Enterprise", "survey", "Single sign-on via Okta is a hard requirement for our security team."),
        ("SMB", "support_ticket", "Ticket: Timezone handling is wrong, all my timestamps are off by hours."),
        ("Free", "interview", "The onboarding emails are helpful but the product itself still felt confusing."),
        ("Mid-Market", "survey", "Cross-filtering between charts would make analysis much faster."),
        ("Enterprise", "interview", "We need white-labeling so we can embed dashboards in our own portal."),
        ("SMB", "survey", "Would love a way to annotate charts before sharing them."),
        ("Mid-Market", "support_ticket", "Ticket: Scheduled report email never arrived this morning."),
        ("Free", "survey", "More chart types, please — pie and bar only feels limiting."),
        ("Enterprise", "support_ticket", "Ticket: Data retention policy config is missing for compliance."),
        ("SMB", "interview", "Every time I refresh, my custom layout resets to the default."),
        ("Mid-Market", "interview", "Drill-down from a summary chart into the raw rows doesn't work well."),
        ("Free", "support_ticket", "Ticket: Can't undo an accidental delete of a saved report."),
        ("Enterprise", "survey", "We need SOC 2 documentation before we can expand our contract."),
        ("SMB", "survey", "The color palette isn't colorblind-friendly for our team."),
        ("Mid-Market", "interview", "Loading spinner sometimes hangs and I have to reload the whole page."),
    ]
    
    for segment, source_type, text in standalone:
        date = (datetime.now() - timedelta(days=random.randint(1, 90))).strftime("%Y-%m-%d")
        sources.append({
            "id": f"src_{source_id_counter:03d}",
            "source_type": source_type,
            "customer_name": random.choice(customers),
            "segment": segment,
            "date": date,
            "text": text
        })
        source_id_counter += 1
    
    os.makedirs("data", exist_ok=True)
    
    output_file = "data/sources.json"
    with open(output_file, "w") as f:
        json.dump(sources, f, indent=2)
    
    source_type_counts = {}
    segment_counts = {}
    for source in sources:
        source_type_counts[source["source_type"]] = source_type_counts.get(source["source_type"], 0) + 1
        segment_counts[source["segment"]] = segment_counts.get(source["segment"], 0) + 1
    
    print(f"✓ Generated {len(sources)} sources")
    print(f"  By type: {source_type_counts}")
    print(f"  By segment: {segment_counts}")
    print(f"  Written to: {output_file}")


if __name__ == "__main__":
    generate_synthetic_data()
