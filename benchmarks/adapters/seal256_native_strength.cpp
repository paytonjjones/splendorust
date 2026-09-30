// Native strength probe for seal256/splendor.
//
// This adapter keeps the upstream MCTS and game rules unchanged. It is a
// native-reference result, not a cross-engine match. It records every game so
// rule, termination, and seat-rotation differences stay visible.
#include <cstdlib>
#include <chrono>
#include <numeric>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "agents.h"
#include "json.hpp"
#include "splendor.h"

using json = nlohmann::json;
using splendor::SplendorGameState;

struct Options {
  int games = 100;
  int iterations = 500;
  int max_chance_children = 100;
  unsigned seed = 1;
  unsigned policy_seed = 6000001;
  std::string output;
};

static Options parse(int argc, char **argv) {
  Options o;
  for (int i = 1; i < argc; ++i) {
    const std::string key = argv[i];
    if (i + 1 >= argc)
      throw std::runtime_error("missing value for " + key);
    const std::string value = argv[++i];
    if (key == "--games")
      o.games = std::stoi(value);
    else if (key == "--iterations")
      o.iterations = std::stoi(value);
    else if (key == "--max-chance-children")
      o.max_chance_children = std::stoi(value);
    else if (key == "--seed")
      o.seed = static_cast<unsigned>(std::stoul(value));
    else if (key == "--policy-seed")
      o.policy_seed = static_cast<unsigned>(std::stoul(value));
    else if (key == "--output")
      o.output = value;
    else
      throw std::runtime_error("unknown option " + key);
  }
  if (o.games <= 0 || o.games % 2 != 0 || o.iterations <= 0 ||
      o.max_chance_children <= 0 || o.output.empty())
    throw std::runtime_error("games must be positive and even; output is required");
  return o;
}

static json play(const Options &o, int index, const SplendorGameState &initial) {
  const unsigned game_seed = o.seed + static_cast<unsigned>(index / 2);
  std::srand(o.policy_seed + static_cast<unsigned>(index / 2));
  auto state = std::make_shared<SplendorGameState>(initial);
  json initial_json; initial.to_json(initial_json);

  mcts::MCTSParams params;
  params.iterations = o.iterations;
  params.max_chance_children = o.max_chance_children;
  RandomAgent random("random");
  // Agents are immutable. Constructing this local MCTS agent with the
  // requested parameters avoids the upstream JSON/task runner and keeps the
  // one-game seed boundary deterministic.
  MCTSAgent configured("seal256_mcts", params);
  const bool mcts_first = index % 2 == 0;
  const std::vector<std::string> seats =
      mcts_first ? std::vector<std::string>{"seal256_mcts", "random"}
                 : std::vector<std::string>{"random", "seal256_mcts"};

  const auto started = std::chrono::steady_clock::now();
  std::string status = "complete";
  std::vector<int> actions;
  size_t decisions = 0;
  while (!state->is_terminal()) {
    const int active = state->active_player();
    if (active == CHANCE_PLAYER) {
      const auto legal = state->get_actions();
      if (legal.empty())
        throw std::runtime_error("chance node has no action");
      const int action = legal[std::rand() % legal.size()];
      state->apply_action(action);
      actions.push_back(action);
    } else {
      const Agent &agent = (seats[active] == "seal256_mcts")
                               ? static_cast<const Agent &>(configured)
                               : static_cast<const Agent &>(random);
      const int action = agent.get_action(std::shared_ptr<const GameState>(state));
      if (!state->verify_action(action).first)
        throw std::runtime_error("agent selected an invalid action");
      state->apply_action(action);
      actions.push_back(action);
      ++decisions;
    }
    if (decisions >= 20000 && !state->is_terminal()) {
      status = "decision_limit";
      break;
    }
  }

  auto rewards = state->rewards();
  if (status != "complete") rewards.assign(2, 0.0);
  if (status == "complete" && std::accumulate(rewards.begin(), rewards.end(), 0.0) == 0.0)
    status = "native_no_winner";
  json record = {
      {"index", index},
      {"setup_seed", game_seed},
      {"policy_seed", o.policy_seed + static_cast<unsigned>(index / 2)},
      {"initial_state", initial_json},
      {"rotation", index % 2},
      {"seats", seats},
      {"iterations", o.iterations},
      {"max_chance_children", o.max_chance_children},
      {"status", status},
      {"play_seconds", std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count()},
      {"decisions", decisions},
      {"round", state->round},
      {"rewards", rewards},
      {"scores", {state->players[0].points, state->players[1].points}},
      {"actions", actions},
  };
  return record;
}

int main(int argc, char **argv) {
  try {
    const Options options = parse(argc, argv);
    std::ofstream out(options.output);
    if (!out)
      throw std::runtime_error("cannot open output");
    json meta = {
        {"schema_version", 1},
        {"engine", "seal256_native"},
        {"policy", "upstream MCTSAgent versus upstream RandomAgent"},
        {"games", options.games},
        {"seed", options.seed},
        {"policy_seed", options.policy_seed},
        {"paired_initial_states", true},
        {"setup_rng", "upstream persistent mt19937 shuffle, one setup construction per block; exact initial fixtures saved"},
        {"iterations", options.iterations},
        {"max_chance_children", options.max_chance_children},
        {"full_seat_rotation", true},
        {"ruleset", "seal256-native-v1"},
        {"observation_profile", "seal256-native-state-v1"},
        {"status_semantics", "native terminal only; no SplendoRust no_legal_action mapping"},
    };
    out << meta.dump() << '\n';
    std::shared_ptr<SplendorGameState> initial;
    for (int i = 0; i < options.games; ++i) {
      if (i % 2 == 0) {
        std::srand(options.seed + static_cast<unsigned>(i / 2));
        initial = std::make_shared<SplendorGameState>(2);
      }
      out << play(options, i, *initial).dump() << '\n';
      out.flush();
    }
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}
