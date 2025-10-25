# Prompts Directory

This directory contains the system prompts used by the BetweenUS Slack Conflict Analyst bot.

## Files

### `conflict_analyst_prompt.txt`
The main system prompt that defines the bot's behavior, personality, and output format.

**Usage:** This prompt is loaded automatically by `agent.py` when the bot starts.

**Structure:**
- **Role & Objective**: Defines the bot as a Slack Conflict Analyst
- **Core Principles**: Multi-Intent analysis, conflict classification, common ground finding
- **Available Tools**: Lists the tools the bot can use
- **ReAct Analysis Flow**: Explains the reasoning pattern
- **Output Format**: Specifies the 4-part structured response format

## Modifying Prompts

To change the bot's behavior:

1. Edit `conflict_analyst_prompt.txt` directly
2. Restart the bot (the prompt is loaded on startup)
3. Test with `python test_analyst.py` to verify behavior

## Output Format

The bot produces responses with 4 sections:
- 📊 **What's happening** - Neutral conflict summary
- 🤝 **Common ground** - Shared goals
- 💡 **To better understand this** - Reframing suggestions
- 🗣️ **Instead of saying** - Communication improvements

## Tips for Editing

- Keep the tone **warm but neutral**
- Focus on **actionable advice**, not just analysis
- Maintain the structured output format for consistency
- Test changes with various conflict scenarios
- Use examples to illustrate the expected behavior
