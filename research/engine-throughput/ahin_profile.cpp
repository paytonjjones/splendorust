// Diagnostic profiles for the pinned AhinLendor raw engine.
// Build with the same flags as the trajectory baseline and link game_logic.cpp.
// This file includes the baseline translation unit to reuse its trace parser,
// exact parity replay, and action mapping. It does not edit upstream sources.
#define main ahin_trajectory_baseline_main
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wreturn-type"
#endif
#include "../ahinlendor/engine/trajectory/ahin_trajectory.cpp"
#if defined(__clang__)
#pragma clang diagnostic pop
#endif
#undef main

#include <array>
#include <cstring>
#include <iomanip>
#include <limits>

namespace {

// Same structural parser as the original; complete suite traces need not each
// contain all eight categories. Coverage is reported and selected for the suite.
Trace read_complete_trace(const char* path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open trajectory file");
    Trace trace;
    Turn* turn = nullptr;
    bool saw_header = false, saw_start = false, saw_end = false, saw_nobles = false;
    std::array<bool, 3> saw_deck{};
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
            if (saw_deck[static_cast<std::size_t>(tier)]) throw std::runtime_error("duplicate setup tier");
            saw_deck[static_cast<std::size_t>(tier)] = true;
            trace.draw_order[static_cast<std::size_t>(tier)] = ints(fields[2]);
        } else if (fields[0] == "SETUP_NOBLES") {
            if (fields.size() != 2 || saw_nobles) throw std::runtime_error("bad or duplicate setup noble record");
            saw_nobles = true;
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
    return trace;
}

constexpr std::array<const char*, 4> kPhaseNames{"regular", "return", "noble", "terminal"};

int phase_index(const GameState& state) {
    if (state.is_return_phase) return 1;
    if (state.is_noble_choice_phase) return 2;
    if (isGameOver(state)) return 3;
    return 0;
}

struct ActionCase {
    GameState state;
    Move move;
    int phase;
};

struct PaymentCase {
    GameState state;
    Move buy;
    std::array<int, 5> expected_colored{};
};

enum class DecodedKind : std::uint8_t { Take, ReserveVisible, ReserveDeck, BuyVisible, BuyReserved, Return, Noble };

struct DecodedAction {
    DecodedKind kind{};
    std::array<int, 6> values{};
};

struct DecodedTurn {
    std::vector<DecodedAction> actions;
};

using PhaseStates = std::array<std::vector<GameState>, 4>;

inline void barrier(std::uint64_t value);

inline void barrier_state(const GameState& state) {
#if defined(__clang__) || defined(__GNUC__)
    asm volatile("" : : "g"(&state) : "memory");
#else
    volatile const GameState* observed = &state;
    (void)observed;
#endif
}

template<class T, std::size_t N>
inline void barrier_array(const std::array<T, N>& value) {
#if defined(__clang__) || defined(__GNUC__)
    asm volatile("" : : "g"(&value) : "memory");
#else
    volatile const std::array<T, N>* observed = &value;
    (void)observed;
#endif
}

std::vector<DecodedTurn> decode_trace(const Trace& trace) {
    std::vector<DecodedTurn> decoded;
    decoded.reserve(trace.turns.size());
    for (const auto& turn : trace.turns) {
        DecodedTurn output;
        for (std::size_t i = 0; i < turn.actions.size();) {
            const auto& action = turn.actions[i];
            DecodedAction result{};
            if (action.kind == "take") {
                result.kind = DecodedKind::Take;
            } else if (action.kind == "reserve_visible") {
                result.kind = DecodedKind::ReserveVisible;
            } else if (action.kind == "reserve_deck") {
                result.kind = DecodedKind::ReserveDeck;
            } else if (action.kind == "buy_visible") {
                result.kind = DecodedKind::BuyVisible;
                if (i + 1 >= turn.actions.size() || turn.actions[i + 1].kind != "pay")
                    throw std::runtime_error("decoded buy has no payment record");
                ++i;
            } else if (action.kind == "buy_reserved") {
                result.kind = DecodedKind::BuyReserved;
                if (i + 1 >= turn.actions.size() || turn.actions[i + 1].kind != "pay")
                    throw std::runtime_error("decoded buy has no payment record");
                ++i;
            } else if (action.kind == "return") {
                result.kind = DecodedKind::Return;
                if (action.values.size() != 6 || action.values[5] != 0)
                    throw std::runtime_error("decoded profile does not support gold returns");
            } else if (action.kind == "noble") {
                result.kind = DecodedKind::Noble;
            } else if (action.kind == "pay") {
                throw std::runtime_error("orphan payment in decoded profile");
            } else {
                throw std::runtime_error("unknown action in decoded profile");
            }
            if (action.values.size() > result.values.size())
                throw std::runtime_error("decoded action payload too large");
            for (std::size_t j = 0; j < action.values.size(); ++j) result.values[j] = action.values[j];
            output.actions.push_back(result);
            ++i;
        }
        decoded.push_back(std::move(output));
    }
    return decoded;
}

Move move_for_decoded(const DecodedAction& action, const GameState& state) {
    Move move{};
    switch (action.kind) {
        case DecodedKind::Take:
            move.type = TAKE_GEMS;
            move.gems_taken = Tokens{action.values[0], action.values[1], action.values[2],
                                     action.values[3], action.values[4], 0};
            break;
        case DecodedKind::ReserveVisible:
        case DecodedKind::BuyVisible:
            move.type = action.kind == DecodedKind::ReserveVisible ? RESERVE_CARD : BUY_CARD;
            move.card_tier = action.values[0] / 4;
            move.card_slot = action.values[0] % 4;
            break;
        case DecodedKind::ReserveDeck:
            move.type = RESERVE_CARD;
            move.from_deck = true;
            move.card_tier = action.values[0];
            break;
        case DecodedKind::BuyReserved:
            move.type = BUY_CARD;
            move.from_reserved = true;
            move.card_slot = action.values[0];
            break;
        case DecodedKind::Return:
            // A canonical return can contain several colors; the caller emits
            // one native RETURN_GEM per colored token.
            move.type = RETURN_GEM;
            move.gem_returned[Color::White] = 1;
            break;
        case DecodedKind::Noble: {
            move.type = CHOOSE_NOBLE;
            const int wanted = kCanonicalToAhinNoble[static_cast<std::size_t>(action.values[0])];
            const auto end = state.available_nobles.begin() + state.noble_count;
            const auto it = std::find_if(state.available_nobles.begin(), end,
                                         [wanted](const Noble& noble) { return noble.id == wanted; });
            if (it == end) throw std::runtime_error("decoded noble choice is unavailable");
            move.noble_idx = static_cast<int>(it - state.available_nobles.begin());
            break;
        }
    }
    return move;
}

std::uint64_t replay_decoded(const std::vector<DecodedTurn>& turns, const GameState& initial,
                             const Trace* parity_trace = nullptr, bool enumerate_mask = true) {
    GameState state = initial;
    std::uint64_t checksum = 0;
    std::size_t turn_index = 0;
    for (const auto& turn : turns) {
        for (const auto& action : turn.actions) {
            if (action.kind == DecodedKind::Return) {
                for (int color = 0; color < 5; ++color) {
                    for (int count = 0; count < action.values[static_cast<std::size_t>(color)]; ++count) {
                        Move move{};
                        move.type = RETURN_GEM;
                        move.gem_returned[static_cast<Color>(color)] = 1;
                        if (enumerate_mask) {
                            const auto mask = getValidMoveMask(state);
                            barrier_array(mask);
                            const int index = moveToActionIndex(move);
                            if (index < 0 || index >= 69 || mask[static_cast<std::size_t>(index)] == 0)
                                throw std::runtime_error("decoded return is illegal");
                        }
                        applyMove(state, move);
                    }
                }
            } else {
                const Move move = move_for_decoded(action, state);
                if (enumerate_mask) {
                    const auto mask = getValidMoveMask(state);
                    barrier_array(mask);
                    const int index = moveToActionIndex(move);
                    if (index < 0 || index >= 69 || mask[static_cast<std::size_t>(index)] == 0)
                        throw std::runtime_error("decoded action is illegal");
                }
                applyMove(state, move);
            }
        }
        // Keep each completed player turn's state observable in the timed path.
        barrier_state(state);
        ++checksum;
        if (parity_trace != nullptr) {
            const auto& expected = parity_trace->turns.at(turn_index);
            if (material_digest(state) != expected.expected_digest ||
                material_snapshot(state) != expected.expected_snapshot)
                throw std::runtime_error("predecoded exact state mismatch at turn " + std::to_string(turn_index));
        }
        ++turn_index;
    }
    if (parity_trace != nullptr && (turn_index != parity_trace->turns.size() ||
        material_digest(state) != parity_trace->final_digest ||
        material_snapshot(state) != parity_trace->final_snapshot || !isGameOver(state)))
        throw std::runtime_error("predecoded final exact state mismatch");
    if (parity_trace != nullptr) {
        const int winner = determineWinner(state);
        std::cerr << "outcome_winners_mask=" << (winner == -1 ? 3 : (1 << winner)) << '\n';
    }
    return checksum;
}

// Native moves are prepared with a shadow replay before any timed loop.
// This resolves noble slots and expands compound returns only once.
std::vector<std::vector<Move>> prepare_native_turns(
    const std::vector<DecodedTurn>& turns, const GameState& initial) {
    GameState state = initial;
    std::vector<std::vector<Move>> prepared;
    prepared.reserve(turns.size());
    for (const auto& turn : turns) {
        std::vector<Move> moves;
        const auto append = [&](const Move& move) {
            applyMove(state, move);
            moves.push_back(move);
        };
        for (const auto& action : turn.actions) {
            if (action.kind == DecodedKind::Return) {
                for (int color = 0; color < 5; ++color) {
                    for (int count = 0; count < action.values[static_cast<std::size_t>(color)]; ++count) {
                        Move move{};
                        move.type = RETURN_GEM;
                        move.gem_returned[static_cast<Color>(color)] = 1;
                        append(move);
                    }
                }
            } else {
                append(move_for_decoded(action, state));
            }
        }
        prepared.push_back(std::move(moves));
    }
    return prepared;
}

std::uint64_t replay_prepared_native(const std::vector<std::vector<Move>>& turns,
                                    const GameState& initial, const Trace* parity_trace = nullptr) {
    GameState state = initial;
    std::size_t turn_index = 0;
    for (const auto& turn : turns) {
        for (const auto& move : turn) {
#if defined(__clang__) || defined(__GNUC__)
            // Match the Rust path's observable supplied native action input.
            asm volatile("" : : "g"(&move) : "memory");
#endif
            applyMove(state, move);
        }
        barrier_state(state);
        if (parity_trace != nullptr) {
            const auto& expected = parity_trace->turns.at(turn_index);
            if (material_digest(state) != expected.expected_digest ||
                material_snapshot(state) != expected.expected_snapshot)
                throw std::runtime_error("prepared native state mismatch at turn " + std::to_string(turn_index));
        }
        ++turn_index;
    }
    if (parity_trace != nullptr) {
        if (turn_index != parity_trace->turns.size() ||
            material_digest(state) != parity_trace->final_digest ||
            material_snapshot(state) != parity_trace->final_snapshot || !isGameOver(state))
            throw std::runtime_error("prepared native final state mismatch");
        const int winner = determineWinner(state);
        std::cerr << "outcome_winners_mask=" << (winner == -1 ? 3 : (1 << winner)) << '\n';
    }
    return turn_index;
}

// Collect every state at which the trace selects one native move. A canonical
// buy+pay pair is one Ahin move; a canonical multi-return is several moves.
std::vector<ActionCase> collect_action_cases(const Trace& trace, const GameState& initial,
                                             PhaseStates& states_by_phase,
                                             std::vector<PaymentCase>& payment_cases) {
    GameState state = initial;
    std::vector<ActionCase> cases;
    auto remember = [&](const Move& move) {
        const int phase = phase_index(state);
        states_by_phase[static_cast<std::size_t>(phase)].push_back(state);
        cases.push_back(ActionCase{state, move, phase});
    };

    for (const auto& turn : trace.turns) {
        for (std::size_t i = 0; i < turn.actions.size();) {
            const auto& action = turn.actions[i];
            if (action.kind == "buy_visible" || action.kind == "buy_reserved") {
                const Move move = move_for(action);
                if (i + 1 >= turn.actions.size() || turn.actions[i + 1].kind != "pay")
                    throw std::runtime_error("buy missing payment during profile extraction");
                if (turn.actions[i + 1].values.size() != 5)
                    throw std::runtime_error("canonical payment has wrong size");
                PaymentCase payment{state, move, {}};
                for (std::size_t color = 0; color < 5; ++color)
                    payment.expected_colored[color] = turn.actions[i + 1].values[color];
                payment_cases.push_back(payment);
                remember(move);
                require_legal(state, move);
                applyMove(state, move);
                i += 2;
                continue;
            }
            if (action.kind == "pay") throw std::runtime_error("orphan payment during profile extraction");
            if (action.kind == "return") {
                if (action.values.size() != 6 || action.values[5] != 0)
                    throw std::runtime_error("gold return is unsupported by this trajectory profile");
                for (int color = 0; color < 5; ++color) {
                    for (int count = 0; count < action.values[static_cast<std::size_t>(color)]; ++count) {
                        Move move{};
                        move.type = RETURN_GEM;
                        move.gem_returned[static_cast<Color>(color)] = 1;
                        remember(move);
                        require_legal(state, move);
                        applyMove(state, move);
                    }
                }
                ++i;
                continue;
            }
            Move move = move_for(action);
            if (action.kind == "noble") {
                const int wanted = kCanonicalToAhinNoble[static_cast<std::size_t>(action.values.at(0))];
                const auto end = state.available_nobles.begin() + state.noble_count;
                const auto it = std::find_if(state.available_nobles.begin(), end,
                                             [wanted](const Noble& n) { return n.id == wanted; });
                if (it == end) throw std::runtime_error("selected noble not available during profile extraction");
                move.noble_idx = static_cast<int>(it - state.available_nobles.begin());
            }
            remember(move);
            require_legal(state, move);
            applyMove(state, move);
            ++i;
        }
    }
    return cases;
}

inline void barrier(std::uint64_t value) {
#if defined(__clang__) || defined(__GNUC__)
    asm volatile("" : : "g"(value) : "memory");
#else
    volatile std::uint64_t observed = value;
    (void)observed;
#endif
}

struct Sample {
    std::string trace;
    std::string profile;
    std::string phase;
    int repeat;
    std::uint64_t iterations;
    std::uint64_t operations;
    double seconds;
};

std::string active_trace;

template<class Fn>
Sample timed(const std::string& profile, const std::string& phase, int repeat,
             std::uint64_t iterations, std::uint64_t operations, Fn&& fn) {
    const auto start = std::chrono::steady_clock::now();
    const std::uint64_t checksum = fn();
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    barrier(checksum);
    return Sample{active_trace, profile, phase, repeat, iterations, operations, seconds};
}

void emit(const Sample& sample) {
    const double rate = sample.seconds > 0 ? static_cast<double>(sample.operations) / sample.seconds : 0;
    std::cout << sample.trace << ',' << sample.profile << ',' << sample.phase << ',' << sample.repeat << ','
              << sample.iterations << ',' << sample.operations << ',' << std::setprecision(9)
              << sample.seconds << ',' << std::setprecision(3) << rate << '\n';
}

void profile_trace(const char* path, int repeats, std::uint64_t iterations, bool prepared_only) {
    active_trace = path;
    const Trace trace = read_complete_trace(path);
    const GameState initial = make_initial(trace);

    // Exact snapshots and terminal status are checked before any timed loop.
    const ReplayStats verified = replay(trace, initial, true);
    if (prepared_only) {
        const auto native_turns = prepare_native_turns(decode_trace(trace), initial);
        std::size_t native_applies = 0;
        for (const auto& turn : native_turns) native_applies += turn.size();
        if (native_applies != verified.native_applies || native_turns.size() != verified.completed_turns)
            throw std::runtime_error("prepared native operation count differs from baseline replay");
        replay_prepared_native(native_turns, initial, &trace);
        std::cerr << "verified_input=" << path << " seed=" << trace.seed
                  << " turns=" << verified.completed_turns << " native_actions=" << native_applies
                  << " exact_full_state_parity=yes prepared_native_moves=yes\n";
        for (int repeat = 0; repeat < repeats; ++repeat) {
            const auto sample = timed("prepared_native_checked_apply_only", "all_turns", repeat,
                                      iterations, iterations * native_applies, [&] {
                std::uint64_t checksum = 0;
                for (std::uint64_t n = 0; n < iterations; ++n) {
                    checksum += replay_prepared_native(native_turns, initial);
                    barrier(checksum);
                }
                return checksum;
            });
            emit(sample);
        }
        return;
    }
    PhaseStates states_by_phase;
    std::vector<PaymentCase> payment_cases;
    const auto cases = collect_action_cases(trace, initial, states_by_phase, payment_cases);
    const auto decoded_turns = decode_trace(trace);
    if (cases.size() != verified.native_applies)
        throw std::runtime_error("profile extraction operation count differs from exact baseline replay");
    replay_decoded(decoded_turns, initial, &trace);
    replay_decoded(decoded_turns, initial, &trace, false);
    std::cerr << "verified_input=" << path << " seed=" << trace.seed
              << " turns=" << verified.completed_turns << " native_actions=" << cases.size()
              << " exact_full_state_parity=yes\n";

    for (int repeat = 0; repeat < repeats; ++repeat) {
        const auto original = timed("original_full_turn_trace", "all_turns", repeat,
                                    iterations, iterations * cases.size(), [&] {
            std::uint64_t checksum = 0;
            for (std::uint64_t n = 0; n < iterations; ++n) {
                const ReplayStats replayed = replay(trace, initial, false);
                checksum += replayed.native_applies + replayed.completed_turns;
                barrier(checksum);
            }
            return checksum;
        });
        emit(original);

        for (std::size_t phase = 0; phase < states_by_phase.size(); ++phase) {
            const auto& states = states_by_phase[phase];
            const auto sample = timed("mask_generation", kPhaseNames[phase], repeat,
                                      iterations, iterations * states.size(), [&] {
                std::uint64_t checksum = 0;
                for (std::uint64_t n = 0; n < iterations; ++n) {
                    for (const auto& state : states) {
                        barrier_state(state);
                        const auto mask = getValidMoveMask(state);
                        barrier_array(mask);
                        checksum += static_cast<std::uint64_t>((n + checksum) & 1U);
                    }
                }
                return checksum;
            });
            emit(sample);
        }

        // Membership cost consumes precomputed masks. It does not include mask
        // generation or the direct validation already performed by applyMove.
        std::vector<std::array<int, 69>> masks;
        masks.reserve(cases.size());
        std::vector<int> action_indices;
        action_indices.reserve(cases.size());
        for (const auto& item : cases) {
            masks.push_back(getValidMoveMask(item.state));
            action_indices.push_back(moveToActionIndex(item.move));
        }
        const auto membership = timed("pregenerated_mask_membership", "all", repeat,
                                      iterations, iterations * cases.size(), [&] {
            std::uint64_t checksum = 0;
            for (std::uint64_t n = 0; n < iterations; ++n) {
                for (std::size_t i = 0; i < cases.size(); ++i) {
                    barrier_array(masks[i]);
                    const int index = action_indices[i];
                    const bool member = index >= 0 && index < 69 &&
                        masks[i][static_cast<std::size_t>(index)] != 0;
                    checksum += static_cast<std::uint64_t>(member);
                    barrier(checksum);
                }
            }
            return checksum;
        });
        emit(membership);

        // Ahin does not enumerate payment choices. The compatibility replay
        // checks that Rust's recorded payment matches its colored-first rule.
        const auto payment_check = timed("canonical_payment_check", "buy", repeat,
                                         iterations, iterations * payment_cases.size(), [&] {
            std::uint64_t checksum = 0;
            for (std::uint64_t n = 0; n < iterations; ++n) {
                for (const auto& item : payment_cases) {
                    const int p = item.state.current_player;
                    barrier_state(item.state);
                    const Card& purchased = item.buy.from_reserved
                        ? item.state.players[p].reserved.at(static_cast<std::size_t>(item.buy.card_slot)).card
                        : item.state.faceup[item.buy.card_tier][static_cast<std::size_t>(item.buy.card_slot)];
                    int gold = 0;
                    bool matches = true;
                    for (std::size_t color = 0; color < 5; ++color) {
                        const Color c = static_cast<Color>(color);
                        const int due = std::max(0, purchased.cost[c] - item.state.players[p].bonuses[c]);
                        const int colored = std::min(due, item.state.players[p].tokens[c]);
                        gold += due - colored;
                        matches = matches && item.expected_colored[color] == colored;
                    }
                    matches = matches && gold <= item.state.players[p].tokens.joker;
                    if (!matches) throw std::runtime_error("canonical payment differs from C++ payment rule");
                    checksum += static_cast<std::uint64_t>(gold + 1);
                    barrier(checksum ^ static_cast<std::uint64_t>(matches));
                }
            }
            return checksum;
        });
        emit(payment_check);

        // Matched loops make one-shot apply cost visible beside clone cost.
        const auto clone_only = timed("clone_only", "all", repeat,
                                      iterations, iterations * cases.size(), [&] {
            std::uint64_t checksum = 0;
            for (std::uint64_t n = 0; n < iterations; ++n) {
                for (const auto& item : cases) {
                    barrier_state(item.state);
                    GameState copy = item.state;
                    barrier_state(copy);
                    ++checksum;
                }
            }
            return checksum;
        });
        emit(clone_only);

        const auto clone_apply = timed("clone_plus_apply", "all", repeat,
                                       iterations, iterations * cases.size(), [&] {
            std::uint64_t checksum = 0;
            for (std::uint64_t n = 0; n < iterations; ++n) {
                for (const auto& item : cases) {
                    barrier_state(item.state);
                    GameState copy = item.state;
                    applyMove(copy, item.move);
                    barrier_state(copy);
                    ++checksum;
                }
            }
            return checksum;
        });
        emit(clone_apply);

        const auto full_trace = timed("predecoded_full_enum_apply", "all_turns", repeat,
                                      iterations, iterations * cases.size(), [&] {
            std::uint64_t checksum = 0;
            for (std::uint64_t n = 0; n < iterations; ++n) {
                checksum += replay_decoded(decoded_turns, initial);
                barrier(checksum);
            }
            return checksum;
        });
        emit(full_trace);
        const auto supplied = timed("predecoded_checked_apply_only", "all_turns", repeat,
                                    iterations, iterations * cases.size(), [&] {
            std::uint64_t checksum = 0;
            for (std::uint64_t n = 0; n < iterations; ++n) {
                checksum += replay_decoded(decoded_turns, initial, nullptr, false);
                barrier(checksum);
            }
            return checksum;
        });
        emit(supplied);
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc < 2) throw std::runtime_error(
            "usage: ahin_profile [--repeats N] [--iterations N] TRACE.txt [TRACE.txt ...]");
        int repeats = 5;
        std::uint64_t iterations = 1000;
        bool prepared_only = false;
        std::vector<const char*> paths;
        for (int i = 1; i < argc; ++i) {
            if (std::strcmp(argv[i], "--prepared-checked-only") == 0) {
                prepared_only = true;
            } else if (std::strcmp(argv[i], "--repeats") == 0 && i + 1 < argc) {
                repeats = std::stoi(argv[++i]);
            } else if (std::strcmp(argv[i], "--iterations") == 0 && i + 1 < argc) {
                iterations = std::stoull(argv[++i]);
            } else {
                paths.push_back(argv[i]);
            }
        }
        if (repeats < 1 || iterations < 1 || paths.empty())
            throw std::runtime_error("repeats and iterations must be positive and at least one trace is required");
        std::cout << "trace,profile,phase,repeat,iterations,operations,seconds,operations_per_second\n";
        for (const auto* path : paths) profile_trace(path, repeats, iterations, prepared_only);
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
