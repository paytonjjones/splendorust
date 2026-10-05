#include "game_logic.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
volatile std::uint64_t sink = 0;
constexpr std::uint64_t kReplayGames = 10'000;
constexpr std::array<int, 10> kCanonicalToAhinNoble{9, 8, 10, 6, 7, 5, 4, 2, 3, 1};

std::vector<std::string> split(const std::string& text, char delim) {
    std::vector<std::string> parts;
    std::stringstream input(text);
    for (std::string part; std::getline(input, part, delim);) parts.push_back(part);
    return parts;
}

std::vector<int> ints(const std::string& text) {
    std::vector<int> values;
    if (text.empty()) return values;
    for (const auto& part : split(text, ',')) values.push_back(std::stoi(part));
    return values;
}

std::uint64_t hex64(const std::string& value) {
    return std::stoull(value, nullptr, 16);
}

Card card(int id) {
    if (id <= 0 || id > 90) throw std::runtime_error("card ID outside 1..90");
    return standardCards().at(static_cast<std::size_t>(id - 1));
}

struct ActionSpec {
    std::string kind;
    std::vector<int> values;
};

struct Turn {
    int index = -1;
    std::vector<ActionSpec> actions;
    std::uint64_t expected_digest = 0;
    std::string expected_snapshot;
};

struct Trace {
    std::uint64_t seed = 0;
    std::array<std::vector<int>, 3> draw_order;
    std::vector<int> nobles;
    std::uint64_t start_digest = 0;
    std::string start_snapshot;
    std::vector<Turn> turns;
    std::string status;
    std::uint64_t final_digest = 0;
    std::string final_snapshot;
};

Trace read_trace(const char* path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open trajectory file");
    Trace trace;
    Turn* turn = nullptr;
    bool saw_header = false, saw_start = false, saw_end = false;
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line[0] == '#') continue;
        const auto fields = split(line, '|');
        if (fields[0] == "TRAJECTORY") {
            if (fields.size() != 3 || fields[1] != "sprint48-ahin-full-turn-v1" || saw_header) {
                throw std::runtime_error("bad trajectory header");
            }
            trace.seed = std::stoull(fields[2]);
            saw_header = true;
        } else if (fields[0] == "SETUP_DECK") {
            if (fields.size() != 3) throw std::runtime_error("bad setup deck record");
            const int tier = std::stoi(fields[1]);
            if (tier < 0 || tier > 2) throw std::runtime_error("bad setup tier");
            trace.draw_order[static_cast<std::size_t>(tier)] = ints(fields[2]);
        } else if (fields[0] == "SETUP_NOBLES") {
            if (fields.size() != 2) throw std::runtime_error("bad setup noble record");
            trace.nobles = ints(fields[1]);
        } else if (fields[0] == "START") {
            if (fields.size() != 3 || saw_start) throw std::runtime_error("bad START record");
            trace.start_digest = hex64(fields[1]);
            trace.start_snapshot = fields[2];
            saw_start = true;
        } else if (fields[0] == "TURN") {
            if (fields.size() != 2 || turn != nullptr) throw std::runtime_error("bad TURN boundary");
            trace.turns.push_back(Turn{});
            turn = &trace.turns.back();
            turn->index = std::stoi(fields[1]);
        } else if (fields[0] == "ACTION") {
            if (fields.size() != 3 || turn == nullptr) throw std::runtime_error("action outside turn");
            turn->actions.push_back(ActionSpec{fields[1], ints(fields[2])});
        } else if (fields[0] == "ENDTURN") {
            if (fields.size() != 4 || turn == nullptr || std::stoi(fields[1]) != turn->index) {
                throw std::runtime_error("bad ENDTURN record");
            }
            turn->expected_digest = hex64(fields[2]);
            turn->expected_snapshot = fields[3];
            turn = nullptr;
        } else if (fields[0] == "END") {
            if (fields.size() != 5 || turn != nullptr || saw_end) throw std::runtime_error("bad END record");
            trace.status = fields[1];
            if (std::stoul(fields[2]) != trace.turns.size()) throw std::runtime_error("turn count mismatch");
            trace.final_digest = hex64(fields[3]);
            trace.final_snapshot = fields[4];
            saw_end = true;
        } else {
            throw std::runtime_error("unknown trajectory record: " + fields[0]);
        }
    }
    if (!saw_header || !saw_start || !saw_end || trace.status != "complete" || trace.turns.empty()) {
        throw std::runtime_error("trajectory is incomplete or has an unsupported status");
    }
    for (int tier = 0; tier < 3; ++tier) {
        const std::size_t expected = std::array<std::size_t, 3>{40, 30, 20}[static_cast<std::size_t>(tier)];
        if (trace.draw_order[static_cast<std::size_t>(tier)].size() != expected) {
            throw std::runtime_error("setup tier has wrong card count");
        }
    }
    if (trace.nobles.size() != 3) throw std::runtime_error("two-player setup needs three nobles");
    std::array<bool, 8> action_coverage{};
    for (const auto& row : trace.turns) {
        for (const auto& action : row.actions) {
            if (action.kind == "take") action_coverage[0] = true;
            else if (action.kind == "reserve_visible") action_coverage[1] = true;
            else if (action.kind == "reserve_deck") action_coverage[2] = true;
            else if (action.kind == "buy_visible") action_coverage[3] = true;
            else if (action.kind == "buy_reserved") action_coverage[4] = true;
            else if (action.kind == "pay") action_coverage[5] = true;
            else if (action.kind == "return") action_coverage[6] = true;
            else if (action.kind == "noble") action_coverage[7] = true;
        }
    }
    if (!std::all_of(action_coverage.begin(), action_coverage.end(), [](bool covered) { return covered; })) {
        throw std::runtime_error("trajectory lacks required action coverage");
    }
    return trace;
}

GameState make_initial(const Trace& trace) {
    GameState state{};
    state.bank = Tokens{4, 4, 4, 4, 4, 5};
    for (int tier = 0; tier < 3; ++tier) {
        const auto& order = trace.draw_order[static_cast<std::size_t>(tier)];
        for (int slot = 0; slot < 4; ++slot) {
            state.faceup[tier][static_cast<std::size_t>(slot)] = card(order[static_cast<std::size_t>(slot)]);
        }
        for (int i = static_cast<int>(order.size()) - 1; i >= 4; --i) {
            state.deck[tier].push_back(card(order[static_cast<std::size_t>(i)]));
        }
    }
    state.noble_count = 3;
    for (int slot = 0; slot < 3; ++slot) {
        const int id = trace.nobles[static_cast<std::size_t>(slot)];
        if (id < 1 || id > 10) throw std::runtime_error("noble ID outside 1..10");
        state.available_nobles[static_cast<std::size_t>(slot)] = standardNobles().at(static_cast<std::size_t>(id - 1));
    }
    return state;
}

void feed(std::uint64_t& hash, std::uint64_t value) {
    hash = (hash ^ value) * 0x100000001b3ULL;
}

template<class Range, class Convert>
std::string joined(const Range& values, Convert&& convert) {
    std::ostringstream out;
    bool first = true;
    for (const auto& value : values) {
        if (!first) out << ',';
        first = false;
        out << convert(value);
    }
    return out.str();
}

template<class Range>
std::string joined(const Range& values) {
    return joined(values, [](const auto& value) { return value; });
}

std::uint64_t phase_code(const GameState& state) {
    return state.is_return_phase ? 1 : state.is_noble_choice_phase ? 2 : isGameOver(state) ? 4 : 0;
}

std::string material_snapshot(const GameState& state) {
    std::ostringstream out;
    const bool final_round = state.players[0].points >= 15 || state.players[1].points >= 15;
    out << "S;2;" << state.current_player << ';' << state.move_number << ';' << final_round << ';' << phase_code(state) << ';';
    const std::array<int, 6> bank{state.bank.white, state.bank.blue, state.bank.green,
                                  state.bank.red, state.bank.black, state.bank.joker};
    out << "B:" << joined(bank) << ";M:";
    std::array<int, 12> market{};
    for (int tier = 0; tier < 3; ++tier) {
        for (int slot = 0; slot < 4; ++slot) market[static_cast<std::size_t>(tier * 4 + slot)] =
            state.faceup[tier][static_cast<std::size_t>(slot)].id;
    }
    out << joined(market) << ';';
    for (int tier = 0; tier < 3; ++tier) {
        std::vector<int> deck;
        for (const auto& card : state.deck[tier]) deck.push_back(card.id);
        out << 'D' << tier << ':' << joined(deck) << ';';
    }
    std::vector<int> available;
    for (int i = 0; i < state.noble_count; ++i) available.push_back(state.available_nobles[static_cast<std::size_t>(i)].id);
    std::sort(available.begin(), available.end());
    out << "N:" << joined(available) << ';';
    for (int seat = 0; seat < 2; ++seat) {
        const auto& player = state.players[seat];
        const std::array<int, 6> tokens{player.tokens.white, player.tokens.blue, player.tokens.green,
                                        player.tokens.red, player.tokens.black, player.tokens.joker};
        const std::array<int, 5> bonuses{player.bonuses.white, player.bonuses.blue, player.bonuses.green,
                                         player.bonuses.red, player.bonuses.black};
        std::vector<int> owned;
        for (const auto& card : player.cards) owned.push_back(card.id);
        std::sort(owned.begin(), owned.end());
        std::vector<int> claimed;
        for (const auto& noble : player.nobles) claimed.push_back(noble.id);
        std::sort(claimed.begin(), claimed.end());
        out << 'P' << seat << ";T:" << joined(tokens) << ";B:" << joined(bonuses)
            << ";S:" << player.points << ";O:" << joined(owned) << ";N:" << joined(claimed) << ";R:";
        bool first = true;
        for (const auto& reserve : player.reserved) {
            if (!first) out << ',';
            first = false;
            out << reserve.card.id << ':' << reserve.card.level - 1 << ':' << reserve.is_public;
        }
        out << ';';
    }
    return out.str();
}

std::uint64_t material_digest(const GameState& state) {
    std::uint64_t hash = 0xcbf29ce484222325ULL;
    const bool final_round = state.players[0].points >= 15 || state.players[1].points >= 15;
    const std::uint64_t phase = state.is_return_phase ? 1 : state.is_noble_choice_phase ? 2 : isGameOver(state) ? 4 : 0;
    for (auto value : {2ULL, static_cast<std::uint64_t>(state.current_player),
                       static_cast<std::uint64_t>(state.move_number), static_cast<std::uint64_t>(final_round), phase}) {
        feed(hash, value);
    }
    for (Color c : {Color::White, Color::Blue, Color::Green, Color::Red, Color::Black, Color::Joker}) {
        feed(hash, static_cast<std::uint64_t>(state.bank[c]));
    }
    for (int tier = 0; tier < 3; ++tier) {
        for (const auto& c : state.faceup[tier]) feed(hash, static_cast<std::uint64_t>(c.id));
    }
    for (const auto& deck : state.deck) feed(hash, deck.size());
    std::vector<int> available;
    for (int i = 0; i < state.noble_count; ++i) available.push_back(state.available_nobles[static_cast<std::size_t>(i)].id);
    std::sort(available.begin(), available.end());
    feed(hash, available.size());
    for (int id : available) feed(hash, static_cast<std::uint64_t>(id));
    for (const auto& player : state.players) {
        for (Color c : {Color::White, Color::Blue, Color::Green, Color::Red, Color::Black, Color::Joker}) {
            feed(hash, static_cast<std::uint64_t>(player.tokens[c]));
        }
        for (Color c : {Color::White, Color::Blue, Color::Green, Color::Red, Color::Black}) {
            feed(hash, static_cast<std::uint64_t>(player.bonuses[c]));
        }
        feed(hash, static_cast<std::uint64_t>(player.points));
        std::vector<int> owned;
        for (const auto& c : player.cards) owned.push_back(c.id);
        std::sort(owned.begin(), owned.end());
        feed(hash, owned.size());
        for (int id : owned) feed(hash, static_cast<std::uint64_t>(id));
        std::vector<int> claimed;
        for (const auto& n : player.nobles) claimed.push_back(n.id);
        std::sort(claimed.begin(), claimed.end());
        feed(hash, claimed.size());
        for (int id : claimed) feed(hash, static_cast<std::uint64_t>(id));
        feed(hash, player.reserved.size());
        for (const auto& r : player.reserved) {
            feed(hash, static_cast<std::uint64_t>(r.card.id));
            feed(hash, static_cast<std::uint64_t>(r.card.level - 1));
            feed(hash, static_cast<std::uint64_t>(r.is_public));
        }
    }
    for (const auto& deck : state.deck) {
        feed(hash, deck.size());
        for (const auto& c : deck) feed(hash, static_cast<std::uint64_t>(c.id));
    }
    return hash;
}

void require_legal(const GameState& state, const Move& move) {
    const int index = moveToActionIndex(move);
    const auto mask = getValidMoveMask(state);
    if (index < 0 || index >= static_cast<int>(mask.size()) || mask[static_cast<std::size_t>(index)] == 0) {
        throw std::runtime_error("trajectory action is not legal in Ahin state");
    }
}

Move move_for(const ActionSpec& action) {
    Move move{};
    if (action.kind == "take") {
        if (action.values.size() != 5) throw std::runtime_error("TAKE needs five values");
        move.type = TAKE_GEMS;
        move.gems_taken = Tokens{action.values[0], action.values[1], action.values[2], action.values[3], action.values[4], 0};
    } else if (action.kind == "reserve_visible" || action.kind == "buy_visible") {
        if (action.values.size() != 1 || action.values[0] < 0 || action.values[0] >= 12) throw std::runtime_error("bad market slot");
        move.type = action.kind == "reserve_visible" ? RESERVE_CARD : BUY_CARD;
        move.card_tier = action.values[0] / 4;
        move.card_slot = action.values[0] % 4;
    } else if (action.kind == "reserve_deck") {
        if (action.values.size() != 1 || action.values[0] < 0 || action.values[0] > 2) throw std::runtime_error("bad deck tier");
        move.type = RESERVE_CARD;
        move.from_deck = true;
        move.card_tier = action.values[0];
    } else if (action.kind == "buy_reserved") {
        if (action.values.size() != 1 || action.values[0] < 0 || action.values[0] > 2) throw std::runtime_error("bad reserved slot");
        move.type = BUY_CARD;
        move.from_reserved = true;
        move.card_slot = action.values[0];
    } else if (action.kind == "noble") {
        if (action.values.size() != 1 || action.values[0] < 0 || action.values[0] > 9) throw std::runtime_error("bad canonical noble ID");
        const int wanted = kCanonicalToAhinNoble[static_cast<std::size_t>(action.values[0])];
        move.type = CHOOSE_NOBLE;
        move.noble_idx = wanted; // converted to the current slot before use
    } else {
        throw std::runtime_error("action cannot be mapped directly: " + action.kind);
    }
    return move;
}

void apply_buy_and_check_payment(GameState& state, const Move& buy, const ActionSpec& pay, std::uint64_t& native_applies) {
    if (pay.kind != "pay" || pay.values.size() != 5) throw std::runtime_error("buy has no following canonical payment");
    const int p = state.current_player;
    const Card purchased = buy.from_reserved
        ? state.players[p].reserved.at(static_cast<std::size_t>(buy.card_slot)).card
        : state.faceup[buy.card_tier][static_cast<std::size_t>(buy.card_slot)];
    const Tokens before = state.players[p].tokens;
    Tokens due;
    for (Color c : {Color::White, Color::Blue, Color::Green, Color::Red, Color::Black}) {
        due[c] = std::max(0, purchased.cost[c] - state.players[p].bonuses[c]);
    }
    std::array<int, 5> colored{};
    int gold = 0;
    for (int i = 0; i < 5; ++i) {
        const Color c = static_cast<Color>(i);
        colored[static_cast<std::size_t>(i)] = std::min(due[c], before[c]);
        gold += due[c] - colored[static_cast<std::size_t>(i)];
        if (pay.values[static_cast<std::size_t>(i)] != colored[static_cast<std::size_t>(i)]) {
            throw std::runtime_error("canonical payment differs from Ahin colored-first policy");
        }
    }
    if (gold > before.joker) throw std::runtime_error("canonical buy requires unavailable gold");
    require_legal(state, buy);
    applyMove(state, buy);
    ++native_applies;
    const Tokens after = state.players[p].tokens;
    for (int i = 0; i < 5; ++i) {
        if (before[static_cast<Color>(i)] - after[static_cast<Color>(i)] != colored[static_cast<std::size_t>(i)]) {
            throw std::runtime_error("Ahin auto-payment colored-token delta mismatch");
        }
    }
    if (before.joker - after.joker != gold) throw std::runtime_error("Ahin auto-payment gold delta mismatch");
}

struct ReplayStats {
    std::uint64_t canonical_actions = 0;
    std::uint64_t native_applies = 0;
    std::uint64_t legal_enumerations = 0;
    std::uint64_t completed_turns = 0;
};

ReplayStats replay(const Trace& trace, const GameState& initial, bool verify_digest) {
    GameState state = initial;
    if (verify_digest && (material_digest(state) != trace.start_digest || material_snapshot(state) != trace.start_snapshot)) {
        throw std::runtime_error("initial full-material exact snapshot mismatch");
    }
    ReplayStats stats;
    for (const auto& turn : trace.turns) {
        if (turn.index != static_cast<int>(stats.completed_turns)) throw std::runtime_error("nonsequential turn index");
        for (std::size_t i = 0; i < turn.actions.size();) {
            const auto& action = turn.actions[i];
            ++stats.canonical_actions;
            if (action.kind == "buy_visible" || action.kind == "buy_reserved") {
                const Move buy = move_for(action);
                if (i + 1 >= turn.actions.size()) throw std::runtime_error("buy missing payment action");
                apply_buy_and_check_payment(state, buy, turn.actions[i + 1], stats.native_applies);
                stats.legal_enumerations++;
                stats.canonical_actions++;
                i += 2;
                continue;
            }
            if (action.kind == "pay") throw std::runtime_error("orphan payment record");
            if (action.kind == "return") {
                if (action.values.size() != 6 || action.values[5] != 0) throw std::runtime_error("gold return is unsupported");
                for (int color = 0; color < 5; ++color) {
                    for (int count = 0; count < action.values[static_cast<std::size_t>(color)]; ++count) {
                        Move move{};
                        move.type = RETURN_GEM;
                        move.gem_returned[static_cast<Color>(color)] = 1;
                        require_legal(state, move);
                        ++stats.legal_enumerations;
                        applyMove(state, move);
                        ++stats.native_applies;
                    }
                }
                i++;
                continue;
            }
            Move move = move_for(action);
            if (action.kind == "noble") {
                const int canonical_id = action.values[0];
                const int wanted = kCanonicalToAhinNoble[static_cast<std::size_t>(canonical_id)];
                const auto it = std::find_if(state.available_nobles.begin(), state.available_nobles.begin() + state.noble_count,
                    [wanted](const Noble& noble) { return noble.id == wanted; });
                if (it == state.available_nobles.begin() + state.noble_count) throw std::runtime_error("chosen noble is not available");
                move.noble_idx = static_cast<int>(it - state.available_nobles.begin());
            }
            require_legal(state, move);
            ++stats.legal_enumerations;
            applyMove(state, move);
            ++stats.native_applies;
            ++i;
        }
        ++stats.completed_turns;
        if (verify_digest && (material_digest(state) != turn.expected_digest || material_snapshot(state) != turn.expected_snapshot)) {
            throw std::runtime_error("post-turn full-material/deck exact mismatch at turn " + std::to_string(turn.index));
        }
    }
    if (verify_digest && (material_digest(state) != trace.final_digest || material_snapshot(state) != trace.final_snapshot)) {
        throw std::runtime_error("final full-material exact snapshot mismatch");
    }
    if (verify_digest && !isGameOver(state)) throw std::runtime_error("trace does not end at a complete game");
    return stats;
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: ahin_trajectory TRAJECTORY.txt");
        const Trace trace = read_trace(argv[1]);
        const GameState initial = make_initial(trace);
        const ReplayStats verified = replay(trace, initial, true);
        std::cerr << "verified seed=" << trace.seed << " turns=" << verified.completed_turns
                  << " canonical_actions=" << verified.canonical_actions
                  << " ahin_apply_calls=" << verified.native_applies
                  << " ahin_legal_enumerations=" << verified.legal_enumerations << '\n';
        std::cout << "engine,workload,repeat,replayed_games,complete_turns,canonical_actions,native_apply_calls,legal_enumerations,seconds,turns_per_second,games_per_second\n";
        for (int repeat = 0; repeat < 3; ++repeat) {
            const auto start = std::chrono::steady_clock::now();
            ReplayStats timed;
            for (std::uint64_t game = 0; game < kReplayGames; ++game) {
                const ReplayStats one = replay(trace, initial, false);
                timed.canonical_actions += one.canonical_actions;
                timed.native_applies += one.native_applies;
                timed.legal_enumerations += one.legal_enumerations;
                timed.completed_turns += one.completed_turns;
            }
            const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            sink += timed.native_applies + timed.canonical_actions;
            std::cout << "ahin,full_turn_trace," << repeat << ',' << kReplayGames << ',' << timed.completed_turns << ','
                      << timed.canonical_actions << ',' << timed.native_applies << ',' << timed.legal_enumerations
                      << ',' << seconds << ',' << (timed.completed_turns / seconds) << ',' << (kReplayGames / seconds) << '\n';
        }
        std::cerr << "anti-optimization sink=" << sink << '\n';
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 1;
    }
}
