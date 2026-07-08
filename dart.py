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
STATS_HEADER = """# Dart Score stats format
# 501: YYYY-MM-DD HH:MM;501;score_per_round;D<double_attempts>;C<checkout_darts>|F
# Klockan: YYYY-MM-DD HH:MM;klockan;dart_sequence_per_round;C|F
# Klockan rounds use 0/1 per dart, e.g. 111,010,001
# D = dubbelförsök
"""


def load_checkout_suggestions():
    checkout_file = next(
        path for path in Path(__file__).resolve().parent.iterdir()
        if path.name.lower().startswith("utg") and path.suffix == ".py"
    )
    spec = importlib.util.spec_from_file_location("utgangar", checkout_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.UTGANGAR)


UTGANGAR = load_checkout_suggestions()

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
    total_darts = winner_darts(game, final_darts)

    if selected_game == "501":
        average = game.start_score / total_darts * 3 if total_darts else 0
        return f"{total_darts} pilar  Snitt: {average:.2f}"

    return f"{total_darts} pilar"


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
            return f"{name} är redan markerad"

        player = self.current_player()
        player.name = name
        player.stats_file = stats_file
        return f"Spelare markerad som {name}"

    def add_score(self, points, double_attempts=None):
        player = self.current_player()

        if not self.is_legal_move(points):
            return "Ogiltigt kast"

        old_score = player.score
        old_player = self.current

        if double_attempts is None:
            if points == 0:
                double_attempts = 3
            elif points == player.score:
                double_attempts = 1
            else:
                double_attempts = 0

        if points > player.score:
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
            return f"{player.name} vann!"

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
        return f"Ångrade {points}"

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


class ClockGame:
    def __init__(self, names):
        self.players = [Player(name, 0) for name in names]
        self.current = 0
        self.history = []
        self.winner_index = None

    def current_player(self):
        return self.players[self.current]

    def current_target(self, player=None):
        player = player or self.current_player()
        if player.clock_index >= len(CLOCK_TARGETS):
            return "klar"
        return CLOCK_TARGETS[player.clock_index]

    def next_player(self):
        self.current = (self.current + 1) % len(self.players)

    def identify_current_player(self, code):
        name, stats_file = PLAYER_IDENTITIES[code]

        if any(player.stats_file == stats_file for player in self.players):
            return f"{name} är redan markerad"

        player = self.current_player()
        player.name = name
        player.stats_file = stats_file
        return f"Spelare markerad som {name}"

    def add_hits(self, hits):
        if hits < 0 or hits > 3:
            return "Tryck 0, 1, 2 eller 3"

        player = self.current_player()
        old_index = player.clock_index
        old_player = self.current

        player.clock_index = min(len(CLOCK_TARGETS), player.clock_index + hits)
        player.throws.append(hits)
        player.clock_darts.append(str(hits))
        self.history.append((old_player, old_index, hits, str(hits)))

        if player.clock_index == len(CLOCK_TARGETS):
            self.winner_index = old_player
            return f"{player.name} vann!"

        self.next_player()
        return f"{player.name}: {hits} träff"

    def add_dart_sequence(self, sequence):
        if not sequence or len(sequence) > 3 or any(dart not in "01" for dart in sequence):
            return "Skriv 0/1 för varje pil"

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
            return "Skriv 3 pilar"

        hits = player.clock_index - old_index
        player.throws.append(hits)
        player.clock_darts.append(used_sequence)
        self.history.append((old_player, old_index, hits, used_sequence))

        if finished:
            self.winner_index = old_player
            return f"{player.name} vann!"

        self.next_player()
        return f"{player.name}: {hits} träff"

    def undo(self):
        if not self.history:
            return None

        player_index, old_index, hits, _ = self.history.pop()
        self.players[player_index].clock_index = old_index
        self.players[player_index].throws.pop()
        self.players[player_index].clock_darts.pop()
        self.current = player_index
        self.winner_index = None
        return f"Ångrade {hits}"

    def save_completed_leg(self, final_darts):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        for player_index, player in enumerate(self.players):
            if not player.stats_file:
                continue

            throws = ",".join(player.clock_darts)
            result = "C" if player_index == self.winner_index else "F"
            if result == "C":
                line = f"{timestamp};klockan;{throws};C\n"
            else:
                line = f"{timestamp};klockan;{throws};F\n"

            append_stats_line(player.stats_file, line)


def load_player_stats(stats_filename):
    stats_path = Path(__file__).resolve().parent / stats_filename
    legs_501 = []
    clock_legs = []

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

            if game_type == "klockan":
                rounds = [value for value in parts[2].split(",") if value]
                result = parts[3]

                if result not in {"C", "F"}:
                    continue

                if any(set(round_value) - {"0", "1"} for round_value in rounds):
                    continue

                darts = sum(len(round_value) for round_value in rounds)
                segment_stats = exact_clock_segments(rounds)

                clock_legs.append({
                    "rounds": rounds,
                    "darts": darts,
                    "completed": result == "C",
                    "segment_stats": segment_stats,
                })
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

                legs_501.append({
                    "start_score": start_score,
                    "throws": throws,
                    "double_attempts": double_attempts,
                    "checkout_darts": checkout_darts,
                    "darts": darts,
                })
        except (IndexError, ValueError):
            continue

    wins = [leg for leg in legs_501 if leg["checkout_darts"] is not None]
    all_throws = [points for leg in legs_501 for points in leg["throws"]]
    total_points = sum(all_throws)
    total_darts = sum(leg["darts"] for leg in legs_501)
    total_double_attempts = sum(leg["double_attempts"] for leg in legs_501)
    checkouts = [leg["throws"][-1] for leg in wins if leg["throws"]]
    clock_wins = [leg for leg in clock_legs if leg["completed"]]
    clock_segment_attempts = sum(
        leg["segment_stats"]["segment_attempts"]
        for leg in clock_legs
        if leg["segment_stats"]
    )
    clock_segment_hits = sum(
        leg["segment_stats"]["segment_hits"]
        for leg in clock_legs
        if leg["segment_stats"]
    )
    clock_25_attempts = sum(
        leg["segment_stats"]["twenty_five_attempts"]
        for leg in clock_legs
        if leg["segment_stats"]
    )
    clock_25_hits = sum(
        leg["segment_stats"]["twenty_five_hits"]
        for leg in clock_legs
        if leg["segment_stats"]
    )
    clock_bull_attempts = sum(
        leg["segment_stats"]["bull_attempts"]
        for leg in clock_legs
        if leg["segment_stats"]
    )
    clock_bull_hits = sum(
        leg["segment_stats"]["bull_hits"]
        for leg in clock_legs
        if leg["segment_stats"]
    )

    return {
        "legs": len(legs_501),
        "wins": len(wins),
        "losses": len(legs_501) - len(wins),
        "win_percent": len(wins) / len(legs_501) * 100 if legs_501 else 0,
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
        "clock_legs": len(clock_legs),
        "clock_wins": len(clock_wins),
        "clock_losses": len(clock_legs) - len(clock_wins),
        "clock_win_percent": len(clock_wins) / len(clock_legs) * 100 if clock_legs else 0,
        "clock_average_darts": (
            sum(leg["darts"] for leg in clock_wins) / len(clock_wins)
            if clock_wins else 0
        ),
        "clock_best": min((leg["darts"] for leg in clock_wins), default=0),
        "clock_segment_percent": percent(clock_segment_hits, clock_segment_attempts),
        "clock_25_percent": percent(clock_25_hits, clock_25_attempts),
        "clock_bull_percent": percent(clock_bull_hits, clock_bull_attempts),
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
    global state, player_count, selected_game, game, current_input, message, checkout_darts, stats_data, stats_player_index
    state = STATE_START
    player_count = None
    selected_game = None
    game = None
    current_input = ""
    message = ""
    checkout_darts = None
    stats_data = None
    stats_player_index = 0


# ---------- Pygame ----------
pygame.init()

screen = pygame.display.set_mode((1000, 600))
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

running = True
while running:

    # ---------- Events ----------
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN:
            state_before_keydown = state

            if event.key == pygame.K_ESCAPE:
                reset_to_start()

            elif state == STATE_START:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    state = STATE_GAME_SELECT

            elif state == STATE_PLAYER_COUNT:
                if event.unicode in "123456789":
                    player_count = int(event.unicode)
                    names = [f"P{i + 1}" for i in range(player_count)]
                    if selected_game == "501":
                        game = DartGame(names, start_score=501)
                    elif selected_game == "klockan":
                        game = ClockGame(names)
                    current_input = ""
                    message = ""
                    state = STATE_PLAYING

            elif state == STATE_GAME_SELECT:
                if event.unicode == "1":
                    selected_game = "501"
                    state = STATE_PLAYER_COUNT

                elif event.unicode == "2":
                    selected_game = "klockan"
                    state = STATE_PLAYER_COUNT

                elif event.unicode == "3":
                    stats_player_index = 0
                    stats_data = load_player_stats(STATS_PLAYERS[stats_player_index][1])
                    state = STATE_STATS

            elif state == STATE_STATS:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
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

                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    submitted_input = current_input or "0"

                    if current_input and submitted_input in PLAYER_IDENTITIES:
                        message = game.identify_current_player(submitted_input)
                    else:
                        try:
                            if selected_game == "501":
                                points, double_attempts = parse_score_input(submitted_input)
                                message = game.add_score(points, double_attempts)
                            elif selected_game == "klockan":
                                if game.current_player().stats_file:
                                    message = game.add_dart_sequence(submitted_input)
                                else:
                                    if submitted_input not in "0123" or len(submitted_input) != 1:
                                        raise ValueError("Clock hits must be 0, 1, 2 or 3")

                                    message = game.add_hits(int(submitted_input))

                            if "vann" in message:
                                if selected_game == "klockan" and game.current_player().stats_file:
                                    checkout_darts = len(game.current_player().clock_darts[-1])
                                    state = STATE_GAME_OVER
                                else:
                                    state = STATE_CHECKOUT_DARTS

                        except Exception:
                            message = "Fel input"

                    current_input = ""

            elif state == STATE_CHECKOUT_DARTS:
                if event.key == pygame.K_BACKSPACE:
                    message = game.undo()
                    checkout_darts = None
                    state = STATE_PLAYING

                elif event.unicode in "123":
                    checkout_darts = int(event.unicode)
                    state = STATE_GAME_OVER

            elif state == STATE_GAME_OVER:
                if event.key == pygame.K_BACKSPACE:
                    if selected_game == "klockan" and game.players[game.winner_index].stats_file:
                        message = game.undo()
                        checkout_darts = None
                        state = STATE_PLAYING
                    else:
                        checkout_darts = None
                        state = STATE_CHECKOUT_DARTS

                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    try:
                        game.save_completed_leg(checkout_darts)
                        reset_to_start()
                    except OSError:
                        message = "Kunde inte spara statistik"

            if state_before_keydown == STATE_PLAYING:
                if event.unicode in "0123456789+-*/.,":
                    current_input += event.unicode

    # ---------- Draw ----------
    screen.fill((25, 25, 25))

    if state == STATE_START:
        title = big_font.render("DART", True, (255, 255, 255))
        hint = medium_font.render("Enter för att börja", True, (200, 200, 200))

        screen.blit(title, (345, 150))
        screen.blit(hint, (300, 330))

    elif state == STATE_PLAYER_COUNT:
        title = medium_font.render("Hur många spelare?", True, (255, 255, 255))
        hint = medium_font.render("Tryck 1-9", True, (200, 200, 200))

        screen.blit(title, (300, 210))
        screen.blit(hint, (380, 290))

    elif state == STATE_GAME_SELECT:
        title = medium_font.render("Välj", True, (255, 255, 255))
        option1 = medium_font.render("1. 501", True, (200, 255, 200))
        option2 = medium_font.render("2. Klockan", True, (200, 255, 200))
        option3 = medium_font.render("3. Stats", True, (180, 220, 255))

        screen.blit(title, (380, 150))
        screen.blit(option1, (380, 250))
        screen.blit(option2, (380, 320))
        screen.blit(option3, (380, 390))

    elif state == STATE_STATS:
        stats_player_name = STATS_PLAYERS[stats_player_index][0]
        title = medium_font.render(f"{stats_player_name}s statistik", True, (255, 255, 255))
        screen.blit(title, (335, 35))

        left_stats = [
            ("501", ""),
            ("Spelade legs", stats_data["legs"]),
            ("3-pilssnitt", f'{stats_data["three_dart_average"]:.2f}'),
            ("Bästa leg", f'{stats_data["best_leg"]} pilar' if stats_data["best_leg"] else "-"),
            ("Checkout", f'{stats_data["checkout_percent"]:.1f}%'),
            ("100+ / 140+", f'{stats_data["score_100_plus"]}/{stats_data["score_140_plus"]}'),
            ("180", stats_data["score_180"]),
            ("100+ utgångar", stats_data["checkout_100_plus"]),
            ("Högsta utgång", stats_data["highest_checkout"] or "-"),
            ("9-pilare", stats_data["nine_darters"]),
        ]
        right_stats = [
            ("Klockan", ""),
            ("Spelade", stats_data["clock_legs"]),
            ("Snitt pilar", f'{stats_data["clock_average_darts"]:.1f}' if stats_data["clock_average_darts"] else "-"),
            ("Bästa klocka", f'{stats_data["clock_best"]} pilar' if stats_data["clock_best"] else "-"),
            ("1-20 träff", f'{stats_data["clock_segment_percent"]:.1f}%'),
            ("25 träff", f'{stats_data["clock_25_percent"]:.1f}%'),
            ("BULL träff", f'{stats_data["clock_bull_percent"]:.1f}%'),
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
                y += 37

        hint = small_font.render("Enter byter spelare, Backspace till meny, Esc till start", True, (180, 180, 180))
        screen.blit(hint, (205, 555))

    elif state == STATE_PLAYING:
        player = game.current_player()

        box_height = 35 + len(game.players) * 35
        pygame.draw.rect(screen, (45, 45, 45), (20, 20, 260, box_height))

        y = 35
        for i, p in enumerate(game.players):
            color = (0, 255, 100) if i == game.current else (220, 220, 220)
            if selected_game == "501":
                player_status = p.score
            else:
                player_status = game.current_target(p)

            text = small_font.render(f"{p.name}: {player_status}", True, color)
            screen.blit(text, (35, y))
            y += 35

        name_text = medium_font.render(player.name, True, (220, 220, 220))
        screen.blit(name_text, (420, 80))

        if selected_game == "501":
            score_text = big_font.render(str(player.score), True, (255, 255, 255))
            screen.blit(score_text, (420, 150))

            suggestion_box = pygame.Rect(705, 20, 270, 135)
            pygame.draw.rect(screen, (45, 45, 45), suggestion_box)
            suggestion_title = small_font.render("Föreslaget kast", True, (220, 220, 220))
            screen.blit(suggestion_title, (725, 35))

            suggested_score = suggestion_score(player.score, current_input)
            routes = UTGANGAR.get(suggested_score, ()) if suggested_score is not None else ()
            if routes:
                for route_index, route in enumerate(routes[:2]):
                    route_text = small_font.render(format_route(route), True, (200, 255, 200))
                    screen.blit(route_text, (725, 75 + route_index * 35))
        else:
            target_text = medium_font.render(f"Du är på: {game.current_target()}", True, (255, 255, 255))
            if player.stats_file:
                clock_hint = "Skriv 0/1 för varje pil"
            else:
                clock_hint = "Tryck 0-3 för antal träffar"
            hint_text = small_font.render(clock_hint, True, (200, 200, 200))
            screen.blit(target_text, (360, 170))
            screen.blit(hint_text, (360, 250))

        input_text = medium_font.render(f"> {current_input}", True, (255, 255, 100))
        screen.blit(input_text, (320, 360))

        msg_text = medium_font.render(message, True, (180, 220, 255))
        screen.blit(msg_text, (320, 440))
    elif state == STATE_CHECKOUT_DARTS:
        if selected_game == "501":
            prompt = "Hur många pilar vid utgång?"
        else:
            prompt = "Hur många pilar kastades?"

        title = medium_font.render(prompt, True, (255, 255, 255))
        hint = medium_font.render("Tryck 1, 2 eller 3", True, (200, 200, 200))

        screen.blit(title, (220, 220))  
        screen.blit(hint, (320, 310))
        
    elif state == STATE_GAME_OVER:
        title = medium_font.render(message, True, (255, 255, 255))
        extra = medium_font.render(game_over_summary(game, selected_game, checkout_darts), True, (200, 255, 200))
        hint = medium_font.render("Enter sparar, Backspace ändrar", True, (200, 200, 200))

        screen.blit(title, (330, 190))
        screen.blit(extra, (330, 270))
        screen.blit(hint, (250, 350))

    pygame.display.flip()

pygame.quit()
