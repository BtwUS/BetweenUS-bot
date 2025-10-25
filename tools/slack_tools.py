"""Slack-specific tools for the conflict resolution bot."""

import os
from datetime import datetime
from langchain_core.tools import tool
from slack_sdk import WebClient

# Initialize Slack client - this will be set from app.py
client: WebClient = None

def set_slack_client(slack_client: WebClient):
    """Set the Slack client for the tools to use."""
    global client
    client = slack_client

@tool
def get_channel_history(channel_id: str, limit: int = 5) -> str:
    """
    Fetches the recent history of a Slack channel.
    Useful for getting context about a conversation.
    The `channel_id` is the ID of the conversation.
    """
    if client is None:
        return "Error: Slack client not initialized"
    
    try:
        result = client.conversations_history(channel=channel_id, limit=limit)
        messages = result["messages"]
        history_str = ""
        for msg in reversed(messages):
            user = msg.get("user")
            text = msg.get("text")
            timestamp = datetime.fromtimestamp(float(msg["ts"])).strftime('%Y-%m-%d %H:%M:%S')
            
            # Add user and timestamp information for context
            history_str += f"[**User: {user} at {timestamp}**] {text}\n"
        return history_str
    except Exception as e:
        return f"Error fetching channel history: {e}"

@tool
def get_user_info(user_id: str) -> str:
    """
    Fetches information about a Slack user.
    Useful for getting a username or other details for context.
    """
    if client is None:
        return "Error: Slack client not initialized"
    
    try:
        user_info = client.users_info(user=user_id)
        if user_info["ok"]:
            return user_info["user"]["profile"]["real_name"]
        return f"User info not found for ID: {user_id}"
    except Exception as e:
        return f"Error fetching user info: {e}"