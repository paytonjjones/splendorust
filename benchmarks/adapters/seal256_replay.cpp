// Replay native control histories through the unchanged native validator.
#include "splendor.h"
#include <iostream>
#include <cstdlib>
using json=nlohmann::json;
int main(){std::string line;while(std::getline(std::cin,line)){
 try {const auto v=json::parse(line);std::srand(v.at("setup_seed").get<unsigned>());splendor::SplendorGameState s(2);
  if(v.contains("initial_state")) {
    const auto& initial=v.at("initial_state");
    std::unordered_map<std::string,const splendor::Card*> card_map;
    for(const auto& row:splendor::CARDS)for(const auto& c:row)card_map[c.to_str()]=&c;
    std::unordered_map<std::string,const splendor::Noble*> noble_map;
    for(const auto& n:splendor::NOBLES)noble_map[n.to_str()]=&n;
    for(int t=0;t<3;++t){s.decks[t].clear();s.cards[t].clear();
      for(const auto& c:initial.at("decks")[t])s.decks[t].push_back(card_map.at(c.get<std::string>()));
      for(const auto& c:initial.at("cards")[t])s.cards[t].push_back(card_map.at(c.get<std::string>()));}
    s.nobles.clear();for(const auto& n:initial.at("nobles"))s.nobles.push_back(noble_map.at(n.get<std::string>()));
    s.gems.gems=initial.at("gems").get<std::array<int,6>>();
    if(s.round!=0||s.player_to_move!=0||s.skips!=0||s.table_card_needed)throw std::runtime_error("noninitial fixture");
  }
  for(int action:v.at("actions")){if(!s.verify_action(action).first)throw std::runtime_error("invalid native replay action");s.apply_action(action);}
  std::cout<<json({{"scores",{s.players[0].points,s.players[1].points}}, {"rewards",s.rewards()}, {"round",s.round},{"terminal",s.is_terminal()}}).dump()<<std::endl;
 }catch(const std::exception& e){std::cout<<json({{"error",e.what()}}).dump()<<std::endl;}
}}
