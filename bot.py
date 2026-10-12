"""Mafia Night: play Mafia / Werewolf inside any Discord server."""
import asyncio
import logging
import os

import discord
from discord import app_commands
from dotenv import load_dotenv

from game import MAX_PLAYERS, MIN_PLAYERS, ROLE_BLURB, Game, Phase, Role, role_counts

load_dotenv()

NIGHT_SECONDS = int(os.getenv("NIGHT_SECONDS", 45))
DISCUSS_SECONDS = int(os.getenv("DISCUSS_SECONDS", 90))
VOTE_SECONDS = int(os.getenv("VOTE_SECONDS", 45))
LOBBY_TIMEOUT = 600

log = logging.getLogger("mafia-night")
sessions: dict = {}  # channel_id -> Session


# ======================================================================
# Night: private dropdown sent by DM
# ======================================================================
class NightSelect(discord.ui.Select):
    def __init__(self, session, actor_id, verb):
        game = session.game
        options = [discord.SelectOption(label=p.name[:100], value=str(p.id)) for p in game.targets_for(actor_id)]
        super().__init__(placeholder=f"Pick who to {verb}...", options=options)
        self.session = session
        self.actor_id = actor_id

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        game = self.session.game
        if not game.submit_night_action(self.actor_id, target_id):
            await interaction.response.send_message("That choice isn't allowed right now.", ephemeral=True)
            return
        name = game.players[target_id].name
        await interaction.response.edit_message(content=f"✅ You chose **{name}**. You can change it until time runs out.")
        if game.night_complete():
            self.session.night_done.set()


class NightView(discord.ui.View):
    def __init__(self, session, actor_id, verb):
        super().__init__(timeout=NIGHT_SECONDS + 5)
        self.add_item(NightSelect(session, actor_id, verb))


# ======================================================================
# Day: public vote dropdown
# ======================================================================
class VoteSelect(discord.ui.Select):
    def __init__(self, session):
        game = session.game
        options = [discord.SelectOption(label=p.name[:100], value=str(p.id)) for p in game.alive()]
        options.append(discord.SelectOption(label="Skip vote", value="0", emoji="⏭️"))
        super().__init__(placeholder="Vote to eliminate someone...", options=options)
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        game = self.session.game
        raw = int(self.values[0])
        target = None if raw == 0 else raw
        if not game.cast_vote(interaction.user.id, target):
            await interaction.response.send_message("Only living players can vote.", ephemeral=True)
            return
        who = "skip" if target is None else game.players[target].name
        await interaction.response.send_message(f"🗳️ Vote saved: **{who}**. You can change it until time runs out.", ephemeral=True)
        if game.day_complete():
            self.session.vote_done.set()


class VoteView(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=VOTE_SECONDS + 5)
        self.add_item(VoteSelect(session))


# ======================================================================
# Lobby
# ======================================================================
class LobbyView(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=LOBBY_TIMEOUT)
        self.session = session

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green, emoji="🎮")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        user = interaction.user
        if not s.game.add_player(user.id, user.display_name):
            await interaction.response.send_message("You're already in, or the lobby is full.", ephemeral=True)
            return
        s.users[user.id] = user
        await interaction.response.edit_message(embed=s.lobby_embed(), view=self)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.grey)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if interaction.user.id == s.host.id:
            await interaction.response.send_message("The host can't leave. Use /mafia-end to cancel.", ephemeral=True)
            return
        if not s.game.remove_player(interaction.user.id):
            await interaction.response.send_message("You aren't in the lobby.", ephemeral=True)
            return
        s.users.pop(interaction.user.id, None)
        await interaction.response.edit_message(embed=s.lobby_embed(), view=self)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.blurple, emoji="▶️")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if interaction.user.id != s.host.id:
            await interaction.response.send_message("Only the host can start the game.", ephemeral=True)
            return
        if len(s.game.players) < MIN_PLAYERS:
            await interaction.response.send_message(f"Need at least {MIN_PLAYERS} players.", ephemeral=True)
            return
        s.started = True
        self.stop()
        await interaction.response.edit_message(embed=s.lobby_embed(starting=True), view=None)
        s.task = asyncio.create_task(s.run())

    async def on_timeout(self):
        s = self.session
        if not s.started:
            sessions.pop(s.channel.id, None)
            try:
                await s.lobby_message.edit(content="⌛ Lobby closed because nobody started the game.", embed=None, view=None)
            except discord.HTTPException:
                pass


# ======================================================================
# One game in one channel
# ======================================================================
class Session:
    def __init__(self, channel, host):
        self.channel = channel
        self.host = host
        self.game = Game()
        self.users = {host.id: host}
        self.game.add_player(host.id, host.display_name)
        self.started = False
        self.lobby_message = None
        self.lobby_view = None
        self.task = None
        self.night_done = asyncio.Event()
        self.vote_done = asyncio.Event()

    def lobby_embed(self, starting=False):
        names = "\n".join(f"• {p.name}" for p in self.game.players.values())
        e = discord.Embed(
            title="🌙 Mafia Night" if not starting else "🌙 Mafia Night: starting!",
            description=f"Host: **{self.host.display_name}**\n\n**Players ({len(self.game.players)}/{MAX_PLAYERS}):**\n{names}",
            color=0x5865F2,
        )
        e.set_footer(text=f"Need {MIN_PLAYERS}+ players. Roles are sent by DM, so keep your DMs open!")
        return e

    async def run(self):
        try:
            if not await self.send_roles():
                return
            while True:
                await self.night()
                if self.game.winner():
                    break
                await self.day()
                if self.game.winner():
                    break
                self.game.begin_night()
            await self.finish()
        except Exception:
            log.exception("Game crashed")
            await self.channel.send("⚠️ Something went wrong and the game had to stop.")
        finally:
            self.game.phase = Phase.OVER
            sessions.pop(self.channel.id, None)

    async def send_roles(self) -> bool:
        self.game.start()
        mafia_names = ", ".join(p.name for p in self.game.alive(Role.MAFIA))
        failed = []
        for p in self.game.players.values():
            text = ROLE_BLURB[p.role]
            if p.role == Role.MAFIA:
                text += f"\n\nMafia team: **{mafia_names}**"
            try:
                await self.users[p.id].send(text)
            except discord.HTTPException:
                failed.append(p.name)
        if failed:
            await self.channel.send(
                f"❌ I couldn't DM: **{', '.join(failed)}**. Turn on *Direct Messages* from server members "
                f"(Server name → Privacy Settings), then use /mafia to try again."
            )
            return False
        counts = role_counts(len(self.game.players))
        await self.channel.send(
            f"🎭 Roles sent by DM! **{counts[Role.MAFIA]}** Mafia, 1 Doctor, 1 Detective, "
            f"{counts[Role.VILLAGER]} Villager(s). Night falls..."
        )
        return True

    async def night(self):
        g = self.game
        self.night_done.clear()
        await self.channel.send(f"🌙 **Night {g.night_number}.** Everyone sleeps. If you have a night role, check your DMs. ({NIGHT_SECONDS}s)")
        verbs = {Role.MAFIA: "eliminate", Role.DOCTOR: "protect", Role.DETECTIVE: "investigate"}
        for p in g.alive():
            if p.role in verbs:
                try:
                    await self.users[p.id].send(f"🌙 Night {g.night_number}: choose.", view=NightView(self, p.id, verbs[p.role]))
                except discord.HTTPException:
                    pass
        try:
            await asyncio.wait_for(self.night_done.wait(), timeout=NIGHT_SECONDS)
        except asyncio.TimeoutError:
            pass

        result = g.resolve_night()
        if result.investigation:
            detective, target, is_mafia = result.investigation
            verdict = "🔪 **MAFIA**" if is_mafia else "✅ **not Mafia**"
            try:
                await self.users[detective.id].send(f"🔍 **{target.name}** is {verdict}.")
            except discord.HTTPException:
                pass
        if result.killed:
            await self.channel.send(f"☀️ Morning! **{result.killed.name}** was eliminated in the night. They were **{result.killed.role.value}**.")
        else:
            await self.channel.send("☀️ Morning! Nobody died last night.")

    async def day(self):
        g = self.game
        if g.winner():
            return
        g.begin_day()
        self.vote_done.clear()
        alive = ", ".join(p.name for p in g.alive())
        await self.channel.send(f"💬 **Day {g.night_number}.** Alive: {alive}\nDiscuss for {DISCUSS_SECONDS}s. Who is the Mafia?")
        await asyncio.sleep(DISCUSS_SECONDS)
        await self.channel.send(f"🗳️ **Time to vote!** You have {VOTE_SECONDS}s.", view=VoteView(self))
        try:
            await asyncio.wait_for(self.vote_done.wait(), timeout=VOTE_SECONDS)
        except asyncio.TimeoutError:
            pass
        victim = g.resolve_day()
        if victim:
            await self.channel.send(f"⚖️ The town eliminated **{victim.name}**. They were **{victim.role.value}**.")
        else:
            await self.channel.send("⚖️ The vote was tied or skipped, so nobody was eliminated.")

    async def finish(self):
        winner = self.game.winner()
        reveal = "\n".join(f"• {p.name}: {p.role.value}{'' if p.alive else ' 💀'}" for p in self.game.players.values())
        icon = "🏘️" if winner == "Town" else "🔪"
        await self.channel.send(f"{icon} **{winner} wins!**\n\n**Roles:**\n{reveal}\n\nUse /mafia to play again.")


# ======================================================================
# Bot + slash commands
# ======================================================================
class MafiaBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        dev_guild = os.getenv("DEV_GUILD_ID")
        if dev_guild:  # instant command updates while developing
            guild = discord.Object(id=int(dev_guild))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        log.info("Logged in as %s", self.user)


bot = MafiaBot()


@bot.tree.command(name="mafia", description="Start a game of Mafia in this channel")
@app_commands.guild_only()
async def mafia(interaction: discord.Interaction):
    if interaction.channel_id in sessions:
        await interaction.response.send_message("A game is already running in this channel.", ephemeral=True)
        return
    session = Session(interaction.channel, interaction.user)
    sessions[interaction.channel_id] = session
    view = LobbyView(session)
    session.lobby_view = view
    await interaction.response.send_message(embed=session.lobby_embed(), view=view)
    session.lobby_message = await interaction.original_response()


@bot.tree.command(name="mafia-rules", description="How to play")
async def mafia_rules(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**How Mafia works**\n"
        "• Everyone gets a secret role by DM.\n"
        "• 🌙 **Night:** Mafia picks a victim, the Doctor protects someone, the Detective checks someone.\n"
        "• ☀️ **Day:** Everyone discusses, then votes to eliminate a suspect.\n"
        "• 🏘️ **Town wins** when all Mafia are gone. 🔪 **Mafia wins** when they equal or outnumber the rest.",
        ephemeral=True,
    )


@bot.tree.command(name="mafia-end", description="Cancel the game in this channel (host or moderators)")
@app_commands.guild_only()
async def mafia_end(interaction: discord.Interaction):
    session = sessions.get(interaction.channel_id)
    if not session:
        await interaction.response.send_message("No game is running here.", ephemeral=True)
        return
    is_mod = interaction.permissions.manage_messages
    if interaction.user.id != session.host.id and not is_mod:
        await interaction.response.send_message("Only the host or a moderator can end the game.", ephemeral=True)
        return
    if session.task:
        session.task.cancel()
    if session.lobby_view and not session.started:
        # Kill the lobby buttons too, or the host could start an orphaned game.
        session.lobby_view.stop()
        if session.lobby_message:
            try:
                await session.lobby_message.edit(content="🛑 Game cancelled.", embed=None, view=None)
            except discord.HTTPException:
                pass
    sessions.pop(interaction.channel_id, None)
    await interaction.response.send_message("🛑 Game ended.")


def main():
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Missing DISCORD_TOKEN. Copy .env.example to .env and paste your bot token.")
    bot.run(token)


if __name__ == "__main__":
    main()
