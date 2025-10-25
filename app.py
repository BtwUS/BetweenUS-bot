import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Import the agent executor from our agent module
from agent import agent_executor, ConflictResolutionState
from tools.slack_tools import set_slack_client

# Load environment variables from the .env file
load_dotenv()

# Initialize Slack App with bot and app tokens
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
client = app.client  # The web client is needed for the tools

# Set the Slack client for tools to use
set_slack_client(client)

# --- Define the Slack event handler ---
@app.event("app_mention")
def handle_app_mention_events(body, say):
    try:
        user_message_text = body["event"]["text"]
        channel_id = body["event"]["channel"]
        user_id = body["event"]["user"]
        bot_user_id = client.auth_test()["user_id"]

        # Clean the message by removing the bot's mention
        clean_message = user_message_text.replace(f"<@{bot_user_id}>", "").strip()
        
        # Add context about the channel and user for better personalization
        clean_message += f" [Context: This is from user {user_id} in channel {channel_id}]"
        
        # Print the cleaned message for debugging
        print(f"Received message: {clean_message} from user: {user_id} in channel: {channel_id}")

        # Create initial state for the LangGraph agent
        initial_state = {
            "messages": [HumanMessage(content=clean_message)]
        }
        
        # Invoke the LangGraph conflict resolution agent
        result = agent_executor.invoke(
            initial_state,
            config={
                "recursion_limit": 10,  # Allow more iterations for complex conflict resolution
                "configurable": {
                    "channel_id": channel_id,
                    "user_id": user_id
                }
            }
        )
        
        # Extract the final response from the agent
        final_messages = result["messages"]
        
        # Get the last AI message (not tool messages)
        final_response = None
        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage) and not hasattr(msg, 'tool_calls'):
                final_response = msg.content
                break
            elif isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and not msg.tool_calls:
                final_response = msg.content
                break
        
        if not final_response:
            # Fallback if no AI message found
            final_response = "I'm your Slack Conflict Analyst. Mention me with details about a conflict or channel ID to analyze."
        
        # Post the agent's response back to the Slack channel
        say(text=final_response)
        # say(text=final_response, thread_ts=body["event"]["ts"])
        
    except Exception as e:
        print(f"Error in conflict resolution agent: {e}")
        error_message = "I encountered an issue while processing your message. Let me try to help you find a solution anyway. What specific conflict or challenge are you facing?"
        say(text=error_message)
        # say(text=error_message, thread_ts=body["event"]["ts"])

# --- Start the app ---
if __name__ == "__main__":
    SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()
