import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Sequence
import operator
from datetime import datetime

# --- Import LangGraph and LangChain components ---
from langgraph.prebuilt import create_react_agent
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_community.utilities import GoogleSearchAPIWrapper
from langchain_community.tools import GoogleSearchRun
from slack_sdk import WebClient

# Load environment variables from the .env file
load_dotenv()

# Initialize Slack App with bot and app tokens
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
client = app.client # The web client is needed for the tools

# --- Define custom Slack Tools using the @tool decorator ---

@tool
def get_channel_history(channel_id: str, limit: int = 5) -> str:
    """
    Fetches the recent history of a Slack channel.
    Useful for getting context about a conversation.
    The `channel_id` is the ID of the conversation.
    """
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
    try:
        user_info = client.users_info(user=user_id)
        if user_info["ok"]:
            return user_info["user"]["profile"]["real_name"]
        return f"User info not found for ID: {user_id}"
    except Exception as e:
        return f"Error fetching user info: {e}"

# --- Initialize Google Search Tool ---
search = GoogleSearchAPIWrapper(
    google_api_key=os.environ.get("GOOGLE_API_KEY"),
    google_cse_id=os.environ.get("GOOGLE_CSE_ID")
)


google_search_tool = GoogleSearchRun(api_wrapper=search)

# --- Initialize the LLM with ChatGroq ---
llm = ChatGroq(
    temperature=0,
    groq_api_key=os.environ.get("GROQ_API_KEY"),
    model_name="openai/gpt-oss-120b"
)

# --- Define the agent and tool ---
tools = [get_channel_history, get_user_info, google_search_tool]


agent_executor = create_react_agent(
    model=llm,
    tools=tools,
)

# --- Define the Slack event handler ---
@app.event("app_mention")
def handle_app_mention_events(body, say):
    try:
        user_message_text = body["event"]["text"]
        channel_id = body["event"]["channel"]
        bot_user_id = client.auth_test()["user_id"]

        # Clean the message by removing the bot's mention
        clean_message = user_message_text.replace(f"<@{bot_user_id}>", "").strip()
        clean_message += f" from channel {channel_id}"
        # Print the cleaned message for debugging
        print(f"Received message: {clean_message} from channel: {channel_id}")

        # LangGraph agents expect messages to be in a list format
        messages = [HumanMessage(content=clean_message)]
        
        # Invoke the LangGraph agent with recursion limit
        response = agent_executor.invoke(
            {"messages": messages},
            config={"recursion_limit": 5}  # Limit agent to 10 iterations max
            # Pass thread_ts to track conversation history if needed
            # "thread_ts": body["event"]["ts"]  
        )
        
        # The agent's response is an object; extract the last message
        final_message = response["messages"][-1].content
        
        # Post the agent's response back to the Slack channel
        say(text=final_message, thread_ts=body["event"]["ts"])
    except Exception as e:
        print(f"Error: {e}")
        say(f"An error occurred: {e}", thread_ts=body["event"]["ts"])

# --- Start the app ---
if __name__ == "__main__":
    SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()
