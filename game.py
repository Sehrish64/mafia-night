"""Pure Mafia game logic. No Discord code in here, so it is easy to test."""
import random
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Optional

MIN_PLAYERS = 4
MAX_PLAYERS = 20


class Role(str, Enum):
    MAFIA = "Mafia"
    DOCTOR = "Doctor"
    DETECTIVE = "Detective"
    VILLAGER = "Villager"


class Phase(str, Enum):
    LOBBY = "lobby"
    NIGHT = "night"
    DAY = "day"
    OVER = "over"


ROLE_BLURB = {
    Role.MAFIA: "🔪 You are **Mafia**. Each night, pick someone to eliminate. Stay hidden during the day!",
    Role.DOCTOR: "💉 You are the **Doctor**. Each night, pick one person to protect from the Mafia (you can pick yourself).",
    Role.DETECTIVE: "🔍 You are the **Detective**. Each night, check one person to learn if they are Mafia.",
    Role.VILLAGER: "🏘️ You are a **Villager**. You have no night power, so use your brain and vote out the Mafia!",
}


@dataclass
class Player:
    id: int
    name: str
    role: Optional[Role] = None
    alive: bool = True


@dataclass
class NightResult:
    killed: Optional[Player]
    saved: bool
    investigation: Optional[tuple]  # (detective, target, is_mafia)


def role_counts(n: int) -> dict:
    """How many of each role for n players."""
    mafia = max(1, n // 3)
    doctor = 1
    detective = 1
    villagers = n - mafia - doctor - detective
    return {Role.MAFIA: mafia, Role.DOCTOR: doctor, Role.DETECTIVE: detective, Role.VILLAGER: villagers}


class Game:
    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()
        self.players: dict = {}
        self.phase = Phase.LOBBY
        self.night_number = 0
        self.kill_votes: dict = {}
        self.save_target: Optional[int] = None
        self.check_target: Optional[int] = None
        self.day_votes: dict = {}

    # ---------- lobby ----------
    def add_player(self, pid: int, name: str) -> bool:
        if self.phase != Phase.LOBBY or pid in self.players or len(self.players) >= MAX_PLAYERS:
            return False
        self.players[pid] = Player(pid, name)
        return True

    def remove_player(self, pid: int) -> bool:
        if self.phase != Phase.LOBBY:
            return False
        return self.players.pop(pid, None) is not None

    def start(self) -> None:
        if len(self.players) < MIN_PLAYERS:
            raise ValueError(f"Need at least {MIN_PLAYERS} players.")
        roles = []
        for role, count in role_counts(len(self.players)).items():
            roles += [role] * count
        self.rng.shuffle(roles)
        for player, role in zip(self.players.values(), roles):
            player.role = role
        self.begin_night()

    # ---------- helpers ----------
    def alive(self, role: Optional[Role] = None) -> list:
        return [p for p in self.players.values() if p.alive and (role is None or p.role == role)]

    def is_alive(self, pid: int) -> bool:
        p = self.players.get(pid)
        return bool(p and p.alive)

    def targets_for(self, pid: int) -> list:
        """Who this player may pick tonight."""
        me = self.players[pid]
        if me.role == Role.MAFIA:
            return [p for p in self.alive() if p.role != Role.MAFIA]
        if me.role == Role.DOCTOR:
            return self.alive()
        if me.role == Role.DETECTIVE:
            return [p for p in self.alive() if p.id != pid]
        return []

    # ---------- night ----------
    def begin_night(self) -> None:
        self.phase = Phase.NIGHT
        self.night_number += 1
        self.kill_votes = {}
        self.save_target = None
        self.check_target = None

    def submit_night_action(self, pid: int, target_id: int) -> bool:
        if self.phase != Phase.NIGHT or not self.is_alive(pid):
            return False
        if target_id not in [p.id for p in self.targets_for(pid)]:
            return False
        role = self.players[pid].role
        if role == Role.MAFIA:
            self.kill_votes[pid] = target_id
        elif role == Role.DOCTOR:
            self.save_target = target_id
        elif role == Role.DETECTIVE:
            self.check_target = target_id
        else:
            return False
        return True

    def night_complete(self) -> bool:
        if any(m.id not in self.kill_votes for m in self.alive(Role.MAFIA)):
            return False
        if self.alive(Role.DOCTOR) and self.save_target is None:
            return False
        if self.alive(Role.DETECTIVE) and self.check_target is None:
            return False
        return True

    def resolve_night(self) -> NightResult:
        victim = None
        if self.kill_votes:
            counts = Counter(self.kill_votes.values())
            top = max(counts.values())
            victim = self.players[self.rng.choice([t for t, c in counts.items() if c == top])]

        saved = victim is not None and victim.id == self.save_target
        killed = None
        if victim and not saved:
            victim.alive = False
            killed = victim

        investigation = None
        detective = next(iter(self.alive(Role.DETECTIVE)), None)
        if detective and self.check_target is not None:
            target = self.players[self.check_target]
            investigation = (detective, target, target.role == Role.MAFIA)

        return NightResult(killed, saved, investigation)

    # ---------- day ----------
    def begin_day(self) -> None:
        self.phase = Phase.DAY
        self.day_votes = {}

    def cast_vote(self, voter: int, target_id: Optional[int]) -> bool:
        """target_id None = skip vote."""
        if self.phase != Phase.DAY or not self.is_alive(voter):
            return False
        if target_id is not None and not self.is_alive(target_id):
            return False
        self.day_votes[voter] = target_id
        return True

    def day_complete(self) -> bool:
        return all(p.id in self.day_votes for p in self.alive())

    def tally(self) -> Counter:
        return Counter(t for t in self.day_votes.values() if t is not None)

    def resolve_day(self) -> Optional[Player]:
        """Eliminate the most-voted player. A tie (or no votes) eliminates nobody."""
        counts = self.tally()
        if not counts:
            return None
        ranked = counts.most_common()
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            return None
        victim = self.players[ranked[0][0]]
        victim.alive = False
        return victim

    # ---------- win check ----------
    def winner(self) -> Optional[str]:
        mafia = len(self.alive(Role.MAFIA))
        others = len(self.alive()) - mafia
        if mafia == 0:
            return "Town"
        if mafia >= others:
            return "Mafia"
        return None
