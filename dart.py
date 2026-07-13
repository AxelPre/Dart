import pygame
import ast
import importlib.util
import operator as op
from datetime import datetime
from pathlib import Path


PLAYER_IDENTITIES = {
    "*": ("Axel", "StatsAxel.txt"),
    "/": ("Eila", "StatsEila.txt"),
}
STATS_PLAYERS = [
    ("Axel", "StatsAxel.txt"),
    ("Eila", "StatsEila.txt"),
]
CLOCK_TARGETS = list(range(1, 21)) + [25, 50]
X01_GAMES = {"501", "301"}
CHECKOUT_RUN_GAMES = {"checkout121", "checkout61"}
BULLGAME = "bullgame"
STATS_HEADER = """# Dart Score stats format
# x01: YYYY-MM-DD HH:MM;501|301;score_per_round;D<double_attempts>;C<checkout_darts>|F
# Clock: YYYY-MM-DD HH:MM;clock;dart_sequence_per_round;C|F
# Clock rounds use 0/1 per dart, e.g. 111,010,001
# Superclock: YYYY-MM-DD HH:MM;superclock;dart_sequence_per_round;C|F
# Superclock rounds use 0/1/2/3 per dart, e.g. 020,103,11
# Bullgame: YYYY-MM-DD HH:MM;bullgame;round_code,...
# Bullgame rounds use three digits: first dart 0/1/2 for miss/25/50.
# If the first dart is 1 or 2, darts two and three use 0/1/2 for miss/25/50.
# If the first dart is 0, dart two is triple 0/1 and dart three is double 0/1.
# Checkout run: YYYY-MM-DD HH:MM;checkout121|checkout61;best_run
# D = double attempts
"""


def load_checkout_suggestions():
    checkout_file = Path(__file__).resolve().parent / "checkouts.py"
    spec = importlib.util.spec_from_file_location("checkouts", checkout_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.CHECKOUTS)


CHECKOUTS = load_checkout_suggestions()

# ---------- Safe math ----------
OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.floordiv,
}

def safe_eval(expr):
    def eval_node(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](eval_node(node.left), eval_node(node.right))
        raise ValueError("Invalid expression")

    return eval_node(ast.parse(expr, mode="eval").body)


def parse_score_input(value):
    value = value.replace(",", ".")

    if "." not in value:
        return safe_eval(value), None

    if value.count(".") != 1:
        raise ValueError("Invalid double attempt suffix")

    score_expression, double_attempts = value.rsplit(".", 1)
    if double_attempts not in "123" or len(double_attempts) != 1:
        raise ValueError("Double attempts must be 1, 2 or 3")

    return safe_eval(score_expression), int(double_attempts)


def format_route(route):
    return " ".join(route)


def suggestion_score(current_score, current_input):
    if not current_input or current_input in PLAYER_IDENTITIES:
        return current_score

    try:
        points, _ = parse_score_input(current_input)
    except Exception:
        return None

    remaining = current_score - points
    if remaining < 0:
        return None

    return remaining


def winner_darts(game, final_darts):
    winner = game.players[game.winner_index]
    return max(0, (len(winner.throws) - 1) * 3 + final_darts)


def game_over_summary(game, selected_game, final_darts):
    if selected_game in CHECKOUT_RUN_GAMES:
        return f"Best run: {game.best_run_summary()}"

    total_darts = winner_darts(game, final_darts)

    if selected_game in X01_GAMES:
        average = game.start_score / total_darts * 3 if total_darts else 0
        return f"{total_darts} darts  Average: {average:.2f}"

    return f"{total_darts} darts"


def percent(hits, attempts):
    return hits / attempts * 100 if attempts else 0


def exact_clock_segments(rounds):
    darts = "".join(rounds)
    segment_attempts = 0
    segment_hits = 0
    twenty_five_attempts = 0
    twenty_five_hits = 0
    bull_attempts = 0
    bull_hits = 0
    completed_segments = 0

    for dart in darts:
        if completed_segments < 20:
            segment_attempts += 1
            if dart == "1":
                segment_hits += 1
                completed_segments += 1
        elif completed_segments == 20:
            twenty_five_attempts += 1
            if dart == "1":
                twenty_five_hits += 1
                completed_segments += 1
        elif completed_segments == 21:
            bull_attempts += 1
            if dart == "1":
                bull_hits += 1
                completed_segments += 1
        else:
            break

    return {
        "segment_attempts": segment_attempts,
        "segment_hits": segment_hits,
        "twenty_five_attempts": twenty_five_attempts,
        "twenty_five_hits": twenty_five_hits,
        "bull_attempts": bull_attempts,
        "bull_hits": bull_hits,
    }


def exact_superclock_segments(rounds):
    darts = "".join(rounds)
    segment_attempts = 0
    segment_hits = 0
    twenty_five_attempts = 0
    twenty_five_hits = 0
    bull_attempts = 0
    bull_hits = 0
    target_index = 0

    for dart in darts:
        value = int(dart)

        if target_index < 20:
            segment_attempts += 1
            if value:
                segment_hits += 1
                target_index = min(21, target_index + value)
        elif target_index == 20:
            if value > 1:
                return None
            twenty_five_attempts += 1
            if value == 1:
                twenty_five_hits += 1
                target_index = 21
        elif target_index == 21:
            if value > 1:
                return None
            bull_attempts += 1
            if value == 1:
                bull_hits += 1
                target_index = len(CLOCK_TARGETS)
        else:
            break

    return {
        "segment_attempts": segment_attempts,
        "segment_hits": segment_hits,
        "twenty_five_attempts": twenty_five_attempts,
        "twenty_five_hits": twenty_five_hits,
        "bull_attempts": bull_attempts,
        "bull_hits": bull_hits,
    }


def aggregate_clock_stats(legs):
    wins = [leg for leg in legs if leg["completed"]]
    segment_attempts = sum(
        leg["segment_stats"]["segment_attempts"]
        for leg in legs
        if leg["segment_stats"]
    )
    segment_hits = sum(
        leg["segment_stats"]["segment_hits"]
        for leg in legs
        if leg["segment_stats"]
    )
    twenty_five_attempts = sum(
        leg["segment_stats"]["twenty_five_attempts"]
        for leg in legs
        if leg["segment_stats"]
    )
    twenty_five_hits = sum(
        leg["segment_stats"]["twenty_five_hits"]
        for leg in legs
        if leg["segment_stats"]
    )
    bull_attempts = sum(
        leg["segment_stats"]["bull_attempts"]
        for leg in legs
        if leg["segment_stats"]
    )
    bull_hits = sum(
        leg["segment_stats"]["bull_hits"]
        for leg in legs
        if leg["segment_stats"]
    )

    return {
        "legs": len(legs),
        "wins": len(wins),
        "losses": len(legs) - len(wins),
        "win_percent": len(wins) / len(legs) * 100 if legs else 0,
        "average_darts": (
            sum(leg["darts"] for leg in wins) / len(wins)
            if wins else 0
        ),
        "best": min((leg["darts"] for leg in wins), default=0),
        "segment_percent": percent(segment_hits, segment_attempts),
        "twenty_five_percent": percent(twenty_five_hits, twenty_five_attempts),
        "bull_percent": percent(bull_hits, bull_attempts),
    }


def bullgame_round_stats(rounds):
    bull_attempts = 0
    bull_hits = 0
    fifty_hits = 0
    triple_attempts = 0
    triple_hits = 0
    double_attempts = 0
    double_hits = 0

    for code in rounds:
        first, second, third = code
        bull_attempts += 1
        if first in "12":
            bull_hits += 1
            fifty_hits += first == "2"
            bull_attempts += 2
            bull_hits += (second in "12") + (third in "12")
            fifty_hits += (second == "2") + (third == "2")
        else:
            triple_attempts += 1
            triple_hits += second == "1"
            double_attempts += 1
            double_hits += third == "1"

    return {
        "bull_attempts": bull_attempts,
        "bull_hits": bull_hits,
        "fifty_hits": fifty_hits,
        "triple_attempts": triple_attempts,
        "triple_hits": triple_hits,
        "double_attempts": double_attempts,
        "double_hits": double_hits,
        "darts": len(rounds) * 3,
    }


def aggregate_bullgame_stats(rounds):
    stats = bullgame_round_stats(rounds)
    return {
        "rounds": len(rounds),
        "bull_percent": percent(stats["bull_hits"], stats["bull_attempts"]),
        "fifty_percent": percent(stats["fifty_hits"], stats["bull_attempts"]),
        "triple_percent": percent(stats["triple_hits"], stats["triple_attempts"]),
        "double_percent": percent(stats["double_hits"], stats["double_attempts"]),
    }


def aggregate_x01_stats(legs):
    wins = [leg for leg in legs if leg["checkout_darts"] is not None]
    all_throws = [points for leg in legs for points in leg["throws"]]
    total_points = sum(all_throws)
    total_darts = sum(leg["darts"] for leg in legs)
    total_double_attempts = sum(leg["double_attempts"] for leg in legs)
    checkouts = [leg["throws"][-1] for leg in wins if leg["throws"]]

    return {
        "legs": len(legs),
        "wins": len(wins),
        "losses": len(legs) - len(wins),
        "win_percent": len(wins) / len(legs) * 100 if legs else 0,
        "three_dart_average": total_points / total_darts * 3 if total_darts else 0,
        "checkout_percent": len(wins) / total_double_attempts * 100 if total_double_attempts else 0,
        "double_attempts": total_double_attempts,
        "score_100_plus": sum(points >= 100 for points in all_throws),
        "score_140_plus": sum(points >= 140 for points in all_throws),
        "score_180": all_throws.count(180),
        "checkout_100_plus": sum(points >= 100 for points in checkouts),
        "highest_checkout": max(checkouts, default=0),
        "best_leg": min((leg["darts"] for leg in wins), default=0),
        "nine_darters": sum(
            leg["start_score"] == 501 and leg["darts"] == 9
            for leg in wins
        ),
        "six_darters": sum(
            leg["start_score"] == 301 and leg["darts"] == 6
            for leg in wins
        ),
    }


def append_stats_line(stats_filename, line):
    stats_path = Path(__file__).resolve().parent / stats_filename

    try:
        existing_text = stats_path.read_text(encoding="utf-8")
    except OSError:
        existing_text = ""

    with stats_path.open("w", encoding="utf-8") as stats_file:
        if not existing_text.startswith("# Dart Score stats format"):
            stats_file.write(STATS_HEADER)
            if existing_text and not existing_text.startswith("\n"):
                stats_file.write("\n")

        stats_file.write(existing_text)
        if existing_text and not existing_text.endswith("\n"):
            stats_file.write("\n")
        stats_file.write(line)


# ---------- Game logic ----------
class Player:
    def __init__(self, name, score=501):
        self.name = name
        self.score = score
        self.stats_file = None
        self.throws = []
        self.double_attempts = []
        self.clock_index = 0
        self.clock_darts = []
        self.checkout_target = score
        self.checkout_best = score
        self.checkout_darts_used = 0
        self.checkout_active = True


class DartGame:
    def __init__(self, names, start_score=501):
        self.players = [Player(name, start_score) for name in names]
        self.start_score = start_score
        self.current = 0
        self.history = []
        self.winner_index = None

    def current_player(self):
        return self.players[self.current]

    def next_player(self):
        self.current = (self.current + 1) % len(self.players)

    def is_legal_move(self, points):
        impossible_scores = {
            179, 178, 176, 175, 173, 172, 169,
            168, 166, 165, 163, 162, 159
        }

        return 0 <= points <= 180 and points not in impossible_scores

    def identify_current_player(self, code):
        name, stats_file = PLAYER_IDENTITIES[code]

        if any(player.stats_file == stats_file for player in self.players):
            return f"{name} is already assigned"

        player = self.current_player()
        player.name = name
        player.stats_file = stats_file
        return f"Player assigned as {name}"

    def add_score(self, points, double_attempts=None):
        player = self.current_player()

        if not self.is_legal_move(points):
            return "Invalid throw"

        old_score = player.score
        old_player = self.current

        if double_attempts is None:
            if points == 0:
                double_attempts = 3
            elif points == player.score:
                double_attempts = 1
            else:
                double_attempts = 0

        if points > player.score or player.score - points == 1:
            player.throws.append(0)
            player.double_attempts.append(double_attempts)
            self.history.append((old_player, old_score, points))
            self.next_player()
            return "Bust!"

        player.score -= points
        player.throws.append(points)
        player.double_attempts.append(double_attempts)
        self.history.append((old_player, old_score, points))

        if player.score == 0:
            self.winner_index = old_player
            return f"{player.name} won!"

        self.next_player()
        return f"{player.name}: {points}"

    def undo(self):
        if not self.history:
            return None

        player_index, old_score, points = self.history.pop()
        self.players[player_index].score = old_score
        self.players[player_index].throws.pop()
        self.players[player_index].double_attempts.pop()
        self.current = player_index
        self.winner_index = None
        return f"Undid {points}"

    def save_completed_leg(self, checkout_darts):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        for player_index, player in enumerate(self.players):
            if not player.stats_file:
                continue

            throws = ",".join(str(points) for points in player.throws)
            double_attempts = sum(player.double_attempts)
            result = f"C{checkout_darts}" if player_index == self.winner_index else "F"
            line = f"{timestamp};{self.start_score};{throws};D{double_attempts};{result}\n"

            append_stats_line(player.stats_file, line)


class CheckoutRunGame:
    def __init__(self, names, start_target, stats_game_type):
        self.players = [Player(name, start_target) for name in names]
        self.start_target = start_target
        self.stats_game_type = stats_game_type
        self.current = 0
        self.history = []
        self.winner_index = None

        for player in self.players:
            player.checkout_target = start_target
            player.checkout_best = start_target
            player.checkout_darts_used = 0
            player.checkout_active = True

    def current_player(self):
        return self.players[self.current]

    def next_player(self):
        if not any(player.checkout_active for player in self.players):
            return

        for offset in range(1, len(self.players) + 1):
            next_index = (self.current + offset) % len(self.players)
            if self.players[next_index].checkout_active:
                self.current = next_index
                return

    def current_target(self, player=None):
        player = player or self.current_player()
        return player.checkout_target

    def identify_current_player(self, code):
        name, stats_file = PLAYER_IDENTITIES[code]

        if any(player.stats_file == stats_file for player in self.players):
            return f"{name} is already assigned"

        player = self.current_player()
        player.name = name
        player.stats_file = stats_file
        return f"Player assigned as {name}"

    def is_legal_move(self, points):
        impossible_scores = {
            179, 178, 176, 175, 173, 172, 169,
            168, 166, 165, 163, 162, 159
        }

        return 0 <= points <= 180 and points not in impossible_scores

    def snapshot(self, player):
        return (
            self.current,
            player.score,
            player.checkout_target,
            player.checkout_best,
            player.checkout_darts_used,
            player.checkout_active,
            len(player.throws),
            self.winner_index,
        )

    def restore_snapshot(self, player, snapshot):
        (
            self.current,
            player.score,
            player.checkout_target,
            player.checkout_best,
            player.checkout_darts_used,
            player.checkout_active,
            throws_len,
            self.winner_index,
        ) = snapshot
        del player.throws[throws_len:]

    def fail_current_run(self, player):
        player.checkout_active = False

        if any(active_player.checkout_active for active_player in self.players):
            failed_name = player.name
            failed_best = player.checkout_best
            self.next_player()
            return f"{failed_name} out at {failed_best}"

        self.winner_index = self.current
        return "All runs ended"

    def add_score(self, points):
        player = self.current_player()

        if not self.is_legal_move(points):
            return "Invalid throw"

        old_player = self.current
        snapshot = self.snapshot(player)

        if points > player.score or player.score - points == 1:
            player.checkout_darts_used += 3
            player.throws.append(0)
            self.history.append((old_player, snapshot))

            if player.checkout_darts_used >= 9:
                return self.fail_current_run(player)

            self.next_player()
            return "Bust!"

        player.score -= points
        player.throws.append(points)
        self.history.append((old_player, snapshot))

        if player.score == 0:
            return f"{player.name} checked out!"

        player.checkout_darts_used += 3
        if player.checkout_darts_used >= 9:
            return self.fail_current_run(player)

        self.next_player()
        return f"{player.name}: {points}"

    def complete_checkout(self, checkout_darts):
        player = self.current_player()
        total_darts = player.checkout_darts_used + checkout_darts

        if total_darts > 9:
            return self.fail_current_run(player)

        completed_target = player.checkout_target
        player.checkout_target += 1
        player.checkout_best = max(player.checkout_best, player.checkout_target)
        player.score = player.checkout_target
        player.checkout_darts_used = 0
        player.throws.clear()

        self.next_player()
        return ""

    def undo(self):
        if not self.history:
            return None

        player_index, snapshot = self.history.pop()
        player = self.players[player_index]
        self.restore_snapshot(player, snapshot)
        return "Undid throw"

    def best_run_summary(self):
        return max((player.checkout_best for player in self.players), default=self.start_target)

    def save_completed_leg(self, checkout_darts):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        for player in self.players:
            if not player.stats_file:
                continue

            line = f"{timestamp};{self.stats_game_type};{player.checkout_best}\n"
            append_stats_line(player.stats_file, line)


class BullGame:
    def __init__(self, names):
        self.players = [Player(name, 0) for name in names]
        self.current = 0
        self.history = []

    def current_player(self):
        return self.players[self.current]

    def next_player(self):
        self.current = (self.current + 1) % len(self.players)

    def current_target(self, player=None):
        return len((player or self.current_player()).clock_darts)

    def identify_current_player(self, code):
        name, stats_file = PLAYER_IDENTITIES[code]
        if any(player.stats_file == stats_file for player in self.players):
            return f"{name} is already assigned"
        player = self.current_player()
        player.name = name
        player.stats_file = stats_file
        return f"Player assigned as {name}"

    def add_round(self, code):
        if len(code) != 3 or code[0] not in "012" or any(dart not in "012" for dart in code[1:]):
            return "Enter exactly 3 digits"
        if code[0] == "0" and (code[1] not in "01" or code[2] not in "01"):
            return "After 0, use 0/1 for triple and double"

        old_player = self.current
        player = self.current_player()
        player.clock_darts.append(code)
        self.history.append(old_player)
        self.next_player()
        return f"{player.name}: {code}"

    def undo(self):
        if not self.history:
            return None
        player_index = self.history.pop()
        player = self.players[player_index]
        player.clock_darts.pop()
        self.current = player_index
        return "Undid round"

    def save_completed_leg(self, checkout_darts=None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        for player in self.players:
            if player.stats_file and player.clock_darts:
                rounds = ",".join(player.clock_darts)
                append_stats_line(player.stats_file, f"{timestamp};bullgame;{rounds}\n")
class ClockGame:
    def __init__(self, names, stats_game_type="clock"):
        self.players = [Player(name, 0) for name in names]
        self.stats_game_type = stats_game_type
        self.current = 0
        self.history = []
        self.winner_index = None

    def current_player(self):
        return self.players[self.current]

    def current_target(self, player=None):
        player = player or self.current_player()
        if player.clock_index >= len(CLOCK_TARGETS):
            return "done"
        return CLOCK_TARGETS[player.clock_index]

    def next_player(self):
        self.current = (self.current + 1) % len(self.players)

    def identify_current_player(self, code):
        name, stats_file = PLAYER_IDENTITIES[code]

        if any(player.stats_file == stats_file for player in self.players):
            return f"{name} is already assigned"

        player = self.current_player()
        player.name = name
        player.stats_file = stats_file
        return f"Player assigned as {name}"

    def add_hits(self, hits):
        if hits < 0 or hits > 3:
            return "Press 0, 1, 2 or 3"

        player = self.current_player()
        old_index = player.clock_index
        old_player = self.current

        player.clock_index = min(len(CLOCK_TARGETS), player.clock_index + hits)
        player.throws.append(hits)
        player.clock_darts.append(str(hits))
        self.history.append((old_player, old_index, hits, str(hits)))

        if player.clock_index == len(CLOCK_TARGETS):
            self.winner_index = old_player
            return f"{player.name} won!"

        self.next_player()
        return f"{player.name}: {hits} hit"

    def add_dart_sequence(self, sequence):
        if not sequence or len(sequence) > 3 or any(dart not in "01" for dart in sequence):
            return "Enter 0/1 for each dart"

        player = self.current_player()
        old_index = player.clock_index
        old_player = self.current
        finished = False
        used_sequence = ""

        for dart in sequence:
            used_sequence += dart
            if dart == "1":
                player.clock_index += 1
                if player.clock_index == len(CLOCK_TARGETS):
                    finished = True
                    break

        if not finished and len(sequence) != 3:
            player.clock_index = old_index
            return "Enter 3 darts"

        hits = player.clock_index - old_index
        player.throws.append(hits)
        player.clock_darts.append(used_sequence)
        self.history.append((old_player, old_index, hits, used_sequence))

        if finished:
            self.winner_index = old_player
            return f"{player.name} won!"

        self.next_player()
        return f"{player.name}: {hits} hit"

    def undo(self):
        if not self.history:
            return None

        player_index, old_index, hits, _ = self.history.pop()
        self.players[player_index].clock_index = old_index
        self.players[player_index].throws.pop()
        self.players[player_index].clock_darts.pop()
        self.current = player_index
        self.winner_index = None
        return f"Undid {hits}"

    def save_completed_leg(self, final_darts):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        for player_index, player in enumerate(self.players):
            if not player.stats_file:
                continue

            throws = ",".join(player.clock_darts)
            result = "C" if player_index == self.winner_index else "F"
            if result == "C":
                line = f"{timestamp};{self.stats_game_type};{throws};C\n"
            else:
                line = f"{timestamp};{self.stats_game_type};{throws};F\n"

            append_stats_line(player.stats_file, line)


class SuperClockGame(ClockGame):
    def __init__(self, names):
        super().__init__(names, stats_game_type="superclock")

    def add_hits(self, hits):
        return self.add_dart_sequence(str(hits))

    def add_dart_sequence(self, sequence):
        if not sequence or len(sequence) > 3 or any(dart not in "0123" for dart in sequence):
            return "Enter 0/1/2/3 for each dart"

        player = self.current_player()
        old_index = player.clock_index
        old_player = self.current
        finished = False
        used_sequence = ""

        for dart in sequence:
            value = int(dart)
            used_sequence += dart

            if player.clock_index >= len(CLOCK_TARGETS):
                finished = True
                break

            target = self.current_target(player)
            if target in (25, 50) and value > 1:
                player.clock_index = old_index
                return "25 and bull only accept 0/1"

            if value == 0:
                continue

            if target == 50:
                player.clock_index = len(CLOCK_TARGETS)
                finished = True
                break

            if target == 25:
                player.clock_index = 21
            else:
                player.clock_index = min(21, player.clock_index + value)

        if not finished and len(sequence) != 3:
            player.clock_index = old_index
            return "Enter 3 darts"

        hits = player.clock_index - old_index
        player.throws.append(hits)
        player.clock_darts.append(used_sequence)
        self.history.append((old_player, old_index, hits, used_sequence))

        if finished:
            self.winner_index = old_player
            return f"{player.name} won!"

        self.next_player()
        return f"{player.name}: {hits} hit"


def load_player_stats(stats_filename):
    stats_path = Path(__file__).resolve().parent / stats_filename
    x01_legs = []
    clock_legs = []
    superclock_legs = []
    bullgame_rounds = []
    checkout_121_runs = []
    checkout_61_runs = []

    try:
        lines = stats_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []

    for line in lines:
        if not line or line.startswith("#"):
            continue

        try:
            parts = line.split(";")
            game_type = parts[1]

            if game_type in {"checkout121", "checkout61"}:
                best_run = int(parts[2])
                if game_type == "checkout121":
                    checkout_121_runs.append(best_run)
                else:
                    checkout_61_runs.append(best_run)
            elif game_type == "bullgame":
                rounds = [value for value in parts[2].split(",") if value]
                if any(
                    len(code) != 3
                    or code[0] not in "012"
                    or any(dart not in "012" for dart in code[1:])
                    or (code[0] == "0" and any(dart not in "01" for dart in code[1:]))
                    for code in rounds
                ):
                    continue
                bullgame_rounds.extend(rounds)
            elif game_type in {"clock", "superclock"}:
                rounds = [value for value in parts[2].split(",") if value]
                result = parts[3]

                if result not in {"C", "F"}:
                    continue

                allowed_darts = {"0", "1"} if game_type == "clock" else {"0", "1", "2", "3"}
                if any(set(round_value) - allowed_darts for round_value in rounds):
                    continue

                darts = sum(len(round_value) for round_value in rounds)
                if game_type == "clock":
                    segment_stats = exact_clock_segments(rounds)
                else:
                    segment_stats = exact_superclock_segments(rounds)
                    if segment_stats is None:
                        continue

                leg = {
                    "rounds": rounds,
                    "darts": darts,
                    "completed": result == "C",
                    "segment_stats": segment_stats,
                }
                if game_type == "clock":
                    clock_legs.append(leg)
                else:
                    superclock_legs.append(leg)
            else:
                start_score = int(game_type)
                throws = [int(points) for points in parts[2].split(",") if points]
                double_attempts = int(parts[3][1:]) if parts[3].startswith("D") else 0
                result = parts[4]

                if result.startswith("C"):
                    checkout_darts = int(result[1:])
                    darts = max(0, (len(throws) - 1) * 3 + checkout_darts)
                elif result == "F":
                    checkout_darts = None
                    darts = len(throws) * 3
                else:
                    continue

                x01_legs.append({
                    "start_score": start_score,
                    "throws": throws,
                    "double_attempts": double_attempts,
                    "checkout_darts": checkout_darts,
                    "darts": darts,
                })
        except (IndexError, ValueError):
            continue

    stats_501 = aggregate_x01_stats([leg for leg in x01_legs if leg["start_score"] == 501])
    stats_301 = aggregate_x01_stats([leg for leg in x01_legs if leg["start_score"] == 301])
    clock_stats = aggregate_clock_stats(clock_legs)
    superclock_stats = aggregate_clock_stats(superclock_legs)
    bullgame_stats = aggregate_bullgame_stats(bullgame_rounds)

    return {
        "legs": stats_501["legs"],
        "wins": stats_501["wins"],
        "losses": stats_501["losses"],
        "win_percent": stats_501["win_percent"],
        "three_dart_average": stats_501["three_dart_average"],
        "checkout_percent": stats_501["checkout_percent"],
        "double_attempts": stats_501["double_attempts"],
        "score_100_plus": stats_501["score_100_plus"],
        "score_140_plus": stats_501["score_140_plus"],
        "score_180": stats_501["score_180"],
        "checkout_100_plus": stats_501["checkout_100_plus"],
        "highest_checkout": stats_501["highest_checkout"],
        "best_leg": stats_501["best_leg"],
        "nine_darters": stats_501["nine_darters"],
        "301_legs": stats_301["legs"],
        "301_three_dart_average": stats_301["three_dart_average"],
        "301_best_leg": stats_301["best_leg"],
        "301_checkout_percent": stats_301["checkout_percent"],
        "301_score_100_plus": stats_301["score_100_plus"],
        "301_score_140_plus": stats_301["score_140_plus"],
        "301_score_180": stats_301["score_180"],
        "301_checkout_100_plus": stats_301["checkout_100_plus"],
        "301_highest_checkout": stats_301["highest_checkout"],
        "301_six_darters": stats_301["six_darters"],
        "clock_legs": clock_stats["legs"],
        "clock_wins": clock_stats["wins"],
        "clock_losses": clock_stats["losses"],
        "clock_win_percent": clock_stats["win_percent"],
        "clock_average_darts": clock_stats["average_darts"],
        "clock_best": clock_stats["best"],
        "clock_segment_percent": clock_stats["segment_percent"],
        "clock_25_percent": clock_stats["twenty_five_percent"],
        "clock_bull_percent": clock_stats["bull_percent"],
        "superclock_legs": superclock_stats["legs"],
        "superclock_wins": superclock_stats["wins"],
        "superclock_losses": superclock_stats["losses"],
        "superclock_win_percent": superclock_stats["win_percent"],
        "superclock_average_darts": superclock_stats["average_darts"],
        "superclock_best": superclock_stats["best"],
        "superclock_segment_percent": superclock_stats["segment_percent"],
        "superclock_25_percent": superclock_stats["twenty_five_percent"],
        "superclock_bull_percent": superclock_stats["bull_percent"],
        "checkout_121_best": max(checkout_121_runs, default=0),
        "checkout_61_best": max(checkout_61_runs, default=0),
        "checkout_121_average": sum(checkout_121_runs) / len(checkout_121_runs) if checkout_121_runs else 0,
        "checkout_61_average": sum(checkout_61_runs) / len(checkout_61_runs) if checkout_61_runs else 0,
        "bullgame_rounds": bullgame_stats["rounds"],
        "bullgame_bull_percent": bullgame_stats["bull_percent"],
        "bullgame_fifty_percent": bullgame_stats["fifty_percent"],
        "bullgame_triple_percent": bullgame_stats["triple_percent"],
        "bullgame_double_percent": bullgame_stats["double_percent"],
    }


# ---------- States ----------
STATE_START = "start"
STATE_PLAYER_COUNT = "player_count"
STATE_GAME_SELECT = "game_select"
STATE_STATS = "stats"
STATE_PLAYING = "playing"
STATE_CHECKOUT_DARTS = "checkout_darts"
STATE_GAME_OVER = "game_over"


# ---------- Helpers ----------
def reset_to_start():
    global state, player_count, selected_game, game, current_input, message, checkout_darts, stats_data, stats_player_index, stats_page
    state = STATE_START
    player_count = None
    selected_game = None
    game = None
    current_input = ""
    message = ""
    checkout_darts = None
    stats_data = None
    stats_player_index = 0
    stats_page = 0

def replay_game():
    global game, current_input, message, checkout_darts, state

    names = [player.name for player in game.players]
    old_players = game.players
    if selected_game in X01_GAMES:
        game = DartGame(names, start_score=int(selected_game))
    elif selected_game == "clock":
        game = ClockGame(names)
    elif selected_game == "superclock":
        game = SuperClockGame(names)
    elif selected_game == "checkout121":
        game = CheckoutRunGame(names, 121, "checkout121")
    elif selected_game == "checkout61":
        game = CheckoutRunGame(names, 61, "checkout61")
    elif selected_game == BULLGAME:
        game = BullGame(names)

    for new_player, old_player in zip(game.players, old_players):
        new_player.stats_file = old_player.stats_file

    current_input = ""
    message = ""
    checkout_darts = None
    state = STATE_PLAYING

# ---------- Pygame ----------
pygame.init()

BASE_SIZE = (1000, 600)
WINDOW_SIZE = (1000, 600)

screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
canvas = pygame.Surface(BASE_SIZE)
pygame.display.set_caption("Dart Score")

big_font = pygame.font.Font(None, 150)
medium_font = pygame.font.Font(None, 60)
small_font = pygame.font.Font(None, 32)

state = STATE_START

player_count = None
selected_game = None
game = None

current_input = ""
message = ""
checkout_darts = None
stats_data = None
stats_player_index = 0
stats_page = 0
fullscreen = False
window_size = WINDOW_SIZE


def toggle_fullscreen():
    global screen, fullscreen, window_size

    fullscreen = not fullscreen
    if fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode(window_size, pygame.RESIZABLE)


def present_canvas():
    screen_width, screen_height = screen.get_size()
    scale = min(screen_width / BASE_SIZE[0], screen_height / BASE_SIZE[1])
    scaled_size = (
        max(1, int(BASE_SIZE[0] * scale)),
        max(1, int(BASE_SIZE[1] * scale)),
    )
    offset = (
        (screen_width - scaled_size[0]) // 2,
        (screen_height - scaled_size[1]) // 2,
    )

    screen.fill((0, 0, 0))
    scaled_canvas = pygame.transform.smoothscale(canvas, scaled_size)
    screen.blit(scaled_canvas, offset)
    pygame.display.flip()

running = True
while running:

    # ---------- Events ----------
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.VIDEORESIZE and not fullscreen:
            window_size = (event.w, event.h)
            screen = pygame.display.set_mode(window_size, pygame.RESIZABLE)

        if event.type == pygame.KEYDOWN:
            state_before_keydown = state

            if event.key == pygame.K_F11:
                toggle_fullscreen()

            elif event.key == pygame.K_ESCAPE:
                if state == STATE_GAME_OVER or state == STATE_PLAYING and selected_game == BULLGAME:
                    try:
                        game.save_completed_leg(checkout_darts)
                    except OSError:
                        message = 'Could not save stats'
                        continue
                reset_to_start()

            elif state == STATE_START:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    state = STATE_GAME_SELECT

            elif state == STATE_PLAYER_COUNT:
                if event.key == pygame.K_BACKSPACE:
                    state = STATE_GAME_SELECT

                elif event.unicode in "123456789":
                    player_count = int(event.unicode)
                    names = [f"P{i + 1}" for i in range(player_count)]
                    if selected_game in X01_GAMES:
                        game = DartGame(names, start_score=int(selected_game))
                    elif selected_game == "clock":
                        game = ClockGame(names)
                    elif selected_game == "superclock":
                        game = SuperClockGame(names)
                    elif selected_game == "checkout121":
                        game = CheckoutRunGame(names, 121, "checkout121")
                    elif selected_game == "checkout61":
                        game = CheckoutRunGame(names, 61, "checkout61")
                    elif selected_game == BULLGAME:
                        game = BullGame(names)
                    current_input = ""
                    message = ""
                    state = STATE_PLAYING

            elif state == STATE_GAME_SELECT:
                if event.key == pygame.K_BACKSPACE:
                    reset_to_start()

                elif event.unicode == "1":
                    selected_game = "501"
                    state = STATE_PLAYER_COUNT

                elif event.unicode == "2":
                    selected_game = "301"
                    state = STATE_PLAYER_COUNT

                elif event.unicode == "3":
                    selected_game = "clock"
                    state = STATE_PLAYER_COUNT

                elif event.unicode == "4":
                    selected_game = "superclock"
                    state = STATE_PLAYER_COUNT

                elif event.unicode == "5":
                    selected_game = "checkout121"
                    state = STATE_PLAYER_COUNT

                elif event.unicode == "6":
                    selected_game = "checkout61"
                    state = STATE_PLAYER_COUNT

                elif event.unicode == "7":
                    selected_game = BULLGAME
                    state = STATE_PLAYER_COUNT

                elif event.unicode == "8":
                    stats_player_index = 0
                    stats_page = 0
                    stats_data = load_player_stats(STATS_PLAYERS[stats_player_index][1])
                    state = STATE_STATS

            elif state == STATE_STATS:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    stats_page += 1
                    if stats_page >= 3:
                        stats_page = 0
                        stats_player_index = (stats_player_index + 1) % len(STATS_PLAYERS)
                    stats_data = load_player_stats(STATS_PLAYERS[stats_player_index][1])

                elif event.key == pygame.K_BACKSPACE:
                    state = STATE_GAME_SELECT

            elif state == STATE_PLAYING:
                if event.key == pygame.K_BACKSPACE:
                    if current_input:
                        current_input = current_input[:-1]
                    else:
                        undo_message = game.undo()
                        if undo_message:
                            message = undo_message
                        else:
                            reset_to_start()

                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if selected_game == BULLGAME and not current_input:
                        try:
                            game.save_completed_leg()
                            reset_to_start()
                        except OSError:
                            message = "Could not save stats"
                        continue

                    submitted_input = current_input or "0"

                    if current_input and submitted_input in PLAYER_IDENTITIES:
                        message = game.identify_current_player(submitted_input)
                    else:
                        try:
                            if selected_game in X01_GAMES:
                                points, double_attempts = parse_score_input(submitted_input)
                                message = game.add_score(points, double_attempts)
                            elif selected_game == "clock":
                                if game.current_player().stats_file:
                                    message = game.add_dart_sequence(submitted_input)
                                else:
                                    if submitted_input not in "0123" or len(submitted_input) != 1:
                                        raise ValueError("Clock hits must be 0, 1, 2 or 3")

                                    message = game.add_hits(int(submitted_input))
                            elif selected_game == "superclock":
                                message = game.add_dart_sequence(submitted_input)
                            elif selected_game == BULLGAME:
                                message = game.add_round(submitted_input)
                            elif selected_game in CHECKOUT_RUN_GAMES:
                                points, _ = parse_score_input(submitted_input)
                                message = game.add_score(points)

                            if "checked out" in message:
                                state = STATE_CHECKOUT_DARTS
                            elif "All runs ended" in message:
                                state = STATE_GAME_OVER
                            elif "won" in message:
                                if (
                                    selected_game == "superclock"
                                    or (selected_game == "clock" and game.current_player().stats_file)
                                ):
                                    checkout_darts = len(game.current_player().clock_darts[-1])
                                    state = STATE_GAME_OVER
                                else:
                                    state = STATE_CHECKOUT_DARTS

                        except Exception:
                            message = "Invalid input"

                    current_input = ""

            elif state == STATE_CHECKOUT_DARTS:
                if event.key == pygame.K_BACKSPACE:
                    undo_message = game.undo()
                    checkout_darts = None
                    if undo_message:
                        message = undo_message
                        state = STATE_PLAYING
                    else:
                        reset_to_start()

                elif event.unicode in "123":
                    checkout_darts = int(event.unicode)
                    if selected_game in CHECKOUT_RUN_GAMES:
                        message = game.complete_checkout(checkout_darts)
                        checkout_darts = None
                        if "All runs ended" in message:
                            state = STATE_GAME_OVER
                        else:
                            state = STATE_PLAYING
                    else:
                        state = STATE_GAME_OVER

            elif state == STATE_GAME_OVER:
                if event.key == pygame.K_BACKSPACE:
                    if (
                        selected_game in CHECKOUT_RUN_GAMES
                        or selected_game == "superclock"
                        or (selected_game == "clock" and game.players[game.winner_index].stats_file)
                    ):
                        undo_message = game.undo()
                        checkout_darts = None
                        if undo_message:
                            message = undo_message
                            state = STATE_PLAYING
                        else:
                            reset_to_start()
                    else:
                        checkout_darts = None
                        state = STATE_CHECKOUT_DARTS

                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    try:
                        game.save_completed_leg(checkout_darts)
                        replay_game()
                    except OSError:
                        message = "Could not save stats"

            if state_before_keydown == STATE_PLAYING:
                if event.unicode in "0123456789+-*/.,":
                    current_input += event.unicode

    # ---------- Draw ----------
    draw_surface = screen
    screen = canvas
    screen.fill((25, 25, 25))

    if state == STATE_START:
        title = big_font.render("DART", True, (255, 255, 255))
        hint = medium_font.render("Press Enter to start", True, (200, 200, 200))

        screen.blit(title, (345, 150))
        screen.blit(hint, (300, 330))

    elif state == STATE_PLAYER_COUNT:
        title = medium_font.render("How many players?", True, (255, 255, 255))
        hint = medium_font.render("Press 1-9", True, (200, 200, 200))

        screen.blit(title, (300, 210))
        screen.blit(hint, (380, 290))

    elif state == STATE_GAME_SELECT:
        title = medium_font.render("Select", True, (255, 255, 255))
        option1 = medium_font.render("1. 501", True, (200, 255, 200))
        option2 = medium_font.render("2. 301", True, (200, 255, 200))
        option3 = medium_font.render("3. Clock", True, (200, 255, 200))
        option4 = medium_font.render("4. Superclock", True, (200, 255, 200))
        option5 = medium_font.render("5. 121 Checkout", True, (200, 255, 200))
        option6 = medium_font.render("6. 61 Checkout", True, (200, 255, 200))
        option7 = medium_font.render("7. Bullgame", True, (200, 255, 200))
        option8 = medium_font.render("8. Stats", True, (180, 220, 255))

        screen.blit(title, (380, 105))
        screen.blit(option1, (380, 170))
        screen.blit(option2, (380, 215))
        screen.blit(option3, (380, 260))
        screen.blit(option4, (380, 305))
        screen.blit(option5, (380, 350))
        screen.blit(option6, (380, 395))
        screen.blit(option7, (380, 440))
        screen.blit(option8, (380, 485))

    elif state == STATE_STATS:
        stats_player_name = STATS_PLAYERS[stats_player_index][0]
        page_title = "x01" if stats_page == 0 else ("Clock" if stats_page == 1 else "Bullgame")
        title = medium_font.render(f"{stats_player_name}'s {page_title} stats", True, (255, 255, 255))
        screen.blit(title, (335, 35))

        if stats_page == 0:
            left_stats = [
                ("501", ""),
                ("Played legs", stats_data["legs"]),
                ("3-dart average", f'{stats_data["three_dart_average"]:.2f}'),
                ("Best leg", f'{stats_data["best_leg"]} darts' if stats_data["best_leg"] else "-"),
                ("Checkout", f'{stats_data["checkout_percent"]:.1f}%'),
                ("100+ / 140+", f'{stats_data["score_100_plus"]}/{stats_data["score_140_plus"]}'),
                ("180", stats_data["score_180"]),
                ("100+ checkouts", stats_data["checkout_100_plus"]),
                ("Highest checkout", stats_data["highest_checkout"] or "-"),
                ("9-darters", stats_data["nine_darters"]),
                ("Checkout runs", ""),
                ("121 record", stats_data["checkout_121_best"] or "-"),
                ("121 avg run", f'{stats_data["checkout_121_average"]:.1f}' if stats_data["checkout_121_average"] else "-"),
                ("61 record", stats_data["checkout_61_best"] or "-"),
                ("61 avg run", f'{stats_data["checkout_61_average"]:.1f}' if stats_data["checkout_61_average"] else "-"),
            ]
            right_stats = [
                ("301", ""),
                ("Played legs", stats_data["301_legs"]),
                ("3-dart average", f'{stats_data["301_three_dart_average"]:.2f}'),
                ("Best leg", f'{stats_data["301_best_leg"]} darts' if stats_data["301_best_leg"] else "-"),
                ("Checkout", f'{stats_data["301_checkout_percent"]:.1f}%'),
                ("100+ / 140+", f'{stats_data["301_score_100_plus"]}/{stats_data["301_score_140_plus"]}'),
                ("180", stats_data["301_score_180"]),
                ("100+ checkouts", stats_data["301_checkout_100_plus"]),
                ("Highest checkout", stats_data["301_highest_checkout"] or "-"),
                ("6-darters", stats_data["301_six_darters"]),
            ]
        elif stats_page == 1:
            left_stats = [
                ("Clock", ""),
                ("Played", stats_data["clock_legs"]),
                ("Average darts", f'{stats_data["clock_average_darts"]:.1f}' if stats_data["clock_average_darts"] else "-"),
                ("Best clock", f'{stats_data["clock_best"]} darts' if stats_data["clock_best"] else "-"),
                ("1-20 hit", f'{stats_data["clock_segment_percent"]:.1f}%'),
                ("25 hit", f'{stats_data["clock_25_percent"]:.1f}%'),
                ("BULL hit", f'{stats_data["clock_bull_percent"]:.1f}%'),
            ]
            right_stats = [
                ("Superclock", ""),
                ("Played", stats_data["superclock_legs"]),
                ("Average darts", f'{stats_data["superclock_average_darts"]:.1f}' if stats_data["superclock_average_darts"] else "-"),
                ("Best super", f'{stats_data["superclock_best"]} darts' if stats_data["superclock_best"] else "-"),
                ("1-20 hit", f'{stats_data["superclock_segment_percent"]:.1f}%'),
                ("25 hit", f'{stats_data["superclock_25_percent"]:.1f}%'),
                ("BULL hit", f'{stats_data["superclock_bull_percent"]:.1f}%'),
            ]
        else:
            left_stats = [
                ("Bullgame", ""),
                ("Rounds", stats_data["bullgame_rounds"]),
                ("Bull area", f'{stats_data["bullgame_bull_percent"]:.1f}%'),
                ("50 / bull area", f'{stats_data["bullgame_fifty_percent"]:.1f}%'),
            ]
            right_stats = [
                ("After first miss", ""),
                ("Triple", f'{stats_data["bullgame_triple_percent"]:.1f}%'),
                ("Double", f'{stats_data["bullgame_double_percent"]:.1f}%'),
            ]

        for column_x, rows in ((80, left_stats), (540, right_stats)):
            y = 105
            for label, value in rows:
                is_heading = value == ""
                color = (255, 255, 255) if is_heading else (180, 180, 180)
                label_text = small_font.render(label, True, color)
                value_text = small_font.render(str(value), True, (220, 255, 220))
                screen.blit(label_text, (column_x, y))
                screen.blit(value_text, (column_x + 255, y))
                y += 31

        hint = small_font.render("Enter changes page/player, Backspace to menu, Esc to start", True, (180, 180, 180))
        screen.blit(hint, (175, 555))

    elif state == STATE_PLAYING:
        player = game.current_player()

        box_height = 35 + len(game.players) * 35
        pygame.draw.rect(screen, (45, 45, 45), (20, 20, 260, box_height))

        y = 35
        for i, p in enumerate(game.players):
            color = (0, 255, 100) if i == game.current else (220, 220, 220)
            if selected_game in X01_GAMES:
                player_status = p.score
            elif selected_game in CHECKOUT_RUN_GAMES:
                player_status = p.checkout_target if p.checkout_active else f"out {p.checkout_best}"
            else:
                player_status = game.current_target(p)

            text = small_font.render(f"{p.name}: {player_status}", True, color)
            screen.blit(text, (35, y))
            y += 35

        name_text = medium_font.render(player.name, True, (220, 220, 220))
        screen.blit(name_text, (420, 80))

        if selected_game in X01_GAMES:
            score_text = big_font.render(str(player.score), True, (255, 255, 255))
            screen.blit(score_text, (420, 150))

            suggestion_box = pygame.Rect(705, 20, 270, 135)
            pygame.draw.rect(screen, (45, 45, 45), suggestion_box)
            suggestion_title = small_font.render("Suggested throw", True, (220, 220, 220))
            screen.blit(suggestion_title, (725, 35))

            suggested_score = suggestion_score(player.score, current_input)
            routes = CHECKOUTS.get(suggested_score, ()) if suggested_score is not None else ()
            if routes:
                for route_index, route in enumerate(routes[:2]):
                    route_text = small_font.render(format_route(route), True, (200, 255, 200))
                    screen.blit(route_text, (725, 75 + route_index * 35))
        elif selected_game == BULLGAME:
            rounds = len(player.clock_darts)
            score_text = big_font.render(str(rounds), True, (255, 255, 255))
            hint_text = small_font.render("Enter 3 digits: bull 0/1/2; after 0 use triple/double 0/1", True, (200, 200, 200))
            screen.blit(score_text, (420, 150))
            screen.blit(hint_text, (250, 290))
        elif selected_game in CHECKOUT_RUN_GAMES:
            target_text = medium_font.render(f"Target: {player.checkout_target}", True, (255, 255, 255))
            score_text = big_font.render(str(player.score), True, (255, 255, 255))
            darts_left = 9 - player.checkout_darts_used
            darts_text = medium_font.render(f"{darts_left} darts left", True, (200, 255, 200))
            hint_text = small_font.render("Enter score for this visit", True, (200, 200, 200))
            screen.blit(target_text, (360, 120))
            screen.blit(score_text, (420, 190))
            screen.blit(darts_text, (360, 315))
            screen.blit(hint_text, (360, 405))
        else:
            target_text = medium_font.render(f"Target: {game.current_target()}", True, (255, 255, 255))
            if player.stats_file:
                clock_hint = "Enter 0/1 for each dart"
            else:
                clock_hint = "Press 0-3 for hit count"
            if selected_game == "superclock":
                clock_hint = "Enter 0/1/2/3 for each dart"
            hint_text = small_font.render(clock_hint, True, (200, 200, 200))
            screen.blit(target_text, (360, 170))
            screen.blit(hint_text, (360, 250))

        input_text = medium_font.render(f"> {current_input}", True, (255, 255, 100))
        screen.blit(input_text, (320, 360))

        msg_text = medium_font.render(message, True, (180, 220, 255))
        screen.blit(msg_text, (320, 440))
    elif state == STATE_CHECKOUT_DARTS:
        if selected_game in X01_GAMES or selected_game in CHECKOUT_RUN_GAMES:
            prompt = "How many darts for checkout?"
        else:
            prompt = "How many darts were thrown?"

        title = medium_font.render(prompt, True, (255, 255, 255))
        hint = medium_font.render("Press 1, 2 or 3", True, (200, 200, 200))

        screen.blit(title, (220, 220))
        screen.blit(hint, (320, 310))

    elif state == STATE_GAME_OVER:
        title = medium_font.render(message, True, (255, 255, 255))
        extra = medium_font.render(game_over_summary(game, selected_game, checkout_darts), True, (200, 255, 200))
        hint = medium_font.render("ESC FOR EXIT   ENTER FOR REPLAY   BACKSPACE TO EDIT", True, (200, 200, 200))

        screen.blit(title, (330, 190))
        screen.blit(extra, (330, 270))
        screen.blit(hint, (250, 350))

    screen = draw_surface
    present_canvas()

pygame.quit()
