"""
Google Apps Script MCP Server — LLM-callable tools for Gmail, Sheets, Docs, Drive, Calendar.
All calls route through a deployed google_bridge.gs Web App.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apps_script_client import call_bridge, is_configured
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("GoogleAppsScript")

NOT_CONFIGURED = (
    "Google Apps Script MCP is not configured.\n"
    "1. Deploy google_bridge.gs as a Web App at script.google.com\n"
    "2. Set APPS_SCRIPT_URL and APPS_SCRIPT_SECRET in your .env file"
)


def _check_or_call(action: str, params: dict) -> str:
    if not is_configured():
        return json.dumps({"error": NOT_CONFIGURED})
    result = call_bridge(action, params)
    return json.dumps(result, indent=2, default=str)


# ── Gmail ────────────────────────────────────────────────────────────


@mcp.tool()
def gmail_search(query: str = "is:unread", max_results: int = 5) -> str:
    """Search Gmail for emails matching a query string.

    Uses the same query syntax as Gmail search bar.
    Examples: 'from:boss', 'subject:meeting', 'after:2025/01/01'.

    Args:
        query: Gmail search query (default 'is:unread')
        max_results: Max emails to return (default 5, max 20)
    """
    return _check_or_call(
        "gmail_search",
        {
            "query": query,
            "max_results": min(max(1, max_results), 20),
        },
    )


@mcp.tool()
def gmail_send(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
    """Send an email from the user's Gmail account.

    Only use when the user explicitly asks to send an email.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body (plain text)
        cc: Optional CC recipients (comma separated)
        bcc: Optional BCC recipients (comma separated)
    """
    params = {"to": to, "subject": subject, "body": body}
    if cc:
        params["cc"] = cc
    if bcc:
        params["bcc"] = bcc
    return _check_or_call("gmail_send", params)


@mcp.tool()
def gmail_read(thread_id: str) -> str:
    """Read all messages in a Gmail thread.

    Args:
        thread_id: Gmail thread ID returned by gmail_search or gmail_list_unread
    """
    return _check_or_call("gmail_read", {"thread_id": thread_id})


@mcp.tool()
def gmail_list_unread(max_results: int = 10) -> str:
    """Get the user's unread email count and list recent unread messages.

    Args:
        max_results: Max unread threads to show (default 10, max 20)
    """
    return _check_or_call(
        "gmail_list_unread",
        {
            "max_results": min(max(1, max_results), 20),
        },
    )


# ── Google Sheets ────────────────────────────────────────────────────


@mcp.tool()
def sheets_read(
    spreadsheet_id: str, range: str = "A1:Z100", sheet_name: str = ""
) -> str:
    """Read data from a Google Spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet ID (from the URL: docs.google.com/spreadsheets/d/THIS_PART/edit)
        range: Cell range to read (default 'A1:Z100')
        sheet_name: Sheet tab name (default: active sheet)
    """
    params = {"spreadsheet_id": spreadsheet_id, "range": range}
    if sheet_name:
        params["sheet_name"] = sheet_name
    return _check_or_call("sheets_read", params)


@mcp.tool()
def sheets_write(
    spreadsheet_id: str, range: str, values: str, sheet_name: str = ""
) -> str:
    """Write data to a Google Spreadsheet range.

    Args:
        spreadsheet_id: The spreadsheet ID
        range: Target range (e.g. 'A1:C3')
        values: JSON 2D array of values, e.g. '[["Name","Age"],["Alice",30]]'
        sheet_name: Sheet tab name (default: active sheet)
    """
    try:
        parsed = json.loads(values) if isinstance(values, str) else values
    except json.JSONDecodeError:
        return json.dumps({"error": "values must be a JSON 2D array"})
    params = {"spreadsheet_id": spreadsheet_id, "range": range, "values": parsed}
    if sheet_name:
        params["sheet_name"] = sheet_name
    return _check_or_call("sheets_write", params)


@mcp.tool()
def sheets_append(spreadsheet_id: str, row: str, sheet_name: str = "") -> str:
    """Append a single row to a Google Spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet ID
        row: JSON array of cell values, e.g. '["Alice", 30, "Active"]'
        sheet_name: Sheet tab name (default: active sheet)
    """
    try:
        parsed = json.loads(row) if isinstance(row, str) else row
    except json.JSONDecodeError:
        return json.dumps({"error": "row must be a JSON array"})
    if not isinstance(parsed, list):
        return json.dumps({"error": "row must be a JSON array"})
    params = {"spreadsheet_id": spreadsheet_id, "row": parsed}
    if sheet_name:
        params["sheet_name"] = sheet_name
    return _check_or_call("sheets_append", params)


# ── Google Drive ─────────────────────────────────────────────────────


@mcp.tool()
def drive_search(query: str, max_results: int = 10, type: str = "") -> str:
    """Search Google Drive for files by name or type.

    Args:
        query: Search term for file name
        max_results: Max files to return (default 10, max 30)
        type: Optional MIME type filter (e.g. 'spreadsheet', 'document', 'pdf')
    """
    params = {"query": query, "max_results": min(max(1, max_results), 30)}
    if type:
        params["type"] = type
    return _check_or_call("drive_search", params)


# ── Google Docs ──────────────────────────────────────────────────────


@mcp.tool()
def docs_create(title: str, content: str = "") -> str:
    """Create a new Google Doc with optional initial content.

    Args:
        title: Document title
        content: Optional initial text content
    """
    return _check_or_call("docs_create", {"title": title, "content": content})


# ── Google Calendar ──────────────────────────────────────────────────


@mcp.tool()
def calendar_list_events(days_ahead: int = 7, max_results: int = 10) -> str:
    """List upcoming calendar events from the user's default Google Calendar.

    Args:
        days_ahead: How many days ahead to look (default 7)
        max_results: Max events to return (default 10, max 30)
    """
    return _check_or_call(
        "calendar_list",
        {
            "days_ahead": max(1, days_ahead),
            "max_results": min(max(1, max_results), 30),
        },
    )


if __name__ == "__main__":
    mcp.run()
