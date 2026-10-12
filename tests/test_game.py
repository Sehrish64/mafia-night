import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import Game, MAX_PLAYERS, MIN_PLAYERS, Phase, Role, role_counts


def make_game(n=6, seed=1):
    g = Game(random.Random(seed))
    for i in range(1, n + 1):
        g.add_player(i, f"p{i}")
    g.start()
    return g


def test_role_counts_add_up():
    for n in range(MIN_PLAYERS, MAX_PLAYERS + 1):
        counts = role_counts(n)
        assert sum(counts.values()) == n
        assert counts[Role.MAFIA] >= 1
        assert counts[Role.VILLAGER] >= 0


def test_need_minimum_players():
    g = Game()
    for i in range(MIN_PLAYERS - 1):
        g.add_player(i, "x")
    try:
        g.start()
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_no_double_join_and_no_join_after_start():
    g = make_game()
    assert not g.add_player(99, "late")
    g2 = Game()
    assert g2.add_player(1, "a")
    assert not g2.add_player(1, "a")


def test_mafia_kill_and_doctor_save():
    g = make_game(6)
    mafia = g.alive(Role.MAFIA)[0]
    doctor = g.alive(Role.DOCTOR)[0]
    victim = [p for p in g.alive() if p.role != Role.MAFIA][0]

    assert g.submit_night_action(mafia.id, victim.id)
    assert g.submit_night_action(doctor.id, victim.id)
    result = g.resolve_night()
    assert result.saved and result.killed is None and victim.alive

    g.begin_night()
    assert g.submit_night_action(mafia.id, victim.id)
    result = g.resolve_night()
    assert result.killed is victim and not victim.alive


def test_mafia_cannot_target_mafia():
    g = make_game(9)
    mafia = g.alive(Role.MAFIA)
    assert not g.submit_night_action(mafia[0].id, mafia[1].id)


def test_detective_result():
    g = make_game(6)
    det = g.alive(Role.DETECTIVE)[0]
    mafia = g.alive(Role.MAFIA)[0]
    g.submit_night_action(det.id, mafia.id)
    _, target, is_mafia = g.resolve_night().investigation
    assert target is mafia and is_mafia


def test_day_tie_eliminates_nobody():
    g = make_game(6)
    g.begin_day()
    ids = [p.id for p in g.alive()]
    g.cast_vote(ids[0], ids[1])
    g.cast_vote(ids[1], ids[0])
    assert g.resolve_day() is None


def test_day_majority_eliminates():
    g = make_game(6)
    g.begin_day()
    ids = [p.id for p in g.alive()]
    for voter in ids[:3]:
        g.cast_vote(voter, ids[5])
    victim = g.resolve_day()
    assert victim.id == ids[5] and not victim.alive


def test_dead_players_cannot_vote():
    g = make_game(6)
    g.players[1].alive = False
    g.begin_day()
    assert not g.cast_vote(1, 2)


def test_win_conditions():
    g = make_game(6)
    for m in g.alive(Role.MAFIA):
        m.alive = False
    assert g.winner() == "Town"

    g = make_game(6)
    others = [p for p in g.alive() if p.role != Role.MAFIA]
    for p in others[: len(others) - len(g.alive(Role.MAFIA))]:
        p.alive = False
    assert g.winner() == "Mafia"


def test_random_games_always_finish():
    """Bots play random games: every game must end with a winner."""
    for n in range(MIN_PLAYERS, 16):
        for seed in range(30):
            rng = random.Random(seed)
            g = Game(rng)
            for i in range(n):
                g.add_player(i, f"p{i}")
            g.start()
            for _ in range(60):
                for p in g.alive():
                    targets = g.targets_for(p.id)
                    if targets:
                        g.submit_night_action(p.id, rng.choice(targets).id)
                assert g.night_complete()
                g.resolve_night()
                if g.winner():
                    break
                g.begin_day()
                alive = g.alive()
                for p in alive:
                    g.cast_vote(p.id, rng.choice([a.id for a in alive] + [None]))
                assert g.day_complete()
                g.resolve_day()
                if g.winner():
                    break
                g.begin_night()
            assert g.winner() in ("Town", "Mafia"), f"no winner n={n} seed={seed}"


if __name__ == "__main__":
    # run without pytest: python tests/test_game.py
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
