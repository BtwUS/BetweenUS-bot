# BetweenUS-bot

**An active AI mediator that solves workplace miscommunication by treating it with the right medicine.**

## The Problem
Workplace conflict costs organizations hundreds of billions annually through lost productivity, project failures, and turnover. The root cause: **miscommunication**. Current tools fail because they're passive and one-size-fits-all—unable to distinguish between technical disputes (engineering arguments) and emotional-relational conflicts (trust breakdowns). Without understanding intent, they can't deliver the right solution.

## The Solution
**BetweenUS** is a multi-agentic Symmetry Mediator living inside Slack—not a chatbot, but an orchestrated two-stage system:

**Stage 1: Triage & Investigation**  
A Triage Agent pulls Slack history and user context to analyze the conflict's root:
- Hidden common goals?
- Researchable factual problem?
- Technical/logical oversight?
- Missing third solution?

**Stage 2: Adaptive Response**  
A Response Agent routes findings to specialized models:
- **Emotional conflicts** → empathetic reflection building human trust
- **Technical conflicts** → objective, data-driven insights solving actual problems

**Result:** Context-specific interventions that identify conflict roots (Fact vs. Emotion), deliver human-centric warmth for relational issues or actionable insights for technical disputes, and surface the "better third solution" teams in conflict miss—turning friction into progress.

## Features

- 🔍 **Analyzes Slack conversations** to identify conflict dynamics
- 🤝 **Finds common ground** between conflicting parties
- 💡 **Suggests reframing** to help teams understand problems better
- 🗣️ **Provides communication tips** with specific "instead of saying..." examples
- 🤖 **Uses ReAct reasoning** (Thought → Action → Observation → Synthesis)

## Project Structure

```
BetweenUS-bot/
├── agent.py              # LangGraph conflict analyst agent
├── app.py                # Slack bot application
├── prompts/              # System prompts directory
│   ├── conflict_analyst_prompt.txt
│   └── README.md
├── tools/                # Agent tools package
│   ├── __init__.py
│   ├── slack_tools.py    # Slack API tools
│   └── search_tools.py   # Google search tool
├── requirements.txt      # Python dependencies
└── test_analyst.py       # Test script
```

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your `.env` file with:
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
GROQ_API_KEY=...
GOOGLE_API_KEY=...
GOOGLE_CSE_ID=...
```

3. Run the bot:
```bash
python app.py
```

## Usage

Mention the bot in Slack:
```
@BetweenUS analyze the discussion in #engineering

@BetweenUS help us understand channel C0123ABC
```

## Output Format

The bot provides structured, actionable responses:

**📊 What's happening:** [Neutral conflict summary]

**🤝 Common ground:** [Shared goals]

**💡 To better understand this:** [Reframing suggestions]

**🗣️ Instead of saying:** [Communication improvements]

## Customizing

To modify the bot's behavior, edit `prompts/conflict_analyst_prompt.txt` and restart the bot.

See `PROMPT_CHANGES.md` for detailed documentation on the prompt system.

## Testing

Run tests with:
```bash
python test_analyst.py
```
