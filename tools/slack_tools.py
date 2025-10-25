"""Slack-specific tools for the conflict resolution bot."""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re
from langchain_core.tools import tool
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

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
    
@tool
def find_user_by_name(name: str, channel_id: str) -> str:
    """
    Finds a Slack user ID by their name or display name.
    Useful when someone says "tell John" or "ask Sarah" - helps identify who to mention.
    
    Args:
        name: The name or partial name of the user to find
        channel_id: The channel ID to search within for context
    
    Returns:
        User ID in format <@U12345> for mentioning, or error message
    """
    try:
        # Get channel members
        members_response = client.conversations_members(channel=channel_id)
        
        if not members_response.get("ok"):
            return f"Error: Unable to access channel members. Bot may need additional permissions (users:read, channels:read)."
        
        member_ids = members_response.get("members", [])
        
        if not member_ids:
            return "No members found in this channel."
        
        # Search through members for name match
        name_lower = name.lower().strip()
        best_match = None
        all_names = []  # For debugging
        
        for user_id in member_ids:
            try:
                user_info = client.users_info(user=user_id)
                if user_info.get("ok"):
                    profile = user_info["user"]["profile"]
                    real_name = profile.get("real_name", "").lower()
                    display_name = profile.get("display_name", "").lower()
                    username = user_info["user"].get("name", "").lower()
                    
                    # Store for potential suggestion
                    all_names.append(profile.get("real_name", username))
                    
                    # Check for exact or partial match
                    if (name_lower in real_name or 
                        name_lower in display_name or 
                        name_lower in username or
                        real_name.startswith(name_lower) or
                        display_name.startswith(name_lower)):
                        best_match = user_id
                        break  # Found a match
            except Exception as e:
                continue
        
        if best_match:
            return f"<@{best_match}>"
        else:
            # Provide helpful suggestions
            suggestions = ", ".join(all_names[:10])  # Show first 10 names
            return f"Could not find user matching '{name}' in this channel. Available users include: {suggestions}"
            
    except Exception as e:
        return f"Error finding user: {e}. Bot may need permissions: users:read, channels:read"

@tool
def get_mentioned_users(message_text: str) -> str:
    """
    Extracts user IDs from Slack mentions in a message.
    Useful for identifying who was already mentioned/tagged in a conversation.
    
    Args:
        message_text: The message text containing potential <@U12345> mentions
    
    Returns:
        Comma-separated list of user IDs that were mentioned
    """
    try:
        # Slack mentions format: <@U12345>
        mention_pattern = r'<@([UW][A-Z0-9]+)>'
        matches = re.findall(mention_pattern, message_text)
        
        if matches:
            # Get real names for context
            names = []
            for user_id in matches:
                try:
                    user_info = client.users_info(user=user_id)
                    if user_info.get("ok"):
                        name = user_info["user"]["profile"].get("real_name", user_id)
                        names.append(f"{name} (<@{user_id}>)")
                except Exception:
                    names.append(f"<@{user_id}>")
            
            return f"Found {len(matches)} mentioned user(s): {', '.join(names)}"
        else:
            return "No users were mentioned in this message"
            
    except Exception as e:
        return f"Error extracting mentions: {e}"

@tool
def list_channel_members(channel_id: str) -> str:
    """
    Lists all members in a Slack channel with their names.
    Useful when someone asks "who is in this channel" or needs to see available users.
    
    Args:
        channel_id: The channel ID to get members from
    
    Returns:
        List of member names and IDs
    """
    try:
        members_response = client.conversations_members(channel=channel_id)
        
        if not members_response.get("ok"):
            return "Error: Unable to access channel members. Bot needs permissions: users:read, channels:read"
        
        member_ids = members_response.get("members", [])
        
        if not member_ids:
            return "No members found in this channel."
        
        member_list = []
        for user_id in member_ids:
            try:
                user_info = client.users_info(user=user_id)
                if user_info.get("ok"):
                    user = user_info["user"]
                    # Skip bots unless specifically requested
                    if user.get("is_bot"):
                        continue
                    
                    real_name = user["profile"].get("real_name", user.get("name", "Unknown"))
                    member_list.append(f"• {real_name} (<@{user_id}>)")
            except Exception:
                continue
        
        if member_list:
            return f"Channel members ({len(member_list)} users):\n" + "\n".join(member_list)
        else:
            return "No human members found in this channel."
            
    except Exception as e:
        return f"Error listing members: {e}"

# --- NEW: summarization tool ---

def _resolve_real_name_cache(user_ids: List[str]) -> Dict[str, str]:
    """Batch-resolve user IDs to real names with caching behavior."""
    names: Dict[str, str] = {}
    for uid in set([u for u in user_ids if u]):
        try:
            info = client.users_info(user=uid)
            if info.get("ok"):
                names[uid] = info["user"]["profile"].get("real_name") or info["user"]["name"] or uid
            else:
                names[uid] = uid
        except SlackApiError:
            names[uid] = uid
        except Exception:
            names[uid] = uid
    return names

def _iter_channel_messages(channel_id: str, oldest_ts: float, max_messages: int) -> List[dict]:
    """Paginate through channel history from newest to oldest within time window."""
    messages: List[dict] = []
    cursor = None
    while True:
        try:
            resp = client.conversations_history(
                channel=channel_id,
                limit=200,
                cursor=cursor,
                oldest=str(oldest_ts),
                include_all_metadata=False
            )
        except SlackApiError as e:
            # Respect rate limits
            if e.response and e.response.status_code == 429:
                delay = int(e.response.headers.get("Retry-After", "2"))
                time.sleep(delay)
                continue
            raise
        msgs = resp.get("messages", [])
        messages.extend(msgs)
        if len(messages) >= max_messages:
            break
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    # Keep newest→oldest order for LLM context building
    messages.sort(key=lambda m: float(m.get("ts", "0")), reverse=False)
    return messages[:max_messages]

def _chunk(text: str, chunk_size: int = 5000) -> List[str]:
    """Simple character-based chunker."""
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

@tool
def summarize_channel_history(
    channel_id: str,
    hours: int = 24,
    user_id: Optional[str] = None,
    max_messages: int = 800
) -> str:
    """
    Summarize recent Slack conversation in a channel.

    Args:
        channel_id: Slack channel ID (e.g., C0123456789).
        hours: Lookback window. Default 24 hours.
        user_id: Optional Slack user ID. If provided, summarize only that user's messages.
        max_messages: Hard cap on messages fetched across pagination.

    Returns:
        A concise summary with key themes, decisions, open questions, and action items.
    """
    try:
        oldest_dt = datetime.utcnow() - timedelta(hours=hours)
        oldest_ts = oldest_dt.timestamp()

        # Fetch messages
        raw_msgs = _iter_channel_messages(channel_id, oldest_ts, max_messages)

        # Filter and format
        filtered = []
        user_ids = []
        for m in raw_msgs:
            # Skip join/leave and non-text events
            subtype = m.get("subtype")
            if subtype and subtype not in (None, ""):
                continue
            text = m.get("text", "").strip()
            if not text:
                continue
            uid = m.get("user") or m.get("bot_id")  # prefer human user when present
            if user_id and uid != user_id:
                continue
            ts_str = datetime.fromtimestamp(float(m["ts"])).strftime("%Y-%m-%d %H:%M:%S")
            filtered.append((uid, ts_str, text))
            if m.get("user"):
                user_ids.append(m["user"])

        if not filtered:
            return "No eligible messages in the specified window."

        # Resolve real names for readability
        name_map = _resolve_real_name_cache(user_ids)

        # Build linearized transcript
        transcript_lines = []
        for uid, ts_str, text in filtered:
            label = name_map.get(uid, uid) if isinstance(uid, str) else "Unknown"
            transcript_lines.append(f"[{ts_str}] {label}: {text}")
        transcript = "\n".join(transcript_lines)

        # Summarize with LLM, using hierarchical reduction for long transcripts
        system_preamble = (
            "You are a helpful meeting summarizer. Produce a crisp, factual summary with sections:\n"
            "1) Key themes\n2) Decisions/Agreements\n3) Open questions\n4) Action items with owners and due dates when stated.\n"
            "Be faithful to the content, avoid speculation, and keep it concise."
        )

        def summarize_block(text_block: str) -> str:
            prompt = (
                f"{system_preamble}\n\nTranscript:\n```\n{text_block}\n```\n\n"
                "Write the summary now."
            )
            # ChatGroq supports simple string or message inputs
            out = llm.invoke([HumanMessage(content=prompt)])
            return getattr(out, "content", str(out))

        chunks = _chunk(transcript, chunk_size=5000)
        if len(chunks) == 1:
            final = summarize_block(chunks[0])
        else:
            # Map-reduce summarization
            partials = [summarize_block(c) for c in chunks]
            combined = "\n\n".join(f"PART {i+1} SUMMARY:\n{p}" for i, p in enumerate(partials))
            final = summarize_block(combined)

        header = f"Channel summary for <#{channel_id}> over the last {hours} hours"
        if user_id:
            # Attempt to present a readable handle for the person
            try:
                info = client.users_info(user=user_id)
                if info.get("ok"):
                    rn = info["user"]["profile"].get("real_name") or info["user"]["name"] or user_id
                    header += f" (focused on {rn})"
                else:
                    header += f" (focused on <@{user_id}>)"
            except Exception:
                header += f" (focused on <@{user_id}>)"

        return f"*{header}*\n\n{final}"

    except Exception as e:
        return f"Error summarizing channel history: {e}"