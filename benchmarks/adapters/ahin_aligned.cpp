// Benchmark-only seal256-intersection-v1 adapter. Upstream rules are unchanged.
#include "game_logic.h"
#include "json.hpp"
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>

using json = nlohmann::json;
using Clock = std::chrono::steady_clock;
static std::array<Move, 69> moves;
static std::vector<int> card_map, noble_map, card_inverse, noble_inverse;
static uint64_t next(uint64_t &s) {
    s += 0x9e3779b97f4a7c15ULL;
    uint64_t z = s;
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}
static json colors(const Tokens &t, int count = 6) {
    json row = json::array();
    for (int i = 0; i < count; ++i) row.push_back(t[static_cast<Color>(i)]);
    return row;
}
static json data() {
    json cards = json::array(), nobles = json::array();
    for (const auto &c : standardCards())
        cards.push_back({{"id", c.id - 1}, {"tier", c.level - 1},
                         {"bonus", static_cast<int>(c.color)},
                         {"points", c.points}, {"cost", colors(c.cost, 5)}});
    for (const auto &n : standardNobles())
        nobles.push_back({{"id", n.id - 1}, {"points", n.points},
                          {"cost", colors(n.requirements, 5)}});
    return {{"cards", cards}, {"nobles", nobles}};
}
static int card_id(const Card &c) { return card_inverse.at(c.id - 1); }
static GameState setup(const json &c) {
    GameState s{};
    s.bank = Tokens{4, 4, 4, 4, 4, 5};
    std::array<bool, 90> seen{};
    for (int t = 0; t < 3; ++t) {
        auto row = c.at("decks").at(t).get<std::vector<int>>();
        if (row.size() != std::array<size_t, 3>{40, 30, 20}[t])
            throw std::runtime_error("deck length");
        for (size_t i = 0; i < row.size(); ++i) {
            int id = row[i];
            if (id < 0 || id >= 90 || seen.at(id)) throw std::runtime_error("deck partition");
            seen[id] = true;
            const auto card = standardCards().at(card_map.at(id));
            if (card.level != t + 1) throw std::runtime_error("card tier");
            if (i < 4) s.faceup[t][i] = card;
        }
        for (int i = static_cast<int>(row.size()) - 1; i >= 4; --i)
            s.deck[t].push_back(standardCards().at(card_map.at(row[i])));
    }
    auto nobles = c.at("nobles").get<std::vector<int>>();
    if (nobles.size() != 3 || !std::is_sorted(nobles.begin(), nobles.end()) ||
        std::adjacent_find(nobles.begin(), nobles.end()) != nobles.end())
        throw std::runtime_error("noble setup");
    for (int i = 0; i < 3; ++i)
        s.available_nobles[i] = standardNobles().at(noble_map.at(nobles[i]));
    s.noble_count = 3;
    return s;
}
static json normalized(const GameState &s) {
    json players = json::array();
    for (const auto &p : s.players) {
        std::vector<int> reserved;
        for (const auto &r : p.reserved) reserved.push_back(card_id(r.card));
        std::sort(reserved.begin(), reserved.end());
        players.push_back({{"tokens", colors(p.tokens)}, {"bonuses", colors(p.bonuses, 5)},
                           {"score", p.points}, {"reserved", reserved}});
    }
    std::vector<int> market, remaining, nobles;
    for (int t = 0; t < 3; ++t) {
        for (const auto &c : s.faceup[t]) if (c.id) market.push_back(card_id(c));
        remaining.push_back(s.deck[t].size());
    }
    for (int i = 0; i < s.noble_count; ++i)
        nobles.push_back(noble_inverse.at(s.available_nobles[i].id - 1));
    std::sort(market.begin(), market.end()); std::sort(nobles.begin(), nobles.end());
    return {{"bank", colors(s.bank)}, {"players", players}, {"market", market},
            {"remaining", remaining}, {"nobles", nobles}, {"current", s.current_player},
            {"turns", s.move_number}, {"terminal", isGameOver(s)}};
}
struct Choice { int key; int native; };
static std::vector<Choice> choices(const GameState &s) {
    const auto mask = getValidMoveMask(s);
    const auto &p = s.players[s.current_player];
    std::vector<Choice> result;
    for (int i = 0; i < 69; ++i) {
        if (!mask[i]) continue;
        const auto &m = moves[i];
        int key = -1;
        if (m.type == BUY_CARD) {
            key = m.from_reserved ? 100 + card_id(p.reserved.at(m.card_slot).card)
                                  : card_id(s.faceup[m.card_tier][m.card_slot]);
        } else if (m.type == RESERVE_CARD && !m.from_deck &&
                   p.tokens.total() + (s.bank.joker > 0) <= 10) {
            key = 2000 + card_id(s.faceup[m.card_tier][m.card_slot]);
        } else if (m.type == TAKE_GEMS) {
            const int count = m.gems_taken.total();
            bool double_take = false;
            for (int c = 0; c < 5; ++c) double_take |= m.gems_taken[static_cast<Color>(c)] == 2;
            if (!((count == 3 && p.tokens.total() <= 7) ||
                  (count == 2 && double_take && p.tokens.total() < 8))) continue;
            key = 1000;
            int pow = 1;
            for (int c = 0; c < 5; ++c) { key += m.gems_taken[static_cast<Color>(c)] * pow; pow *= 3; }
        }
        if (key >= 0) result.push_back({key, i});
    }
    std::sort(result.begin(), result.end(), [](auto a, auto b) { return a.key < b.key; });
    return result;
}
static json game(GameState &s, const json &c, const std::string &policy, int cap, bool trace) {
    const auto start = Clock::now();
    uint64_t rng = c.at("policy_seed").get<uint64_t>();
    json history = json::array(), action_keys = json::array(), legal_keys = json::array();
    if (trace) history.push_back(normalized(s));
    std::string status = "decision_limit";
    while (s.move_number < cap) {
        if (isGameOver(s)) { status = "complete"; break; }
        auto legal = choices(s);
        if (trace) { json keys = json::array(); for (auto x : legal) keys.push_back(x.key); legal_keys.push_back(keys); }
        if (legal.empty()) {
            status = s.players[s.current_player].reserved.size() == 3 && s.bank.total() == s.bank.joker
                         ? "no_legal_action" : "profile_blocked";
            break;
        }
        size_t index = 0;
        if (policy == "random") {
            const uint64_t n = legal.size(), threshold = (uint64_t(0) - n) % n;
            uint64_t x; do { x = next(rng); } while (x < threshold);
            index = x % n;
        } else if (legal[0].key >= 1000) {
            bool found = false; int best = -1;
            for (size_t j = 0; j < legal.size() && legal[j].key < 2000; ++j) {
                int score = 0;
                for (int color = 0; color < 5; ++color)
                    score += moves[legal[j].native].gems_taken[static_cast<Color>(color)] *
                             (8 - s.players[s.current_player].tokens[static_cast<Color>(color)]);
                if (!found || score > best) { found = true; best = score; index = j; }
            }
        }
        const auto selected = legal[index]; const auto &m = moves[selected.native];
        if (m.type == BUY_CARD) {
            const auto &p = s.players[s.current_player];
            const auto card = m.from_reserved ? p.reserved.at(m.card_slot).card : s.faceup[m.card_tier][m.card_slot];
            int eligible = 0;
            for (int n = 0; n < s.noble_count; ++n) {
                bool ok = true;
                for (int color = 0; color < 5; ++color)
                    if (p.bonuses[static_cast<Color>(color)] + (static_cast<int>(card.color) == color) <
                        s.available_nobles[n].requirements[static_cast<Color>(color)]) ok = false;
                eligible += ok;
            }
            if (eligible >= 2) { status = "unsupported_noble_choice"; break; }
        }
        const int before = s.move_number;
        applyMove(s, m); // Upstream checks legality before mutation.
        if (s.is_return_phase || s.is_noble_choice_phase || s.move_number != before + 1)
            throw std::runtime_error("unsupported incomplete turn");
        if (trace) { action_keys.push_back(selected.key); history.push_back(normalized(s)); }
    }
    if (isGameOver(s)) status = "complete";
    const double elapsed = std::chrono::duration<double>(Clock::now() - start).count();
    json result = {{"seed", c.at("seed")}, {"status", status}, {"turns", s.move_number},
                   {"decisions", s.move_number}, {"latency_seconds", elapsed}};
    if (trace) { result["trace"] = history; result["action_keys"] = action_keys; result["legal_keys"] = legal_keys; }
    return result;
}
int main(int argc, char **argv) {
    try {
        std::string file, policy = "random"; bool trace = false; int cap = 20000;
        for (int i = 1; i < argc; ++i) {
            std::string flag = argv[i];
            if (flag == "--export-data") { std::cout << data().dump() << '\n'; return 0; }
            if (flag == "--trace") { trace = true; continue; }
            if (i + 1 == argc) throw std::runtime_error("missing argument");
            std::string value = argv[++i];
            if (flag == "--corpus") file = value;
            else if (flag == "--policy") policy = value;
            else if (flag == "--max-turns") cap = std::stoi(value);
            else if (flag == "--threads" && value == "1") {}
            else throw std::runtime_error("unsupported option");
        }
        if (file.empty() || (policy != "random" && policy != "fixed") || cap <= 0)
            throw std::runtime_error("invalid options");
        json corpus; std::ifstream input(file); input >> corpus;
        if (corpus.at("profile") != "seal256-intersection-v1") throw std::runtime_error("profile mismatch");
        card_map = corpus.at("ahin_core_to_native_cards").get<std::vector<int>>();
        noble_map = corpus.at("ahin_core_to_native_nobles").get<std::vector<int>>();
        auto invert = [](const auto &mapping, int length) {
            if (static_cast<int>(mapping.size()) != length) throw std::runtime_error("mapping length");
            std::vector<int> inverse(length, -1);
            for (int i = 0; i < length; ++i) {
                int value = mapping[i];
                if (value < 0 || value >= length || inverse[value] != -1) throw std::runtime_error("mapping permutation");
                inverse[value] = i;
            }
            return inverse;
        };
        card_inverse = invert(card_map, 90); noble_inverse = invert(noble_map, 10);
        for (int i = 0; i < 69; ++i) moves[i] = actionIndexToMove(i);
        const auto &cases = corpus.at("cases");
        if (!cases.empty()) { auto warmup = setup(cases[0]); game(warmup, cases[0], policy, cap, false); }
        std::vector<GameState> states; states.reserve(cases.size());
        for (const auto &c : cases) states.push_back(setup(c));
        std::vector<json> records(cases.size());
        const auto start = Clock::now();
        for (size_t i = 0; i < cases.size(); ++i) records[i] = game(states[i], cases[i], policy, cap, trace);
        const double seconds = std::chrono::duration<double>(Clock::now() - start).count();
        int complete = 0; uint64_t turns = 0;
        for (size_t i = 0; i < records.size(); ++i) {
            records[i]["final_state"] = normalized(states[i]);
            complete += records[i]["status"] == "complete";
            turns += states[i].move_number;
        }
        std::cout << json({{"engine", "ahinlendor"}, {"policy", policy}, {"threads", 1},
                           {"seconds", seconds}, {"count", cases.size()}, {"completed", complete},
                           {"turns", turns}, {"records", records},
                           {"timing_boundary", "prepared states; native mask, semantic projection, policy, checked apply, clocks and minimal JSON records; setup, snapshots and serialization excluded"}}).dump() << '\n';
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 3; }
}
