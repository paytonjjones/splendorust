// Interface-only harness. The external engine source is not changed.
#include "splendor.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <mutex>
#include <thread>
using Clock = std::chrono::steady_clock;
using splendor::SplendorGameState;
static nlohmann::json normalized(const SplendorGameState &s) {
  nlohmann::json p = nlohmann::json::array();
  for (const auto &x : s.players)
    p.push_back({{"tokens", x.gems.gems},
                 {"bonuses", x.card_gems.gems},
                 {"score", x.points},
                 {"reserved", x.hand_cards.size()}});
  return {{"color_order", "red,green,blue,white,black,gold"},
          {"bank", s.gems.gems},
          {"players", p},
          {"active_player", s.active_player()},
          {"round", s.round},
          {"nobles_available", s.nobles.size()},
          {"win_points", s.rules->win_points},
          {"chance_pending", s.table_card_needed}};
}
int main(int argc, char **argv) {
  const auto start = Clock::now();
  size_t iterations = 100000, threads = 1;
  unsigned seed = 12345;
  for (int i = 1; i < argc; ++i) {
    const std::string key = argv[i];
    if (i + 1 >= argc)
      return 2;
    const auto value = std::stoull(argv[++i]);
    if (key == "--iterations")
      iterations = value;
    else if (key == "--threads")
      threads = value;
    else if (key == "--seed")
      seed = value;
    else
      return 2;
  }
  if (!iterations || !threads || threads > iterations)
    return 2;
  std::srand(
      seed); // Used only for one initial setup; no RNG in the timed take.
  const SplendorGameState base(2);
  if (base.gems.gems != std::array<int, 6>{4, 4, 4, 4, 4, 5} ||
      base.players.size() != 2 || base.player_to_move != 0 || base.round != 0 ||
      base.nobles.size() != 3 || base.rules->win_points != 15)
    return 3;
  for (const auto &p : base.players)
    if (p.gems.sum() || p.card_gems.sum() || p.points || !p.hand_cards.empty())
      return 3;
  const int action = 12; // tg1b1w1, verified below; no purchase/refill/chance.
  if (splendor::ACTIONS_STR.at(action) != "tg1b1w1")
    return 3;
  const auto legal = base.get_actions();
  if (std::find(legal.begin(), legal.end(), action) == legal.end())
    return 3;
  auto check_ptr = base.clone();
  auto &check = static_cast<SplendorGameState &>(*check_ptr);
  if (!check.verify_action(action).first)
    return 3;
  check.apply_action(action);
  if (check.cards != base.cards || check.decks != base.decks ||
      check.nobles != base.nobles)
    return 3;
  if (check.gems.gems != std::array<int, 6>{4, 3, 3, 3, 4, 5} ||
      check.players[0].gems.gems != std::array<int, 6>{0, 1, 1, 1, 0, 0} ||
      check.player_to_move != 1 || check.round != 0 ||
      check.table_card_needed || check.nobles.size() != 3)
    return 3;
  std::mutex mutex;
  std::condition_variable cv;
  size_t ready = 0;
  bool go = false;
  std::vector<uint64_t> sums(threads, 0);
  std::vector<std::thread> workers;
  for (size_t t = 0; t < threads; ++t)
    workers.emplace_back([&, t] {
      // Warm-up outside the measured interval.
      for (size_t i = 0; i < 1000; ++i) {
        auto x = base.clone();
        x->apply_action(action);
      }
      {
        std::unique_lock<std::mutex> lock(mutex);
        ++ready;
        cv.notify_all();
        cv.wait(lock, [&] { return go; });
      }
      const size_t count = iterations / threads + (t < iterations % threads);
      for (size_t i = 0; i < count; ++i) {
        auto x = base.clone();
        if (!static_cast<SplendorGameState &>(*x).verify_action(action).first)
          std::abort();
        x->apply_action(action);
        // Force the complete state to remain observable; destruction is timed.
        asm volatile("" : : "g"(x.get()) : "memory");
        sums[t] += static_cast<SplendorGameState &>(*x).players[0].gems.gems[1];
      }
    });
  {
    std::unique_lock<std::mutex> lock(mutex);
    cv.wait(lock, [&] { return ready == threads; });
  }
  const auto measured_start = Clock::now();
  {
    std::lock_guard<std::mutex> lock(mutex);
    go = true;
  }
  cv.notify_all();
  for (auto &x : workers)
    x.join();
  const auto finish = Clock::now();
  uint64_t checksum = 0;
  for (auto x : sums)
    checksum += x;
  if (checksum != iterations)
    return 3;
  const double elapsed =
      std::chrono::duration<double>(finish - measured_start).count();
  const nlohmann::json result = {
      {"engine", "seal256"},
      {"workload", "opening_clone_take"},
      {"iterations", iterations},
      {"transitions", iterations},
      {"threads", threads},
      {"seed", seed},
      {"elapsed_seconds", elapsed},
      {"startup_setup_warmup_seconds",
       std::chrono::duration<double>(measured_start - start).count()},
      {"checksum", checksum},
      {"before", normalized(base)},
      {"after", normalized(check)},
      {"whole_game_comparable", false},
      {"verified", true},
      {"timing_boundary",
       "native clone plus verify_action plus apply plus destruction, thread "
       "release/join included; setup and warmup excluded"}};
  std::cout << result.dump() << '\n';
}
