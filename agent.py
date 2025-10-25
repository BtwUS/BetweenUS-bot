"""Slack Conflict Analyst agent using LangGraph."""

import os
from typing import TypedDict, Annotated, Sequence, Literal
import operator
from dotenv import load_dotenv

# Import LangGraph and LangChain components
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Import tools from our tools package
from tools import (
    get_channel_history, 
    get_user_info, 
    google_search_tool,
    find_user_by_name,
    get_mentioned_users,
    list_channel_members,
    summarize_channel_history
)

# Load environment variables
load_dotenv()

# Define the tools
tools = [
    get_channel_history, 
    get_user_info, 
    google_search_tool,
    find_user_by_name,
    get_mentioned_users,
    list_channel_members,
    summarize_channel_history
]

# Initialize the LLM with ChatGroq
llm = ChatGroq(
    temperature=0.5,  # Balanced for analytical insights with human warmth
    groq_api_key=os.environ.get("GROQ_API_KEY"),
    model_name="openai/gpt-oss-120b"
)

# Define the agent state
class ConflictResolutionState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# Load the conflict resolution system prompt from file
def load_system_prompt():
    """Load the system prompt from the prompts directory."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "conflict_analyst_prompt.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

# Define the conflict resolution system prompt
CONFLICT_RESOLUTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", load_system_prompt()),
    MessagesPlaceholder(variable_name="messages"),
])

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

def conflict_resolution_agent(state: ConflictResolutionState):
    """The Slack Conflict Analyst agent that analyzes conversations and provides neutral summaries."""
    messages = state['messages']
    
    # Create the prompt with tools
    prompt = CONFLICT_RESOLUTION_PROMPT
    chain = prompt | llm.bind_tools(tools)
    
    # Get response from LLM
    response = chain.invoke({"messages": messages})
    
    return {"messages": [response]}

def should_continue(state: ConflictResolutionState) -> Literal["tools", "end"]:
    """Determine whether to continue with tool calls or end."""
    messages = state['messages']
    last_message = messages[-1]
    
    # If the last message has tool calls, execute tools
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    else:
        return "end"

# Build the conflict resolution graph
def create_agent_executor():
    """Create and return the compiled agent executor."""
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
    return workflow.compile()

# Create the agent executor
agent_executor = create_agent_executor()