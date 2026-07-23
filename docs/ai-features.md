# AI features

SQ can borrow a large language model for planning help; here is how to switch it on and what it does for you.

All of it is optional. Without a provider configured, SQ simply keeps the AI buttons out of sight and works exactly the same otherwise.

## Connecting a provider

Go to Settings, then AI Assist. Pick a provider, paste its API key (or, for Ollama, the server URL), and save. Google Gemini is the default; Anthropic, OpenAI, and a local Ollama server also work. The Model field can stay blank to use a sensible default per provider:

| Provider | Needs | Default model |
|---|---|---|
| gemini | API key | gemini-2.5-flash |
| anthropic | API key | claude-haiku-4-5-20251001 |
| openai | API key | gpt-4o-mini |
| ollama | Server URL (default http://localhost:11434) | llama3.2 |

A saved key stays put when its field is left blank, so you can revisit the pane and save other changes without re-entering secrets; fields with a stored key say "(saved)" and "leave blank to keep".

Press Test to send a tiny round trip to your provider. It reports which provider answered, or the exact error if something is off, so you know the keys work before you rely on them.

Prefer configuration by environment? `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_URL`, `TRACKER_LLM_PROVIDER`, and `TRACKER_LLM_MODEL` override anything saved on the page.

## Assist buttons on cards

Open any card and three buttons appear beneath its fields:

- **AI: break into subtasks** asks for 3 to 8 concrete subtasks and creates them as real child cards under the one you are on. Subtasks you already have are not duplicated.
- **AI: draft description** writes a short, clear description onto the card: what needs to happen and what done looks like.
- **AI: research approaches** thinks through ways to get the task done: two or three approaches with tradeoffs, a suggested step-by-step plan, pitfalls to watch for, and (for hands-on tasks) tools and materials. The notes open in a dialog to review first; append them to the card or copy them out.

## Plan my day

The Plan my day button lives on the Today rail beside every board. It gathers your open cards from active projects that are not already on the list, hands them to the AI with their due dates and priorities, and asks it to pick the 3 to 6 that most deserve attention today, preferring overdue work, then due-soon, then high priority, mixing projects when sensible. The picks land straight on the Today list, so they show up on your wall displays too. If the rail is showing your personal list rather than the shared one, the plan fills that list instead.

## Send to AI

Sometimes you want a bigger brain than a quick assist call, or a conversation. Send to AI, on every card, packs the whole card into one self-contained prompt: title, project, status, priority, due date, labels, description, subtask and checklist progress, and a note of any attached files (the files themselves are not included). From there:

- **Copy prompt** puts the raw prompt on your clipboard for anywhere.
- **Open in Claude** and **Open in ChatGPT** open a new chat with the prompt already in place.
- **Copy for Gemini** copies the prompt and opens Gemini for you to paste (Gemini does not accept a prefilled chat).
- **Copy for Claude Code** copies a ready-to-run `claude "..."` shell command for your terminal.

Send to AI does not use your configured provider at all, so it works even with no AI set up in Settings.

## When the buttons hide

SQ never offers an action that cannot work. Without a configured provider, the three assist buttons and Plan my day stay hidden entirely, and the AI assist line on the Settings overview reads "not set up (optional)". The moment a provider is saved they appear everywhere. Send to AI is the exception: it is always available, since the thinking happens in whichever AI you hand the prompt to.
