#include "game_logic.h"
#include "state_encoder.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {
constexpr std::size_t kBatch = 512;
constexpr std::size_t kOps = 80000;
constexpr std::size_t kRepeats = 3;
volatile std::uint64_t sink = 0;

std::vector<std::string> split(const std::string& line, char delim) {
    std::vector<std::string> out;
    std::stringstream ss(line);
    std::string item;
    while (std::getline(ss, item, delim)) out.push_back(item);
    return out;
}

std::vector<int> ints(const std::string& value) {
    std::vector<int> out;
    if (value.empty()) return out;
    for (const auto& part : split(value, ',')) out.push_back(std::stoi(part));
    return out;
}

Tokens tokens(const std::vector<int>& x, std::size_t offset = 0) {
    if (x.size() == offset + 5) return {x[offset], x[offset + 1], x[offset + 2], x[offset + 3], x[offset + 4], 0};
    if (x.size() < offset + 6) throw std::runtime_error("short token vector");
    return {x[offset], x[offset + 1], x[offset + 2], x[offset + 3], x[offset + 4], x[offset + 5]};
}

Card card(int id) {
    if (id <= 0) return Card{};
    const auto& all = standardCards();
    if (static_cast<std::size_t>(id) > all.size()) throw std::runtime_error("bad card ID");
    return all[static_cast<std::size_t>(id - 1)];
}

Noble noble(int id) {
    if (id <= 0 || id > 10) throw std::runtime_error("bad noble ID");
    return standardNobles()[static_cast<std::size_t>(id - 1)];
}

struct Fixture {
    std::string tag;
    int viewer = 0;
    int current = 0;
    int turns = 0;
    int final_round = 0;
    std::array<int, 6> bank{};
    std::array<int, 12> market{};
    std::array<int, 3> remaining{};
    std::vector<int> nobles;
    std::array<Tokens, 2> player_tokens{};
    std::array<Tokens, 2> player_bonuses{};
    std::array<int, 2> points{};
    std::array<std::vector<int>, 2> owned{};
    std::array<std::vector<int>, 2> player_nobles{};
    std::array<std::vector<std::array<int, 3>>, 2> reserved{};
    std::array<std::vector<int>, 3> deck{};
    std::array<int, 3> next_card{-1, -1, -1};
    std::array<int, 2> refill{-1, -1};
    std::array<int, 5> take{};
    std::uint64_t expected_digest = 0;
    std::uint64_t expected_after_take = 0;
};

std::vector<Fixture> read_fixtures(const char* path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open fixture file");
    std::vector<Fixture> fixtures;
    Fixture* current = nullptr;
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line[0] == '#') continue;
        auto p = split(line, '|');
        if (p[0] == "STATE") {
            fixtures.emplace_back();
            current = &fixtures.back();
            current->tag = p.at(1);
            current->viewer = std::stoi(p.at(2));
            current->current = std::stoi(p.at(3));
            current->turns = std::stoi(p.at(4));
            current->final_round = std::stoi(p.at(5));
            auto bank = ints(p.at(6)), market = ints(p.at(7)), rem = ints(p.at(8));
            if (bank.size() != 6 || market.size() != 12 || rem.size() != 3) throw std::runtime_error("bad state vectors");
            std::copy(bank.begin(), bank.end(), current->bank.begin());
            std::copy(market.begin(), market.end(), current->market.begin());
            std::copy(rem.begin(), rem.end(), current->remaining.begin());
            current->nobles = ints(p.at(9));
        } else if (p[0] == "PLAYER") {
            if (!current) throw std::runtime_error("player without state");
            int seat = std::stoi(p.at(1));
            if (seat < 0 || seat > 1) throw std::runtime_error("bad seat");
            auto tok = ints(p.at(2)), bonus = ints(p.at(3));
            current->player_tokens[seat] = tokens(tok);
            current->player_bonuses[seat] = tokens(bonus);
            current->points[seat] = std::stoi(p.at(4));
            current->owned[seat] = ints(p.at(5));
            current->player_nobles[seat] = ints(p.at(6));
            int count = std::stoi(p.at(7));
            std::size_t i = 8;
            for (int j = 0; j < count; ++j) {
                current->reserved[seat].push_back({std::stoi(p.at(i)), std::stoi(p.at(i + 1)), std::stoi(p.at(i + 2))});
                i += 3;
            }
        } else if (p[0] == "DECK") {
            int tier = std::stoi(p.at(1));
            auto ids = ints(p.at(2));
            // Rust next draw is pool[remaining - 1]; vector::back() is that card.
            current->deck.at(static_cast<std::size_t>(tier)) = std::move(ids);
        } else if (p[0] == "NEXT") {
            current->next_card.at(static_cast<std::size_t>(std::stoi(p.at(1)))) = std::stoi(p.at(2));
        } else if (p[0] == "REFILL") {
            current->refill = {std::stoi(p.at(1)), std::stoi(p.at(2))};
        } else if (p[0] == "DIGEST") {
            current->expected_digest = std::stoull(p.at(1), nullptr, 16);
        } else if (p[0] == "AFTER_TAKE") {
            current->expected_after_take = std::stoull(p.at(1), nullptr, 16);
        } else if (p[0] == "ACTION") {
            auto a = ints(p.at(1));
            if (a.size() != 5) throw std::runtime_error("bad TAKE action");
            std::copy(a.begin(), a.end(), current->take.begin());
        } else if (p[0] == "END") {
            current = nullptr;
        } else if (p[0] != "CARD" && p[0] != "NOBLE") {
            throw std::runtime_error("unknown fixture record");
        }
    }
    return fixtures;
}

void verify_catalog(const char* path) {
    std::ifstream input(path);
    std::array<bool, 90> cards_seen{};
    std::array<bool, 10> nobles_seen{};
    std::array<bool, 10> canonical_nobles_seen{};
    constexpr std::array<int, 10> canonical_to_ahin{9, 8, 10, 6, 7, 5, 4, 2, 3, 1};
    int card_count = 0, noble_count = 0;
    for (std::string line; std::getline(input, line);) {
        auto p = split(line, '|');
        if (p[0] == "CARD") {
            const int id = std::stoi(p.at(1));
            const int tier = std::stoi(p.at(2));
            const int bonus = std::stoi(p.at(3));
            const int points = std::stoi(p.at(4));
            const auto cost = ints(p.at(5));
            const auto& c = standardCards().at(static_cast<std::size_t>(id - 1));
            if (id < 1 || id > 90 || cards_seen[static_cast<std::size_t>(id - 1)] ||
                c.id != id || c.level != tier || static_cast<int>(c.color) != bonus || c.points != points ||
                cost.size() != 5 || c.cost.white != cost[0] || c.cost.blue != cost[1] ||
                c.cost.green != cost[2] || c.cost.red != cost[3] || c.cost.black != cost[4]) {
                throw std::runtime_error("card signature mismatch at ID " + std::to_string(id));
            }
            cards_seen[static_cast<std::size_t>(id - 1)] = true;
            ++card_count;
        } else if (p[0] == "NOBLE") {
            const int canonical_id = std::stoi(p.at(1));
            const int ahin_id = std::stoi(p.at(2));
            const auto req = ints(p.at(3));
            const auto& n = standardNobles().at(static_cast<std::size_t>(ahin_id - 1));
            if (canonical_id < 0 || canonical_id >= 10 || ahin_id < 1 || ahin_id > 10 ||
                nobles_seen[static_cast<std::size_t>(ahin_id - 1)] || req.size() != 5 ||
                canonical_nobles_seen[static_cast<std::size_t>(canonical_id)] ||
                canonical_to_ahin[static_cast<std::size_t>(canonical_id)] != ahin_id ||
                n.id != ahin_id || n.requirements.white != req[0] || n.requirements.blue != req[1] ||
                n.requirements.green != req[2] || n.requirements.red != req[3] || n.requirements.black != req[4]) {
                throw std::runtime_error("noble signature mismatch");
            }
            nobles_seen[static_cast<std::size_t>(ahin_id - 1)] = true;
            canonical_nobles_seen[static_cast<std::size_t>(canonical_id)] = true;
            ++noble_count;
        }
    }
    if (card_count != 90 || noble_count != 10 ||
        !std::all_of(cards_seen.begin(), cards_seen.end(), [](bool x) { return x; }) ||
        !std::all_of(nobles_seen.begin(), nobles_seen.end(), [](bool x) { return x; }) ||
        !std::all_of(canonical_nobles_seen.begin(), canonical_nobles_seen.end(), [](bool x) { return x; })) {
        throw std::runtime_error("incomplete card/noble signature catalog");
    }
}

GameState materialize(const Fixture& f) {
    GameState s{};
    s.bank = tokens(std::vector<int>(f.bank.begin(), f.bank.end()));
    s.current_player = f.current;
    s.move_number = f.turns;
    s.noble_count = static_cast<int>(f.nobles.size());
    for (int i = 0; i < s.noble_count; ++i) s.available_nobles[static_cast<std::size_t>(i)] = noble(f.nobles[static_cast<std::size_t>(i)]);
    for (int i = 0; i < 12; ++i) s.faceup[i / 4][static_cast<std::size_t>(i % 4)] = card(f.market[static_cast<std::size_t>(i)]);
    for (int tier = 0; tier < 3; ++tier) {
        for (int id : f.deck[static_cast<std::size_t>(tier)]) s.deck[tier].push_back(card(id));
        if (static_cast<int>(s.deck[tier].size()) != f.remaining[static_cast<std::size_t>(tier)]) throw std::runtime_error("deck size does not match remaining");
    }
    for (int seat = 0; seat < 2; ++seat) {
        auto& p = s.players[seat];
        p.tokens = f.player_tokens[seat];
        p.bonuses = f.player_bonuses[seat];
        p.points = f.points[seat];
        for (int id : f.owned[seat]) p.cards.push_back(card(id));
        for (int id : f.player_nobles[seat]) p.nobles.push_back(noble(id));
        for (auto r : f.reserved[seat]) {
            const Card reserved_card = card(r[0]);
            if (reserved_card.level - 1 != r[1]) throw std::runtime_error("reserved card tier mismatch");
            p.reserved.push_back({reserved_card, r[2] != 0});
        }
    }
    return s;
}

void digest_feed(std::uint64_t& hash, std::uint64_t value) {
    hash = (hash ^ value) * 0x100000001b3ULL;
}

std::uint64_t material_digest(const Fixture& f, const GameState& s) {
    std::uint64_t hash = 0xcbf29ce484222325ULL;
    std::uint64_t phase = s.is_return_phase ? 1 : s.is_noble_choice_phase ? 2 : isGameOver(s) ? 4 : 0;
    for (std::uint64_t value : {2ULL, static_cast<std::uint64_t>(f.viewer), static_cast<std::uint64_t>(s.current_player),
                                static_cast<std::uint64_t>(s.move_number), static_cast<std::uint64_t>(s.players[0].points >= 15 || s.players[1].points >= 15), phase}) {
        digest_feed(hash, value);
    }
    for (Color color : {Color::White, Color::Blue, Color::Green, Color::Red, Color::Black, Color::Joker}) digest_feed(hash, s.bank[color]);
    for (int tier = 0; tier < 3; ++tier) for (const auto& c : s.faceup[tier]) digest_feed(hash, static_cast<std::uint64_t>(c.id));
    for (int tier = 0; tier < 3; ++tier) digest_feed(hash, s.deck[tier].size());
    digest_feed(hash, static_cast<std::uint64_t>(s.noble_count));
    for (int i = 0; i < s.noble_count; ++i) digest_feed(hash, static_cast<std::uint64_t>(s.available_nobles[static_cast<std::size_t>(i)].id));
    for (int seat = 0; seat < 2; ++seat) {
        const auto& p = s.players[seat];
        for (Color color : {Color::White, Color::Blue, Color::Green, Color::Red, Color::Black, Color::Joker}) digest_feed(hash, p.tokens[color]);
        for (Color color : {Color::White, Color::Blue, Color::Green, Color::Red, Color::Black}) digest_feed(hash, p.bonuses[color]);
        digest_feed(hash, static_cast<std::uint64_t>(p.points));
        digest_feed(hash, p.cards.size());
        for (const auto& c : p.cards) digest_feed(hash, static_cast<std::uint64_t>(c.id));
        digest_feed(hash, p.nobles.size());
        for (const auto& n : p.nobles) digest_feed(hash, static_cast<std::uint64_t>(n.id));
        digest_feed(hash, p.reserved.size());
        for (const auto& r : p.reserved) {
            digest_feed(hash, static_cast<std::uint64_t>(r.card.id));
            digest_feed(hash, static_cast<std::uint64_t>(r.card.level - 1));
            digest_feed(hash, static_cast<std::uint64_t>(r.is_public));
        }
    }
    for (int tier = 0; tier < 3; ++tier) {
        const auto& deck = s.deck[tier];
        digest_feed(hash, deck.size());
        for (const auto& c : deck) digest_feed(hash, static_cast<std::uint64_t>(c.id));
    }
    // The sampled deck arrays are serialized in Rust draw-stack order, which is the vector order here.
    return hash;
}

void verify_material(const GameState& s) {
    std::array<bool, 90> seen_cards{};
    std::array<bool, 10> seen_nobles{};
    std::array<int, 6> held{};
    auto see_card = [&](const Card& c, int tier) {
        if (c.id < 1 || c.id > 90 || seen_cards[static_cast<std::size_t>(c.id - 1)] ||
            c.level != tier + 1) throw std::runtime_error("invalid/duplicate card in materialized world");
        seen_cards[static_cast<std::size_t>(c.id - 1)] = true;
    };
    for (int tier = 0; tier < 3; ++tier) {
        for (const auto& c : s.faceup[tier]) if (c.id != 0) see_card(c, tier);
        for (const auto& c : s.deck[tier]) see_card(c, tier);
    }
    int selected_nobles = s.noble_count;
    for (int i = 0; i < s.noble_count; ++i) {
        const int id = s.available_nobles[static_cast<std::size_t>(i)].id;
        if (id < 1 || id > 10 || seen_nobles[static_cast<std::size_t>(id - 1)]) throw std::runtime_error("duplicate available noble");
        seen_nobles[static_cast<std::size_t>(id - 1)] = true;
    }
    for (const auto& p : s.players) {
        int score = 0;
        std::array<int, 5> bonuses{};
        for (const auto& c : p.cards) {
            see_card(c, c.level - 1);
            ++bonuses[static_cast<std::size_t>(c.color)];
            score += c.points;
        }
        for (int color = 0; color < 5; ++color) if (p.bonuses[static_cast<Color>(color)] != bonuses[static_cast<std::size_t>(color)]) throw std::runtime_error("bonus/card material mismatch");
        if (p.reserved.size() > 3 || p.tokens.total() > 10) throw std::runtime_error("invalid hand/reservation material");
        for (const auto& r : p.reserved) see_card(r.card, r.card.level - 1);
        for (const auto& n : p.nobles) {
            if (n.id < 1 || n.id > 10 || seen_nobles[static_cast<std::size_t>(n.id - 1)]) throw std::runtime_error("duplicate claimed noble");
            seen_nobles[static_cast<std::size_t>(n.id - 1)] = true;
            score += n.points;
            ++selected_nobles;
        }
        if (score != p.points) throw std::runtime_error("score/card/noble material mismatch");
        held[0] += p.tokens.white; held[1] += p.tokens.blue; held[2] += p.tokens.green;
        held[3] += p.tokens.red; held[4] += p.tokens.black; held[5] += p.tokens.joker;
    }
    for (int color = 0; color < 5; ++color) held[static_cast<std::size_t>(color)] += s.bank[static_cast<Color>(color)];
    held[5] += s.bank.joker;
    if (held != std::array<int, 6>{4, 4, 4, 4, 4, 5}) throw std::runtime_error("token conservation mismatch");
    if (selected_nobles != 3 || !std::all_of(seen_cards.begin(), seen_cards.end(), [](bool x) { return x; })) {
        throw std::runtime_error("card/noble inventory is incomplete");
    }
}

void barrier(const GameState& state) {
    sink += static_cast<std::uint64_t>(state.current_player + state.bank.total() + state.players[0].points + state.faceup[0][0].id);
    asm volatile("" : : "g"(&state) : "memory");
}

void read_barrier(const GameState& state) {
    asm volatile("" : : "g"(&state) : "memory");
}

void consume_moves(const std::vector<Move>& actions) {
    asm volatile("" : : "g"(actions.data()), "g"(actions.size()) : "memory");
}

template<class F> void timed(const Fixture& f, const std::string& name, std::size_t ops, F&& fn) {
    for (std::size_t repeat = 0; repeat < kRepeats; ++repeat) {
        const auto start = std::chrono::steady_clock::now();
        for (std::size_t i = 0; i < ops; ++i) fn();
        const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        std::cout << "ahin," << f.tag << ',' << name << ',' << repeat << ',' << ops << ',' << seconds << ',' << (ops / seconds) << '\n';
    }
}

void run(const Fixture& f) {
    const GameState base = materialize(f);
    verify_material(base);
    const auto actual_digest = material_digest(f, base);
    if (actual_digest != f.expected_digest) throw std::runtime_error("Rust/C++ material digest mismatch in " + f.tag);
    if (f.tag == "start") {
        for (int tier = 0; tier < 3; ++tier) {
            if (f.next_card[static_cast<std::size_t>(tier)] <= 0) throw std::runtime_error("missing next-draw proof");
            GameState probe = base;
            Move reserve{};
            reserve.type = RESERVE_CARD;
            reserve.from_deck = true;
            reserve.card_tier = tier;
            applyMove(probe, reserve);
            if (probe.players[f.current].reserved.back().card.id != f.next_card[static_cast<std::size_t>(tier)]) {
                throw std::runtime_error("sampled Rust/C++ next-deck order mismatch");
            }
        }
        std::cerr << "# reserve-deck probes match all three sampled tier tops\n";
    }
    if (f.refill[0] >= 0) {
        GameState probe = base;
        Move buy{};
        buy.type = BUY_CARD;
        buy.card_tier = f.refill[0] / 4;
        buy.card_slot = f.refill[0] % 4;
        applyMove(probe, buy);
        if (probe.faceup[buy.card_tier][static_cast<std::size_t>(buy.card_slot)].id != f.refill[1]) {
            throw std::runtime_error("sampled Rust/C++ buy refill order mismatch");
        }
        std::cerr << "# buy-refill probe matches sampled next card for " << f.tag << '\n';
    }
    Move take{};
    take.type = TAKE_GEMS;
    take.gems_taken = {f.take[0], f.take[1], f.take[2], f.take[3], f.take[4], 0};
    const auto legal = findAllValidMoves(base);
    const auto matching_take = std::find_if(legal.begin(), legal.end(), [&](const Move& m) {
        return m.type == TAKE_GEMS && m.gems_taken.white == take.gems_taken.white &&
               m.gems_taken.blue == take.gems_taken.blue && m.gems_taken.green == take.gems_taken.green &&
               m.gems_taken.red == take.gems_taken.red && m.gems_taken.black == take.gems_taken.black;
    });
    if (matching_take == legal.end()) throw std::runtime_error("fixture TAKE is not legal in C++ state");
    GameState after_take = base;
    applyMove(after_take, take);
    if (material_digest(f, after_take) != f.expected_after_take) throw std::runtime_error("post-TAKE material/phase mismatch in " + f.tag);
    int take_count = 0;
    for (const auto& m : legal) if (m.type == TAKE_GEMS) ++take_count;
    std::cerr << "# ahin state=" << f.tag << " legal_actions=" << legal.size() << " take_actions=" << take_count << '\n';
    timed(f, "clone", kOps, [&] { read_barrier(base); GameState copy = base; barrier(copy); });
    timed(f, "legal_actions", kOps / 4, [&] {
        read_barrier(base);
        auto actions = findAllValidMoves(base);
        consume_moves(actions);
    });
    timed(f, "terminal", kOps, [&] { read_barrier(base); sink += static_cast<std::uint64_t>(isGameOver(base)); });
    timed(f, "observation", kOps / 4, [&] {
        read_barrier(base);
        auto raw = state_encoder::build_raw_state_for_observer(base, f.viewer);
        std::uint64_t checksum = 0;
        for (std::size_t i = 0; i < raw.size(); ++i) checksum = checksum * 257 + static_cast<std::uint64_t>(raw[i] + 1);
        sink += checksum;
    });
    std::vector<GameState> states(kBatch, base);
    for (std::size_t repeat = 0; repeat < kRepeats; ++repeat) {
        double apply_seconds = 0.0;
        for (std::size_t batch = 0; batch < kBatch; ++batch) {
            for (auto& s : states) s = base;
            const auto apply_start = std::chrono::steady_clock::now();
            for (auto& s : states) { applyMove(s, take); barrier(s); }
            apply_seconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - apply_start).count();
        }
        std::cout << "ahin," << f.tag << ",apply_take," << repeat << ',' << (kBatch * kBatch) << ',' << apply_seconds << ',' << ((kBatch * kBatch) / apply_seconds) << '\n';
    }
    timed(f, "clone_apply_take", kOps / 4, [&] { read_barrier(base); GameState copy = base; applyMove(copy, take); barrier(copy); });
    timed(f, "tree_expand_take", kOps / 8, [&] {
        read_barrier(base);
        GameState copy = base;
        auto actions = findAllValidMoves(copy);
        consume_moves(actions);
        applyMove(copy, take);
        barrier(copy);
    });
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: ahin_bench FIXTURES.txt");
        verify_catalog(argv[1]);
        auto fixtures = read_fixtures(argv[1]);
        if (fixtures.size() != 4) throw std::runtime_error("expected start, mid, late, and refill fixtures");
        std::cout << "engine,state,case,repeat,operations,seconds,ops_per_second\n";
        for (const auto& f : fixtures) run(f);
        std::cerr << "# anti-optimization sink=" << sink << '\n';
    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << '\n';
        return 1;
    }
}
