### slack:
This tool sends Slack messages to channels or DMs using Slack Web API.

Set bot token with `SLACK_BOT_TOKEN` (recommended) or pass `token` in tool args.

#### Methods
1. `slack:post_message`
Send a message to a channel.
- `channel` (string, required): channel ID (for example `C0123456789`) or channel name supported by your workspace.
- `text` (string, required): message text.
- `thread_ts` (string, optional): reply in thread.

2. `slack:post_dm`
Send a direct message to a user.
- `user` (string, optional): Slack user ID (for example `U0123456789`).
- `email` (string, optional): used when `user` is not provided.
- `text` (string, required): message text.

3. `slack:list_channels`
List channels visible to the bot.
- `limit` (int, optional, default 20, max 200)
- `types` (string, optional, default `public_channel,private_channel`)
- `exclude_archived` (bool, optional, default true)

#### Usage example
```json
{
  "thoughts": ["I should notify the user in Slack."],
  "tool_name": "slack:post_dm",
  "tool_args": {
    "email": "user@example.com",
    "text": "Deployment passed. Temporal smoke test is green."
  }
}
```
