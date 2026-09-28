// Benchmark-only aligned profile. No external rule body is changed.
#include "splendor.h"
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <thread>
static std::vector<splendor::Action> cached_actions;
using json = nlohmann::json;
using State = splendor::SplendorGameState;
using Clock = std::chrono::steady_clock;
static std::vector<int> core_to_native_cards, native_to_core_cards,
    core_to_native_nobles, native_to_core_nobles;
static std::unordered_map<const splendor::Card *, int> pointer_to_core;
static std::vector<int> chance_actions;
static const int canonical_to_native[6] = {3, 2, 1, 0, 4, 5};
static uint64_t next(uint64_t &s) {
  s += 0x9e3779b97f4a7c15ULL;
  uint64_t z = s;
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
  return z ^ (z >> 31);
}
static int card_id(const splendor::Card *c) {
  if (!pointer_to_core.empty())
    return pointer_to_core.at(c);
  int off = 0;
  for (const auto &row : splendor::CARDS) {
    for (size_t i = 0; i < row.size(); ++i)
      if (c == &row[i])
        return native_to_core_cards.empty() ? off + i
                                            : native_to_core_cards.at(off + i);
    off += row.size();
  }
  throw std::runtime_error("unknowncard");
}
static const splendor::Card *card(int id) {
  if (!core_to_native_cards.empty())
    id = core_to_native_cards.at(id);
  if (id < 0 || id >= 90)
    throw std::runtime_error("cardid");
  return id < 40   ? &splendor::CARDS[0][id]
         : id < 70 ? &splendor::CARDS[1][id - 40]
                   : &splendor::CARDS[2][id - 70];
}
static int noble_id(const splendor::Noble *n) {
  int id = int(n - &splendor::NOBLES[0]);
  return native_to_core_nobles.empty() ? id : native_to_core_nobles.at(id);
}
static int action_named(const std::string &s) {
  auto i =
      std::find(splendor::ACTIONS_STR.begin(), splendor::ACTIONS_STR.end(), s);
  if (i == splendor::ACTIONS_STR.end())
    throw std::runtime_error("action");
  return i - splendor::ACTIONS_STR.begin();
}
static json colors(const splendor::GemSet &gems) {
  json x = json::array();
  for (int i : canonical_to_native)
    x.push_back(gems.gems[i]);
  return x;
}
static json ids(const std::vector<const splendor::Card *> &row, bool sort) {
  std::vector<int> x;
  for (auto c : row)
    x.push_back(card_id(c));
  if (sort)
    std::sort(x.begin(), x.end());
  return x;
}
static json normalized(const State &s, size_t turns) {
  json players = json::array();
  for (const auto &p : s.players) {
    players.push_back(
        {{"tokens", colors(p.gems)},
         {"bonuses", json::array({p.card_gems.gems[3], p.card_gems.gems[2],
                                  p.card_gems.gems[1], p.card_gems.gems[0],
                                  p.card_gems.gems[4]})},
         {"score", p.points},
         {"reserved", ids(p.hand_cards, true)}});
  }
  std::vector<int> market, nobles, remaining;
  for (int t = 0; t < 3; ++t) {
    for (auto c : s.cards[t])
      market.push_back(card_id(c));
    remaining.push_back(s.decks[t].size());
  }
  for (auto n : s.nobles)
    nobles.push_back(noble_id(n));
  std::sort(market.begin(), market.end());
  std::sort(nobles.begin(), nobles.end());
  return {{"bank", colors(s.gems)}, {"players", players},
          {"market", market},       {"remaining", remaining},
          {"nobles", nobles},       {"current", s.player_to_move},
          {"turns", turns},         {"terminal", s.is_terminal()}};
}

static State setup(const json &c) {
  State s(2);
  for (int t = 0; t < 3; ++t) {
    const auto row = c.at("decks").at(t).get<std::vector<int>>();
    if (row.size() != size_t(t == 0 ? 40 : t == 1 ? 30 : 20))
      throw std::runtime_error("decklength");
    s.cards[t].clear();
    s.decks[t].clear();
    std::vector<bool> seen(90, false);
    for (size_t i = 0; i < row.size(); ++i) {
      const int id = row[i];
      if (id < (t == 0   ? 0
                : t == 1 ? 40
                         : 70) ||
          id >= (t == 0   ? 40
                 : t == 1 ? 70
                          : 90) ||
          seen[id])
        throw std::runtime_error("deckpartition");
      seen[id] = true;
      if (i < 4)
        s.cards[t].push_back(card(id));
      else
        s.decks[t].push_back(card(id));
    }
    std::reverse(s.decks[t].begin(), s.decks[t].end());
  }
  s.nobles.clear();
  int previous = -1;
  for (int id : c.at("nobles").get<std::vector<int>>()) {
    if (id <= previous || id >= 10)
      throw std::runtime_error("noblesmustascending");
    previous = id;
    s.nobles.push_back(&splendor::NOBLES[core_to_native_nobles.empty()
                                             ? id
                                             : core_to_native_nobles.at(id)]);
  }
  if (s.nobles.size() != 3)
    throw std::runtime_error("noblecount");
  return s;
}
struct Choice {
  int key;
  int native;
};
static std::vector<Choice> choices(const State &s) {
  std::vector<Choice> result;
  for (int a : s.get_actions()) {
    const auto &spec = cached_actions.at(a);
    int key = -1;
    switch (spec.type) {
    case splendor::ActionType::PURCHASE:
      key = card_id(s.cards[spec.level][spec.pos]);
      break;
    case splendor::ActionType::PURCHASE_HAND:
      key = 100 + card_id(s.players[s.player_to_move].hand_cards[spec.pos]);
      break;
    case splendor::ActionType::TAKE: {
      key = 1000;
      int pow = 1;
      for (int i = 0; i < 5; ++i) {
        key += spec.gems.gems[canonical_to_native[i]] * pow;
        pow *= 3;
      }
      break;
    }
    case splendor::ActionType::RESERVE:
      if (s.players[s.player_to_move].gems.sum() + (s.gems.gems[5] > 0) > 10)
        continue;
      key = 2000 + card_id(s.cards[spec.level][spec.pos]);
      break;
    default:
      continue;
    }
    result.push_back({key, a});
  }
  std::sort(result.begin(), result.end(),
            [](auto a, auto b) { return a.key < b.key; });
  return result;
}
static json data() {
  json cards = json::array(), nobles = json::array();
  for (int id = 0; id < 90; ++id) {
    auto c = card(id);
    int bonus = 0;
    for (; bonus < 5 && canonical_to_native[bonus] != c->gem; ++bonus) {
    }
    auto cost = colors(c->price);
    cost.erase(5);
    cards.push_back({{"id", id},
                     {"tier", id < 40   ? 0
                              : id < 70 ? 1
                                        : 2},
                     {"bonus", bonus},
                     {"points", c->points},
                     {"cost", cost}});
  }
  for (int id = 0; id < 10; ++id) {
    auto cost = colors(splendor::NOBLES[id].price);
    cost.erase(5);
    nobles.push_back(
        {{"id", id}, {"cost", cost}, {"points", splendor::NOBLES[id].points}});
  }
  return {{"cards", cards}, {"nobles", nobles}};
}
static json game(State &s, const json &c, const std::string &policy, size_t cap,
                 bool trace) {
  const auto ready = Clock::now();
  uint64_t rng = c.value("policy_seed", c.at("seed").get<uint64_t>());
  size_t turns = 0, chance = 0;
  json history = json::array(), action_keys = json::array(),
       legal_keys = json::array();
  if (trace)
    history.push_back(normalized(s, 0));
  std::string status = "decision_limit";
  while (turns < cap) {
    if (s.is_terminal()) {
      status = "complete";
      break;
    }
    auto legal = choices(s);
    if (trace) {
      json keys = json::array();
      for (auto x : legal)
        keys.push_back(x.key);
      legal_keys.push_back(keys);
    }
    if (legal.empty()) {
      status = s.players[s.player_to_move].hand_cards.size() == 3 &&
                       s.gems.sum() == s.gems.gems[5]
                   ? "no_legal_action"
                   : "profile_blocked";
      break;
    }
    size_t i = 0;
    if (policy == "random") {
      const uint64_t n = legal.size(), threshold = (uint64_t(0) - n) % n;
      uint64_t x;
      do {
        x = next(rng);
      } while (x < threshold);
      i = x % n;
    } else if (legal[0].key >= 1000) {
      int best = -1;
      bool found = false;
      for (size_t j = 0; j < legal.size(); ++j) {
        if (legal[j].key >= 2000)
          break;
        const auto &a = cached_actions.at(legal[j].native);
        int score = 0;
        for (int c = 0; c < 5; ++c)
          score +=
              a.gems.gems[canonical_to_native[c]] *
              (8 -
               s.players[s.player_to_move].gems.gems[canonical_to_native[c]]);
        if (!found || score > best) {
          found = true;
          best = score;
          i = j;
        }
      }
    }
    const auto selected = legal[i];
    const auto &spec = cached_actions.at(selected.native);
    if (spec.type == splendor::ActionType::PURCHASE ||
        spec.type == splendor::ActionType::PURCHASE_HAND) {
      const auto c = spec.type == splendor::ActionType::PURCHASE
                         ? s.cards[spec.level][spec.pos]
                         : s.players[s.player_to_move].hand_cards[spec.pos];
      int eligible = 0;
      for (auto n : s.nobles) {
        bool ok = true;
        for (int gem = 0; gem < 5; ++gem)
          if (s.players[s.player_to_move].card_gems.gems[gem] +
                  (gem == c->gem) <
              n->price.gems[gem])
            ok = false;
        eligible += ok;
      }
      if (eligible >= 2) {
        status = "unsupported_noble_choice";
        break;
      }
    }
    if (!s.verify_action(selected.native).first)
      throw std::runtime_error("invalidprofileaction");
    s.apply_action(selected.native);
    if (s.table_card_needed) {
      const int a = chance_actions.at(s.decks[s.deck_level].size() - 1);
      if (!s.verify_action(a).first)
        throw std::runtime_error("invalidchance");
      s.apply_action(a);
      ++chance;
    }
    ++turns;
    if (trace) {
      action_keys.push_back(selected.key);
      history.push_back(normalized(s, turns));
    }
  }
  if (s.is_terminal())
    status = "complete";
  const auto end = Clock::now();
  json result = {
      {"seed", c.at("seed")},
      {"status", status},
      {"turns", turns},
      {"chance_transitions", chance},
      {"setup_seconds", 0.0},
      {"play_seconds", std::chrono::duration<double>(end - ready).count()},
      {"latency_seconds", std::chrono::duration<double>(end - ready).count()},
      {"decisions", turns + chance}};
  if (trace) {
    result["trace"] = history;
    result["action_keys"] = action_keys;
    result["legal_keys"] = legal_keys;
  }
  return result;
}
int main(int argc, char **argv) {
  try {
    std::string file, policy = "random";
    size_t threads = 1, cap = 20000, repetitions = 1;
    bool trace = false;
    for (int i = 1; i < argc; ++i) {
      std::string k = argv[i];
      if (k == "--export-data") {
        std::cout << data().dump() << '\n';
        return 0;
      }
      if (k == "--trace") {
        trace = true;
        continue;
      }
      if (i + 1 >= argc)
        return 2;
      std::string v = argv[++i];
      if (k == "--corpus")
        file = v;
      else if (k == "--policy")
        policy = v;
      else if (k == "--threads")
        threads = std::stoull(v);
      else if (k == "--max-turns")
        cap = std::stoull(v);
      else if (k == "--repetitions")
        repetitions = std::stoull(v);
      else
        return 2;
    }
    if (file.empty() || !threads || (policy != "fixed" && policy != "random"))
      return 2;
    std::ifstream in(file);
    json corpus;
    in >> corpus;
    core_to_native_cards =
        corpus.at("core_to_native_cards").get<std::vector<int>>();
    core_to_native_nobles =
        corpus.at("core_to_native_nobles").get<std::vector<int>>();
    if (core_to_native_cards.size() != 90 || core_to_native_nobles.size() != 10)
      throw std::runtime_error("mappinglength");
    native_to_core_cards.assign(90, -1);
    native_to_core_nobles.assign(10, -1);
    for (int i = 0; i < 90; ++i) {
      int n = core_to_native_cards[i];
      if (n < 0 || n >= 90 || native_to_core_cards[n] >= 0)
        throw std::runtime_error("cardmapping");
      native_to_core_cards[n] = i;
    }
    for (int i = 0; i < 10; ++i) {
      int n = core_to_native_nobles[i];
      if (n < 0 || n >= 10 || native_to_core_nobles[n] >= 0)
        throw std::runtime_error("noblemapping");
      native_to_core_nobles[n] = i;
    }
    // Native ACTIONS has internal linkage; cache identical native descriptors
    // once.
    for (const auto &text : splendor::ACTIONS_STR)
      cached_actions.push_back(splendor::Action::from_str(text));
    pointer_to_core.reserve(90);
    for (int id = 0; id < 90; ++id)
      pointer_to_core.emplace(card(id), id);
    for (int i = 0; i < 40; ++i)
      chance_actions.push_back(action_named("c" + std::to_string(i)));
    auto cases = corpus.at("cases");
    const auto warmup_start = Clock::now();
    if (!cases.empty()) {
      auto state = setup(cases[0]);
      game(state, cases[0], policy, cap, false);
    }
    const double warmup_seconds =
        std::chrono::duration<double>(Clock::now() - warmup_start).count();
    for (size_t repetition = 0; repetition < repetitions; ++repetition) {
      std::vector<json> records(cases.size());
      const auto setup_start = Clock::now();
      std::vector<State> bases;
      bases.reserve(cases.size());
      std::vector<double> setup_times;
      for (const auto &c : cases) {
        const auto s = Clock::now();
        bases.push_back(setup(c));
        setup_times.push_back(
            std::chrono::duration<double>(Clock::now() - s).count());
      }
      const auto setup_end =
          Clock::now(); // Inject all fixture state before timed play.
      std::mutex lock;
      std::condition_variable cv;
      size_t ready = 0;
      bool go = false;
      std::vector<std::thread> workers;
      for (size_t t = 0; t < threads; ++t)
        workers.emplace_back([&, t] {
          {
            std::unique_lock<std::mutex> hold(lock);
            ++ready;
            cv.notify_all();
            cv.wait(hold, [&] { return go; });
          }
          for (size_t i = t; i < cases.size(); i += threads)
            records[i] = game(bases[i], cases[i], policy, cap, trace);
        });
      {
        std::unique_lock<std::mutex> hold(lock);
        cv.wait(hold, [&] { return ready == threads; });
      }
      auto start = Clock::now();
      {
        std::lock_guard<std::mutex> hold(lock);
        go = true;
      }
      cv.notify_all();
      for (auto &w : workers)
        w.join();
      double elapsed =
          std::chrono::duration<double>(Clock::now() - start).count();
      for (size_t i = 0; i < records.size(); ++i) {
        records[i]["setup_seconds"] = setup_times[i];
        records[i]["final_state"] =
            normalized(bases[i], records[i]["turns"].get<size_t>());
      }
      size_t completed = 0, blocked = 0, capped = 0, unsupported = 0,
             no_action = 0, turns = 0;
      double setup_s = 0, play_s = 0;
      for (auto &r : records) {
        completed += r["status"] == "complete";
        blocked += r["status"] == "profile_blocked";
        capped += r["status"] == "decision_limit";
        unsupported += r["status"] == "unsupported_noble_choice";
        no_action += r["status"] == "no_legal_action";
        turns += r["turns"].get<size_t>();
        setup_s += r["setup_seconds"].get<double>();
        play_s += r["play_seconds"].get<double>();
      }
      std::cout
          << json({{"engine", "seal256"},
                   {"profile",
                    corpus.value("profile",
                                 std::string("seal256-intersection-v1"))},
                   {"repetition", repetition},
                   {"warmup_seconds", warmup_seconds},
                   {"policy", policy},
                   {"threads", threads},
                   {"elapsed_seconds", elapsed},
                   {"setup_seconds",
                    std::chrono::duration<double>(setup_end - setup_start)
                        .count()},
                   {"thread_pool_startup_seconds",
                    std::chrono::duration<double>(start - setup_end).count()},
                   {"timing_boundary",
                    "prepared states; legal generation, profile projection, "
                    "policy, checked native transitions, clocks and minimal "
                    "record collection; setup, worker creation, final "
                    "snapshots, serialization excluded"},
                   {"trace_enabled", trace},
                   {"games", records.size()},
                   {"completed", completed},
                   {"profile_blocked", blocked},
                   {"decision_limit", capped},
                   {"unsupported_noble_choice", unsupported},
                   {"no_legal_action", no_action},
                   {"main_turns", turns},
                   {"per_game_setup_seconds_sum", setup_s},
                   {"per_game_play_seconds_sum", play_s},
                   {"records", records}})
                 .dump()
          << '\n';
    }
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 3;
  }
}
