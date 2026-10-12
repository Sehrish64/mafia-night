# 🌙 Mafia Night

**Play Mafia / Werewolf inside any Discord server.** Secret roles by DM, night and day rounds, and dropdown voting. Just type `/mafia`.

> 📽️ Add your demo GIF here: `![demo](demo.gif)`

## How a game works

1. Someone types `/mafia`. Players click **Join**, and the host clicks **Start** (4 to 20 players).
2. Everyone gets a secret role by DM:
   - 🔪 **Mafia**: eliminates someone each night
   - 💉 **Doctor**: protects one person each night
   - 🔍 **Detective**: checks if one person is Mafia
   - 🏘️ **Villager**: no power, only brains
3. 🌙 **Night:** people with powers pick a target from a private dropdown in their DMs.
4. ☀️ **Day:** the town sees who died, discusses, and votes in the channel.
5. 🏘️ **Town wins** when all Mafia are gone. 🔪 **Mafia wins** when they equal or outnumber everyone else.

## Commands

| Command | What it does |
|---|---|
| `/mafia` | Open a lobby in this channel |
| `/mafia-rules` | Show the rules (only you see it) |
| `/mafia-end` | Cancel the game (host or moderators) |

## Set it up (free, about 5 minutes)

You need **Python 3.10+**.

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. Open **Bot** → **Reset Token** → copy the token. (No privileged intents are needed.)
3. Open **OAuth2 → URL Generator**. Tick the scopes `bot` and `applications.commands`, and the permissions *View Channels*, *Send Messages* and *Embed Links*. Open the generated link to add the bot to your server.
4. Run:

```bash
git clone https://github.com/Sehrish64/mafia-night
cd mafia-night
pip install -r requirements.txt
cp .env.example .env     # then paste your token into .env
python bot.py
```

5. In your server, type `/mafia`. 🎉

> **Tip:** players must allow *Direct Messages from server members* (Server name → Privacy Settings), or the bot can't send their roles. Set `DEV_GUILD_ID` in `.env` to see slash commands instantly while testing.

## Settings (`.env`)

| Variable | Meaning | Default |
|---|---|---|
| `DISCORD_TOKEN` | Your bot token | required |
| `DEV_GUILD_ID` | Test server ID for instant commands | off |
| `NIGHT_SECONDS` | Time for night actions | 45 |
| `DISCUSS_SECONDS` | Day discussion time | 90 |
| `VOTE_SECONDS` | Voting time | 45 |

## Run the tests

```bash
python tests/test_game.py
```

The game rules live in `game.py` with no Discord code, so they're easy to test and easy to extend.

## Roadmap

- [ ] 🃏 More roles (Jester, Sheriff, Bodyguard)
- [ ] 🌍 Language packs (Roman Urdu, Hinglish, Spanish...)
- [ ] 🏆 Win/loss leaderboard per server
- [ ] 🎨 Themes (Werewolf, Among Us, Pirates)
- [ ] 🐳 One-click deploy button

Ideas and pull requests are welcome!

## License

MIT
