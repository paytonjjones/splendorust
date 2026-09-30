// Upstream MCTS with observation-derived sampled state. No rule-body edits.
#include "splendor.h"
#include "agents.h"
#include <iostream>
#include <set>
#include <array>
using json=nlohmann::json;
static const int color[6]={3,2,1,0,4,5};
static std::vector<const splendor::Card*> cards;
static std::vector<const splendor::Noble*> nobles;
static json choose(const json& o,int iterations,unsigned seed) {
  if(!o.at("sampled_hidden_world").get<bool>()) throw std::runtime_error("sample required");
  const int n=o.at("count");std::srand(seed);
  auto s=std::make_shared<splendor::SplendorGameState>(n);
  std::set<int> used;
  std::array<std::vector<int>,3> slots;
  for(int t=0;t<3;++t) {s->cards[t].clear();s->decks[t].clear();}
  for(int i=0;i<12;++i) {int id=o.at("market")[i];if(id!=255){s->cards[i/4].push_back(cards.at(id));slots[i/4].push_back(i);used.insert(id);}}
  s->nobles.clear();for(int id:o.at("nobles"))s->nobles.push_back(nobles.at(id));
  for(int c=0;c<6;++c)s->gems.gems[color[c]]=o.at("bank")[c];
  for(int i=0;i<n;++i){auto& p=s->players[i];const auto& q=o.at("players")[i];
    p.points=q.at("score");p.hand_cards.clear();
    for(int c=0;c<6;++c)p.gems.gems[color[c]]=q.at("tokens")[c];
    for(int c=0;c<5;++c)p.card_gems.gems[color[c]]=q.at("bonuses")[c];
    for(int id:q.at("owned"))used.insert(id);
    for(const auto& r:q.at("reserved")){int id=r.at("card");if(id!=255){p.hand_cards.push_back(cards.at(id));used.insert(id);}}
  }
  for(int id=0;id<90;++id)if(!used.count(id))s->decks[id<40?0:id<70?1:2].push_back(cards.at(id));
  for(int t=0;t<3;++t)if(s->decks[t].size()!=o.at("remaining")[t].get<size_t>())throw std::runtime_error("deck count");
  s->player_to_move=o.at("current");s->round=o.at("turns").get<int>()/n;s->skips=0;s->table_card_needed=false;
  // Setup construction RNG is excluded from native policy randomness.
  std::srand(seed);mcts::MCTSParams params;params.iterations=iterations;
  MCTSAgent agent("seal256",params);int selected=agent.get_action(s);
  if(!s->verify_action(selected).first)throw std::runtime_error("native invalid action");
  const auto a=splendor::Action::from_str(splendor::ACTIONS_STR.at(selected));
  std::array<int,7> out{};
  switch(a.type){
    case splendor::ActionType::TAKE:out[0]=0;for(int c=0;c<5;++c)out[c+1]=a.gems.gems[color[c]];break;
    case splendor::ActionType::RESERVE:out[0]=1;out[1]=slots.at(a.level).at(a.pos);break;
    case splendor::ActionType::PURCHASE:out[0]=3;out[1]=slots.at(a.level).at(a.pos);break;
    case splendor::ActionType::PURCHASE_HAND:out[0]=4;out[1]=a.pos;break;
    default:return {{"unsupported","native_pass"},{"native_action",selected}};
  }
  return {{"action",out},{"native_action",selected}};
}
int main(int argc,char** argv){int iterations=argc>1?std::stoi(argv[1]):500;std::string line;
  while(std::getline(std::cin,line)){json result;
    try{const auto v=json::parse(line);const auto op=v.at("op").get<std::string>();
      if(op=="data"){
        cards.clear();nobles.clear();std::set<const splendor::Card*> seen;
        for(const auto& c:v.at("cards")){const splendor::Card* match=nullptr;
          for(const auto& row:splendor::CARDS)for(const auto& native:row){bool ok=native.gem==color[c.at("bonus").get<int>()]&&native.points==c.at("points").get<int>();
            int tier=&row-&splendor::CARDS[0];ok=ok&&tier==c.at("tier").get<int>();
            for(int k=0;k<5;++k)ok=ok&&native.price.gems[color[k]]==c.at("cost")[k].get<int>();if(ok)match=&native;}
          if(!match||!seen.insert(match).second)throw std::runtime_error("card data mismatch");cards.push_back(match);}
        for(const auto& q:v.at("nobles")){const splendor::Noble* match=nullptr;for(const auto& native:splendor::NOBLES){bool ok=native.points==3;
            for(int k=0;k<5;++k)ok=ok&&native.price.gems[color[k]]==q.at("cost")[k].get<int>();if(ok)match=&native;}
          if(!match)throw std::runtime_error("noble data mismatch");nobles.push_back(match);}
        result={{"ok",true},{"matched_cards",cards.size()},{"matched_nobles",nobles.size()}};
      }else if(op=="choose")result=choose(v.at("observation"),iterations,v.at("seed"));
      else result={{"ok",true}};
    }catch(const std::exception& e){result={{"error",e.what()}};}
    std::cout<<result.dump()<<std::endl;
  }
}
