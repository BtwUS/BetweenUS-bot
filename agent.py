"""Slack Conflict Analyst agent using LangGraph."""

import os
import json
from typing import TypedDict, Annotated, Sequence, Literal, Optional
import operator
from dotenv import load_dotenv

# Import LangGraph and LangChain components
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
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

# Initialize a separate LLM for classification (lower temperature for more consistent classification)
classifier_llm = ChatGroq(
    temperature=0.1,  # Lower temperature for more deterministic classification
    groq_api_key=os.environ.get("GROQ_API_KEY"),
    model_name="openai/gpt-oss-120b"
)

# Define the agent state
class ConflictResolutionState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    prompt_type: Optional[str]  # Will store "prompt1", "prompt2", "prompt3", or "prompt4"
    classification_reasoning: Optional[str]  # Stores why this classification was chosen

# Load the conflict resolution system prompt from file
def load_system_prompt(prompt_name="conflict_analyst_prompt"):
    """Load the system prompt from the prompts directory.
    
    Args:
        prompt_name: Name of the prompt file (without .txt extension)
    """
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{prompt_name}.txt")
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

# Global variable to store the current prompt name
CURRENT_PROMPT_NAME = "conflict_analyst_prompt"
USE_CLASSIFICATION = True  # Global flag to enable/disable automatic classification

# Define the conflict resolution system prompt
def get_prompt_template():
    """Get the current prompt template based on the selected prompt."""
    return ChatPromptTemplate.from_messages([
        ("system", load_system_prompt(CURRENT_PROMPT_NAME)),
        MessagesPlaceholder(variable_name="messages"),
    ])

def get_dynamic_prompt_template(prompt_type: str):
    """Get a prompt template for a specific prompt type.
    
    Args:
        prompt_type: The prompt type (e.g., "prompt1", "prompt2", etc.)
    """
    return ChatPromptTemplate.from_messages([
        ("system", load_system_prompt(prompt_type)),
        MessagesPlaceholder(variable_name="messages"),
    ])

def classifier_node(state: ConflictResolutionState):
    """Classify the conversation to determine which prompt to use."""
    # Check if classification is disabled
    if not USE_CLASSIFICATION:
        return {
            "prompt_type": CURRENT_PROMPT_NAME,
            "classification_reasoning": "Classification disabled, using fixed prompt"
        }
    
    messages = state['messages']
    
    # Load the classifier prompt
    classifier_prompt_text = load_system_prompt("classifier_prompt")
    
    # Get the user's message (should be the first HumanMessage)
    user_message = None
    for msg in messages:
        if isinstance(msg, HumanMessage):
            user_message = msg.content
            break
    
    if not user_message:
        # Fallback to default prompt if no user message found
        return {"prompt_type": "conflict_analyst_prompt", "classification_reasoning": "No user message found, using default"}
    
    # Create the classification prompt
    classification_messages = [
        SystemMessage(content=classifier_prompt_text),
        HumanMessage(content=f"Analyze and classify this conversation:\n\n{user_message}")
    ]
    
    # Get classification from LLM
    try:
        response = classifier_llm.invoke(classification_messages)
        response_text = response.content.strip()
        
        # Parse the JSON response
        # Remove markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif response_text.startswith("```"):
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        classification_result = json.loads(response_text)
        prompt_type = classification_result.get("classification", "PROMPT1").lower()
        reasoning = classification_result.get("reasoning", "No reasoning provided")
        
        print(f"🔍 Classification: {prompt_type} - {reasoning}")
        
        return {
            "prompt_type": prompt_type,
            "classification_reasoning": reasoning
        }
    except Exception as e:
        print(f"⚠️ Classification error: {e}, using default prompt")
        # Fallback to a reasonable default
        return {
            "prompt_type": "prompt1",
            "classification_reasoning": f"Classification failed: {str(e)}, defaulting to prompt1"
        }

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
    prompt_type = state.get('prompt_type', CURRENT_PROMPT_NAME)
    
    # Use the dynamically selected prompt
    prompt = get_dynamic_prompt_template(prompt_type)
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
    workflow.add_node("classifier", classifier_node)
    workflow.add_node("agent", conflict_resolution_agent)
    workflow.add_node("tools", call_tools)

    # Set entry point to classifier
    workflow.set_entry_point("classifier")
    
    # Classifier always goes to agent
    workflow.add_edge("classifier", "agent")

    # Add conditional edges from agent
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

def set_prompt(prompt_name: str):
    """Set the prompt to use for the agent.
    
    Args:
        prompt_name: Name of the prompt file (without .txt extension)
    """
    global CURRENT_PROMPT_NAME, USE_CLASSIFICATION
    # Verify the prompt exists
    load_system_prompt(prompt_name)  # Will raise error if not found
    CURRENT_PROMPT_NAME = prompt_name
    USE_CLASSIFICATION = False  # Disable classification when prompt is explicitly set
    print(f"✓ Agent prompt set to: {prompt_name}")

def enable_classification():
    """Enable automatic conversation classification."""
    global USE_CLASSIFICATION
    USE_CLASSIFICATION = True
    print(f"✓ Automatic classification enabled")