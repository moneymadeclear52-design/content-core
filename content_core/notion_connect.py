"""
notion_connect.py
Notion integration for the Perspective Bank + Originality Gate audit log.

CONFIGURATION (via environment variables — never hardcode secrets):
  NOTION_TOKEN         Internal integration token from notion.so/my-integrations
  PERSPECTIVE_DB_ID    Perspective Bank database ID
  FRAMEWORKS_DB_ID     Frameworks database ID
  VOICE_ASSETS_DB_ID   Voice assets database ID
  GATES_DB_ID          Originality gate audit-log database ID

Copy .env.example to .env and fill these in. The .env file is gitignored.

Setup:
  pip install notion-client python-dotenv
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from notion_client import Client

# ─── Secrets & config from environment ─────────────────────────────────────────
NOTION_TOKEN       = os.getenv("NOTION_TOKEN", "")
PERSPECTIVE_DB_ID  = os.getenv("PERSPECTIVE_DB_ID", "fc5b0f1b5e824631bde5c30dc1a54cc5")
FRAMEWORKS_DB_ID   = os.getenv("FRAMEWORKS_DB_ID", "b5c6f872b15542ee98471d0dc38226f3")
VOICE_ASSETS_DB_ID = os.getenv("VOICE_ASSETS_DB_ID", "0632211b2f3f4bbd9332ef23be4df929")
GATES_DB_ID        = os.getenv("GATES_DB_ID", "ee55ff1a66b0432198bc0c897d2d4948")

if not NOTION_TOKEN:
    print("[WARNING] NOTION_TOKEN not set — Notion features will fail. "
          "Set it in your .env file.")

notion = Client(auth=NOTION_TOKEN)


def test_connection():
    """Verify your API key works."""
    try:
        me = notion.users.me()
        print(f"✅ Connected to Notion as: {me.get('name', 'Unknown')}")
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("Check your NOTION_TOKEN and make sure the integration is connected to your page.")
        return False


def add_perspective(take_text, take_type, channels, topics):
    """
    Add a single perspective to the Perspective Bank.

    take_type options:  Hot Take, Verdict, Observation,
                        Counter-conventional, Anecdote, Framework
    channels options:   CrimeScopeAI, Money Made Clear,
                        RapidReelz, RapidReelz Stories, All
    """
    try:
        notion.pages.create(
            parent={"database_id": PERSPECTIVE_DB_ID},
            properties={
                "Take Text": {
                    "title": [{"text": {"content": take_text}}]
                },
                "Take Type": {
                    "select": {"name": take_type}
                },
                "Channel": {
                    "multi_select": [{"name": ch} for ch in channels]
                },
                "Topics": {
                    "multi_select": [{"name": t} for t in topics]
                },
                "Times Used": {
                    "number": 0
                },
                "Performance": {
                    "select": {"name": "Untested"}
                },
                "Status": {
                    "select": {"name": "Active"}
                }
            }
        )
        print(f"✅ Added perspective: {take_text[:60]}...")
    except Exception as e:
        print(f"❌ Failed to add perspective: {e}")


def get_perspectives_for_channel(channel, topic_filter=None, limit=10):
    """
    Pull active perspectives for a given channel.
    Used by the Originality Injector.
    """

    filters = {
        "and": [
            {"property": "Status", "select": {"equals": "Active"}},
            {"or": [
                {"property": "Channel", "multi_select": {"contains": channel}},
                {"property": "Channel", "multi_select": {"contains": "All"}}
            ]}
        ]
    }

    results = notion.databases.query(
        database_id=PERSPECTIVE_DB_ID,
        filter=filters,
        sorts=[{"property": "Times Used", "direction": "ascending"}]
    )

    perspectives = []
    for page in results['results'][:limit]:
        props = page['properties']
        title_arr = props.get('Take Text', {}).get('title', [])
        take_text = title_arr[0]['plain_text'] if title_arr else ""
        take_type_obj = props.get('Take Type', {}).get('select')
        take_type = take_type_obj['name'] if take_type_obj else "Unknown"

        perspectives.append({
            "id": page['id'],
            "text": take_text,
            "type": take_type
        })

    return perspectives


def get_framework_for_channel(channel):
    """Pull the primary framework for a channel."""
    results = notion.databases.query(
        database_id=FRAMEWORKS_DB_ID,
        filter={"property": "Channel", "select": {"equals": channel}}
    )

    if results['results']:
        props = results['results'][0]['properties']
        name_arr = props.get('Framework Name', {}).get('title', [])
        name = name_arr[0]['plain_text'] if name_arr else "Unnamed"
        template_arr = props.get('Template', {}).get('rich_text', [])
        template = template_arr[0]['plain_text'] if template_arr else ""

        return {"name": name, "template": template}

    return None


def log_originality_gate(content_id, channel, score, passed, framework_name="", perspectives_used=""):
    """Log a gate result to Notion for audit trail."""
    try:
        notion.pages.create(
            parent={"database_id": GATES_DB_ID},
            properties={
                "Content ID": {
                    "title": [{"text": {"content": content_id}}]
                },
                "Channel": {
                    "select": {"name": channel}
                },
                "Voice Used": {
                    "checkbox": True
                },
                "Framework Applied": {
                    "rich_text": [{"text": {"content": framework_name}}]
                },
                "Perspectives Used": {
                    "rich_text": [{"text": {"content": perspectives_used}}]
                },
                "Originality Score": {
                    "number": score
                },
                "Passed": {
                    "checkbox": passed
                }
            }
        )
    except Exception as e:
        print(f"Warning: Could not log gate result: {e}")


# ─── BULK IMPORT FROM TEXT FILE ─────────────────────────────────────────────────
def bulk_import_perspectives(filepath):
    """
    Import perspectives from a text file.
    Format: one per line as CSV:
    take_text | take_type | channel1,channel2 | topic1,topic2

    Example line:
    Most people treat savings as what's left over, not a fixed expense. | Counter-conventional | Money Made Clear | budgeting,savings
    """
    imported = 0
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split('|')]
            if len(parts) != 4:
                print(f"Skipping malformed line: {line[:50]}")
                continue

            take_text, take_type, channels_str, topics_str = parts
            channels = [c.strip() for c in channels_str.split(',')]
            topics = [t.strip() for t in topics_str.split(',')]

            add_perspective(take_text, take_type, channels, topics)
            imported += 1

    print(f"\n✅ Imported {imported} perspectives.")


if __name__ == "__main__":
    print("Testing Notion connection...")
    if test_connection():
        print("\nFetching a sample from Perspective Bank...")
        sample = get_perspectives_for_channel("Money Made Clear", limit=3)
        if sample:
            print(f"\nFound {len(sample)} perspectives:")
            for p in sample:
                print(f"  [{p['type']}] {p['text'][:80]}")
        else:
            print("Perspective Bank is empty — run your batch capture session first!")
