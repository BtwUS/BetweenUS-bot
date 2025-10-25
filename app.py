import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Sequence, Literal
import operator
from datetime import datetime

# --- Import LangGraph and LangChain components ---
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_community.utilities import GoogleSearchAPIWrapper
from langchain_community.tools import GoogleSearchRun
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
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

# --- Define the tools ---
tools = [get_channel_history, get_user_info, google_search_tool]

# --- Initialize the LLM with ChatGroq ---
llm = ChatGroq(
    temperature=0.7,  # Increased for more empathetic responses
    groq_api_key=os.environ.get("GROQ_API_KEY"),
    model_name="openai/gpt-oss-120b"
)







# --- Define the agent state ---
class ConflictResolutionState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
# --- Define the conflict resolution system prompt ---
CONFLICT_RESOLUTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a master of conflict resolution and psychology, skilled in the art of language to help people find common ground. Your approach follows these principles:

🎯 **Core Mission**: Patiently help conflicting parties discover mutual interests and previously unseen feasible solutions.

🧠 **Psychological Approach**:
- Listen deeply and reflect what you hear to validate each person's perspective
- Identify underlying needs, fears, and values behind positions
- Reframe problems to reveal opportunities for collaboration
- Use empathetic language that builds bridges rather than walls
- Address misinformation gently with facts, not confrontation
- Challenge misconceptions through questions that promote self-discovery

🗣️ **Communication Style**:
- Speak with warmth, wisdom, and genuine curiosity
- Use "we" language to create unity ("How might we..." instead of "You should...")
- Ask powerful questions that shift perspective
- Acknowledge emotions before addressing logic
- Find the grain of truth in each viewpoint
- Celebrate small agreements as stepping stones to larger solutions

🔍 **Problem Analysis**:
- Break down big problems into smaller, manageable pieces
- Look for win-win solutions that address core needs of all parties
- Identify shared values and common goals
- Explore creative alternatives that haven't been considered
- Address root causes, not just symptoms

📋 **Available Tools**:
- get_channel_history: Use to understand conversation context and patterns
- get_user_info: Use to personalize your approach and build rapport  
- google_search_tool: Use to find factual information to resolve misconceptions

Remember: Your goal is not to take sides, but to help all parties see new possibilities for mutual benefit. Be patient, wise, and genuinely invested in their success."""),
    MessagesPlaceholder(variable_name="messages"),
])

# --- Define the tool-calling function ---
def call_tools(state: ConflictResolutionState):
    """Execute tools when the agent decides to use them."""
    messages = state['messages']
    last_message = messages[-1]
    
    # Create tool executor
    tool_executor = {tool.name: tool for tool in tools}
    tool_outputs = []
    
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call['args']
            
            if tool_name in tool_executor:
                try:
                    result = tool_executor[tool_name].invoke(tool_args)
                    tool_outputs.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call['id'],
                        name=tool_name
                    ))
                except Exception as e:
                    tool_outputs.append(ToolMessage(
                        content=f"Error executing {tool_name}: {str(e)}",
                        tool_call_id=tool_call['id'],
                        name=tool_name
                    ))
    
    return {"messages": tool_outputs}

# --- Define the agent function ---
def conflict_resolution_agent(state: ConflictResolutionState):
    """The main agent that processes messages and decides on actions."""
    messages = state['messages']
    
    # Create the prompt with tools
    prompt = CONFLICT_RESOLUTION_PROMPT
    chain = prompt | llm.bind_tools(tools)
    
    # Get response from LLM
    response = chain.invoke({"messages": messages})
    
    return {"messages": [response]}

# --- Define tool execution condition ---
def should_continue(state: ConflictResolutionState) -> Literal["tools", "end"]:
    """Determine whether to continue with tool calls or end."""
    messages = state['messages']
    last_message = messages[-1]
    
    # If the last message has tool calls, execute tools
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    else:
        return "end"

# --- Build the conflict resolution graph ---
workflow = StateGraph(ConflictResolutionState)

# Add nodes
workflow.add_node("agent", conflict_resolution_agent)
workflow.add_node("tools", call_tools)

# Set entry point
workflow.set_entry_point("agent")

# Add conditional edges
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        "end": END,
    }
)

# Add edge from tools back to agent
workflow.add_edge("tools", "agent")

# Compile the graph
agent_executor = workflow.compile()

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
            final_response = "I'm here to help with any conflicts or discussions. How can I assist you in finding common ground?"
        
        # Post the agent's response back to the Slack channel
        say(text=final_response, thread_ts=body["event"]["ts"])
        
    except Exception as e:
        print(f"Error in conflict resolution agent: {e}")
        error_message = "I encountered an issue while processing your message. Let me try to help you find a solution anyway. What specific conflict or challenge are you facing?"
        say(text=error_message, thread_ts=body["event"]["ts"])

# --- Start the app ---
if __name__ == "__main__":
    SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()
