#![forbid(unsafe_code)]

//! Small, observation-safe JSON API for the browser game worker.
use serde::{Deserialize, Serialize};
use splendor_agents::{
    Agent, SearchConfig, SearchProfileOverrides, make_agent_with_profile, transfer,
};
use splendor_core::{
    Action, ActionSet, ENGINE_VERSION, GameOutcome, GameState, NONE, Observation, Phase, Player,
    Source,
    data::{CARDS, NOBLES},
};
use std::collections::HashMap;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::{Mutex, OnceLock};
use wasm_bindgen::prelude::*;

#[derive(Clone, Debug, Deserialize)]
#[serde(default, rename_all = "camelCase", deny_unknown_fields)]
struct ChampionConfig {
    search_agent: String,
    iterations: u32,
    depth: u32,
    world_pool: usize,
    gumbel_max_considered: usize,
    gumbel_cvisit: f64,
    gumbel_cscale: f64,
    gumbel_root_noise: f64,
}
impl Default for ChampionConfig {
    fn default() -> Self {
        Self {
            search_agent: "flywheel-gumbel".into(),
            iterations: 128,
            depth: 16,
            world_pool: 3,
            gumbel_max_considered: 16,
            gumbel_cvisit: 50.0,
            gumbel_cscale: 0.1,
            gumbel_root_noise: 0.0,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct CardView {
    id: u8,
    tier: u8,
    bonus: u8,
    points: u8,
    cost: [u8; 5],
}
impl From<u8> for CardView {
    fn from(id: u8) -> Self {
        let c = CARDS[id as usize];
        Self {
            id,
            tier: c.tier + 1,
            bonus: c.bonus,
            points: c.points,
            cost: c.cost,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct NobleView {
    id: u8,
    requirements: [u8; 5],
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ReservationView {
    hidden: bool,
    tier: u8,
    card: Option<CardView>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PlayerView {
    seat: u8,
    tokens: [u8; 6],
    bonuses: [u8; 5],
    score: u8,
    owned_cards: Vec<CardView>,
    reserved_count: u8,
    reserved: Vec<Option<ReservationView>>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LegalAction {
    id: String,
    kind: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    take: Option<[u8; 5]>,
    #[serde(skip_serializing_if = "Option::is_none")]
    slot: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tier: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reserved_index: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    payment: Option<[u8; 5]>,
    #[serde(skip_serializing_if = "Option::is_none")]
    returns: Option<[u8; 6]>,
    #[serde(skip_serializing_if = "Option::is_none")]
    noble_id: Option<u8>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GameResult {
    status: &'static str,
    winner_mask: u8,
    ranks: [u8; 2],
    scores: [u8; 2],
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<&'static str>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GameEvent {
    revision: u32,
    actor: u8,
    action_id: String,
    kind: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    take: Option<[u8; 5]>,
    #[serde(skip_serializing_if = "Option::is_none")]
    payment: Option<[u8; 5]>,
    #[serde(skip_serializing_if = "Option::is_none")]
    gold_payment: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    returns: Option<[u8; 6]>,
    #[serde(skip_serializing_if = "Option::is_none")]
    slot: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tier: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    card_id: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    noble_id: Option<u8>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GameSnapshot {
    revision: u32,
    turn: u32,
    active_player: u8,
    human_seat: u8,
    stage: &'static str,
    final_round: bool,
    bank: [u8; 6],
    market: Vec<Option<CardView>>,
    deck_counts: [u8; 3],
    nobles: Vec<NobleView>,
    players: [PlayerView; 2],
    pending_card: Option<CardView>,
    legal_actions: Vec<LegalAction>,
    result: Option<GameResult>,
    last_events: Vec<GameEvent>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct TrainingRecord {
    schema: &'static str,
    engine: &'static str,
    players: u8,
    seed: String,
    actions: Vec<[u8; 7]>,
    revision: u32,
    turns: u32,
    state_debug: String,
    result: Option<GameResult>,
}

/// A deterministic two-player game controlled by one human and a loaded model.
#[wasm_bindgen]
pub struct WebGame {
    state: GameState,
    seed: u64,
    human_seat: u8,
    bot: Box<dyn Agent>,
    revision: u32,
    actions: Vec<[u8; 7]>,
    events: Vec<GameEvent>,
}

/// Read-only metadata shared by every game. Colors are white, blue, green, red, black, gold.
#[wasm_bindgen]
pub fn metadata() -> Result<String, JsValue> {
    #[derive(Serialize)]
    #[serde(rename_all = "camelCase")]
    struct Metadata {
        colors: [&'static str; 6],
        cards: Vec<CardView>,
        nobles: Vec<NobleView>,
    }
    serde_json::to_string(&Metadata {
        colors: ["white", "blue", "green", "red", "black", "gold"],
        cards: (0..CARDS.len())
            .map(|id| CardView::from(id as u8))
            .collect(),
        nobles: NOBLES
            .iter()
            .enumerate()
            .map(|(id, &requirements)| NobleView {
                id: id as u8,
                requirements,
            })
            .collect(),
    })
    .map_err(|e| js_error(&format!("could not encode card metadata: {e}")))
}

#[wasm_bindgen]
impl WebGame {
    /// Create a new game. The seed is parsed for setup only and is never returned.
    #[wasm_bindgen(constructor)]
    pub fn new(
        seed: String,
        human_seat: u8,
        model_bytes: Vec<u8>,
        config_json: String,
    ) -> Result<WebGame, JsValue> {
        if human_seat > 1 {
            return Err(js_error("humanSeat must be 0 or 1"));
        }
        let seed = parse_seed(&seed).ok_or_else(|| {
            js_error("seed must be an unsigned decimal or 0x hexadecimal integer")
        })?;
        let config: ChampionConfig = if config_json.trim().is_empty() || config_json.trim() == "{}"
        {
            ChampionConfig::default()
        } else {
            serde_json::from_str(&config_json)
                .map_err(|e| js_error(&format!("invalid champion config: {e}")))?
        };
        let gumbel = config.search_agent == "flywheel-gumbel";
        if !gumbel && config.search_agent != "flywheel-best" {
            return Err(js_error(
                "unsupported champion search agent; this WASM build supports flywheel-best and flywheel-gumbel",
            ));
        }
        if config.iterations == 0
            || config.depth == 0
            || config.world_pool == 0
            || (gumbel
                && (config.gumbel_max_considered == 0
                    || !config.gumbel_cvisit.is_finite()
                    || config.gumbel_cvisit < 0.0
                    || !config.gumbel_cscale.is_finite()
                    || config.gumbel_cscale <= 0.0
                    || !config.gumbel_root_noise.is_finite()
                    || config.gumbel_root_noise < 0.0))
        {
            return Err(js_error(
                "champion search settings are outside valid ranges",
            ));
        }
        let model = load_model(&model_bytes)?;
        let search = SearchConfig {
            iterations: config.iterations,
            depth: config.depth,
            ..SearchConfig::default()
        };
        let profile = if gumbel {
            Some(SearchProfileOverrides {
                world_pool: config.world_pool,
                gumbel_max_considered: config.gumbel_max_considered,
                gumbel_cvisit: config.gumbel_cvisit,
                gumbel_cscale: config.gumbel_cscale,
                gumbel_noise: config.gumbel_root_noise,
            })
        } else {
            None
        };
        let bot = make_agent_with_profile(
            &config.search_agent,
            seed ^ 0x5350_4c45_4e44_4f52,
            &search,
            Some(model),
            profile,
        )
        .map_err(|e| js_error(&format!("could not configure champion search: {e}")))?;
        let state =
            GameState::new(2, seed).map_err(|e| js_error(&format!("could not start game: {e}")))?;
        Ok(Self {
            state,
            seed,
            human_seat,
            bot,
            revision: 0,
            actions: Vec::new(),
            events: Vec::new(),
        })
    }

    /// Return the public board and the human's private information as JSON.
    pub fn snapshot(&self) -> Result<String, JsValue> {
        self.snapshot_json()
    }

    /// Return the private versioned action journal for export or offline validation.
    #[wasm_bindgen(js_name = trainingRecord)]
    pub fn training_record(&self) -> Result<String, JsValue> {
        let observation = self.state.observe(usize::from(self.human_seat));
        let result = self
            .state
            .outcome()
            .map(finished_result)
            .or_else(|| self.is_blocked().then(|| blocked_result(&observation)));
        let record = TrainingRecord {
            schema: "splendor-web-replay-v1",
            engine: ENGINE_VERSION,
            players: 2,
            seed: self.seed.to_string(),
            actions: self.actions.clone(),
            revision: self.revision,
            turns: self.state.turns(),
            state_debug: format!("{:?}", self.state),
            result,
        };
        serde_json::to_string(&record)
            .map_err(|e| js_error(&format!("could not encode training record: {e}")))
    }

    /// Apply one legal human choice, then make forced human choices automatically.
    pub fn act(&mut self, action_id: String) -> Result<String, JsValue> {
        if self.is_blocked() {
            return Err(js_error("game is blocked"));
        }
        if self.state.is_terminal() {
            return Err(js_error("game is finished"));
        }
        if self.state.current_player() != usize::from(self.human_seat) {
            return Err(js_error("it is not the human turn"));
        }
        let action = self
            .action_by_id(&action_id)
            .ok_or_else(|| js_error("action id is not legal in the current state"))?;
        self.events.clear();
        self.apply(action)?;
        self.resolve_forced_human_choices()?;
        self.snapshot_json()
    }

    /// Make one bot engine decision. The caller can repeat this in test mode.
    #[wasm_bindgen(js_name = botStep)]
    pub fn bot_step(&mut self) -> Result<String, JsValue> {
        self.ensure_bot_turn()?;
        self.events.clear();
        self.step_bot()?;
        self.snapshot_json()
    }

    /// Make the bot's full turn, including internal payment or noble choices.
    #[wasm_bindgen(js_name = playBotTurn)]
    pub fn play_bot_turn(&mut self) -> Result<String, JsValue> {
        self.ensure_bot_turn()?;
        self.events.clear();
        let start_turn = self.state.turns();
        let mut decisions = 0;
        while !self.state.is_terminal()
            && !self.is_blocked()
            && self.state.current_player() != usize::from(self.human_seat)
        {
            self.step_bot()?;
            decisions += 1;
            if decisions > 16 || (self.state.turns() == start_turn && decisions == 16) {
                return Err(js_error(
                    "bot did not finish its turn within 16 engine decisions",
                ));
            }
        }
        self.snapshot_json()
    }
}

impl WebGame {
    fn legal(&self) -> ActionSet {
        let mut a = ActionSet::new();
        self.state.legal_actions(&mut a);
        a
    }
    fn action_by_id(&self, id: &str) -> Option<Action> {
        self.legal().into_iter().find(|a| action_id(*a) == id)
    }
    fn apply(&mut self, action: Action) -> Result<(), JsValue> {
        let next_revision = self
            .revision
            .checked_add(1)
            .ok_or_else(|| js_error("game revision limit reached"))?;
        let actor = self.state.current_player() as u8;
        let observation = self.state.observe(actor as usize);
        self.state
            .apply_action(action)
            .map_err(|e| js_error(&format!("engine rejected action: {e}")))?;
        self.actions.push(encode_action(action));
        self.revision = next_revision;
        let after = self.state.observe(actor as usize);
        self.events.push(event_for(
            self.revision,
            actor,
            action,
            &observation,
            &after,
            self.human_seat,
        ));
        Ok(())
    }
    fn is_blocked(&self) -> bool {
        !self.state.is_terminal() && (self.state.turns() == u32::MAX || self.legal().is_empty())
    }
    fn ensure_bot_turn(&self) -> Result<(), JsValue> {
        if self.state.is_terminal() {
            return Err(js_error("game is finished"));
        }
        if self.is_blocked() {
            return Err(js_error("game is blocked"));
        }
        if self.state.current_player() == usize::from(self.human_seat) {
            return Err(js_error("it is the human turn"));
        }
        Ok(())
    }
    fn step_bot(&mut self) -> Result<(), JsValue> {
        let legal = self.legal();
        if legal.is_empty() {
            return Ok(());
        }
        let actor = self.state.current_player();
        let observation = self.state.observe(actor);
        let action = self.bot.select_action(&observation, &legal);
        self.apply(action)
    }
    fn resolve_forced_human_choices(&mut self) -> Result<(), JsValue> {
        while !self.state.is_terminal()
            && !self.is_blocked()
            && self.state.current_player() == usize::from(self.human_seat)
            && self.state.phase() != Phase::Main
        {
            let legal = self.legal();
            if legal.len() != 1 {
                break;
            }
            self.apply(legal[0])?;
        }
        Ok(())
    }
    fn snapshot_json(&self) -> Result<String, JsValue> {
        let observation = self.state.observe(usize::from(self.human_seat));
        let active_player = self.state.current_player() as u8;
        let human_turn = active_player == self.human_seat;
        let blocked = self.is_blocked();
        let stage = if self.state.is_terminal() {
            "finished"
        } else if blocked {
            "blocked"
        } else {
            match self.state.phase() {
                Phase::Main => "main",
                Phase::Payment(_) => "payment",
                Phase::Return => "return",
                Phase::Noble => "noble",
                Phase::Terminal => "finished",
            }
        };
        let mut result = self.state.outcome().map(finished_result);
        if blocked {
            result = Some(blocked_result(&observation));
        }
        let players = std::array::from_fn(|seat| player_view(&observation, seat));
        let mut legal = if human_turn && !blocked && !self.state.is_terminal() {
            self.legal().into_iter().map(legal_view).collect()
        } else {
            Vec::new()
        };
        // Internal decisions for the bot are never returned as available human controls.
        legal.shrink_to_fit();
        let pending_card = if human_turn {
            pending_card(&observation)
        } else {
            None
        };
        let snapshot = GameSnapshot {
            revision: self.revision,
            turn: self.state.turns(),
            active_player,
            human_seat: self.human_seat,
            stage,
            final_round: observation.final_round,
            bank: observation.bank,
            market: observation.market.iter().map(|&id| card(id)).collect(),
            deck_counts: observation.remaining,
            nobles: (0..NOBLES.len())
                .filter(|&id| observation.nobles & (1 << id) != 0)
                .map(|id| NobleView {
                    id: id as u8,
                    requirements: NOBLES[id],
                })
                .collect(),
            players,
            pending_card,
            legal_actions: legal,
            result,
            last_events: self.events.clone(),
        };
        serde_json::to_string(&snapshot)
            .map_err(|e| js_error(&format!("could not encode game state: {e}")))
    }
}

fn parse_seed(seed: &str) -> Option<u64> {
    if let Some(hex) = seed.strip_prefix("0x") {
        u64::from_str_radix(hex, 16).ok()
    } else {
        seed.parse().ok()
    }
}
fn encode_action(action: Action) -> [u8; 7] {
    let mut encoded = [0; 7];
    match action {
        Action::Take(counts) => {
            encoded[0] = 0;
            encoded[1..6].copy_from_slice(&counts);
        }
        Action::ReserveVisible(slot) => {
            encoded[0] = 1;
            encoded[1] = slot;
        }
        Action::ReserveDeck(tier) => {
            encoded[0] = 2;
            encoded[1] = tier;
        }
        Action::BuyVisible(slot) => {
            encoded[0] = 3;
            encoded[1] = slot;
        }
        Action::BuyReserved(slot) => {
            encoded[0] = 4;
            encoded[1] = slot;
        }
        Action::Pay(counts) => {
            encoded[0] = 5;
            encoded[1..6].copy_from_slice(&counts);
        }
        Action::Return(counts) => {
            encoded[0] = 6;
            encoded[1..7].copy_from_slice(&counts);
        }
        Action::Noble(id) => {
            encoded[0] = 7;
            encoded[1] = id;
        }
    }
    encoded
}
fn load_model(bytes: &[u8]) -> Result<&'static transfer::Model, JsValue> {
    static MODELS: OnceLock<Mutex<HashMap<Vec<u8>, &'static transfer::Model>>> = OnceLock::new();
    let models = MODELS.get_or_init(|| Mutex::new(HashMap::new()));
    let mut models = models
        .lock()
        .map_err(|_| js_error("model cache is unavailable"))?;
    if let Some(&model) = models.get(bytes) {
        return Ok(model);
    }
    let model = catch_unwind(AssertUnwindSafe(|| transfer::Model::from_bytes(bytes)))
        .map_err(|_| js_error("model bytes do not contain a supported production model"))?;
    let model: &'static transfer::Model = Box::leak(Box::new(model));
    models.insert(bytes.to_vec(), model);
    Ok(model)
}
fn js_error(message: &str) -> JsValue {
    #[cfg(target_arch = "wasm32")]
    {
        JsValue::from_str(message)
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = message;
        JsValue::NULL
    }
}
fn card(id: u8) -> Option<CardView> {
    (id != NONE).then(|| CardView::from(id))
}
fn player_view(o: &Observation, seat: usize) -> PlayerView {
    let p: &Player = &o.players[seat];
    let reserved = p
        .reserved
        .iter()
        .map(|r| {
            if r.card == NONE {
                return (r.tier != 0).then_some(ReservationView {
                    hidden: true,
                    tier: r.tier + 1,
                    card: None,
                });
            }
            Some(ReservationView {
                hidden: false,
                tier: r.tier + 1,
                card: card(r.card),
            })
        })
        .collect();
    PlayerView {
        seat: seat as u8,
        tokens: p.tokens,
        bonuses: p.bonuses,
        score: p.score,
        owned_cards: (0..CARDS.len())
            .filter(|&id| p.owned & (1u128 << id) != 0)
            .map(|id| CardView::from(id as u8))
            .collect(),
        reserved_count: o.reserved_counts[seat],
        reserved,
    }
}
fn pending_card(o: &Observation) -> Option<CardView> {
    let Phase::Payment(source) = o.phase else {
        return None;
    };
    let id = match source {
        Source::Market(slot) => o.market.get(slot as usize).copied().unwrap_or(NONE),
        Source::Reserved(slot) => o.players[o.current as usize]
            .reserved
            .get(slot as usize)
            .map_or(NONE, |r| r.card),
    };
    card(id)
}
fn finished_result(o: GameOutcome) -> GameResult {
    GameResult {
        status: "finished",
        winner_mask: o.winners,
        ranks: [o.ranks[0], o.ranks[1]],
        scores: [o.scores[0], o.scores[1]],
        reason: None,
    }
}
fn blocked_result(o: &Observation) -> GameResult {
    GameResult {
        status: "blocked",
        winner_mask: 0,
        ranks: [0, 0],
        scores: [o.players[0].score, o.players[1].score],
        reason: Some(if o.turns == u32::MAX {
            "decision_limit"
        } else {
            "no_legal_action"
        }),
    }
}
fn id_for_count(prefix: &str, values: &[u8]) -> String {
    format!(
        "{prefix}:{}",
        values
            .iter()
            .map(u8::to_string)
            .collect::<Vec<_>>()
            .join(",")
    )
}
fn action_id(a: Action) -> String {
    match a {
        Action::Take(v) => id_for_count("take", &v),
        Action::ReserveVisible(i) => format!("reserve-visible:{i}"),
        Action::ReserveDeck(t) => format!("reserve-deck:{t}"),
        Action::BuyVisible(i) => format!("buy-visible:{i}"),
        Action::BuyReserved(i) => format!("buy-reserved:{i}"),
        Action::Pay(v) => id_for_count("pay", &v),
        Action::Return(v) => id_for_count("return", &v),
        Action::Noble(n) => format!("noble:{n}"),
    }
}
fn legal_view(a: Action) -> LegalAction {
    let mut out = LegalAction {
        id: action_id(a),
        kind: "",
        take: None,
        slot: None,
        tier: None,
        reserved_index: None,
        payment: None,
        returns: None,
        noble_id: None,
    };
    match a {
        Action::Take(v) => {
            out.kind = "take";
            out.take = Some(v);
        }
        Action::ReserveVisible(i) => {
            out.kind = "reserve_visible";
            out.slot = Some(i);
        }
        Action::ReserveDeck(t) => {
            out.kind = "reserve_deck";
            out.tier = Some(t + 1);
        }
        Action::BuyVisible(i) => {
            out.kind = "buy_visible";
            out.slot = Some(i);
        }
        Action::BuyReserved(i) => {
            out.kind = "buy_reserved";
            out.reserved_index = Some(i);
        }
        Action::Pay(v) => {
            out.kind = "pay";
            out.payment = Some(v);
        }
        Action::Return(v) => {
            out.kind = "return";
            out.returns = Some(v);
        }
        Action::Noble(n) => {
            out.kind = "noble";
            out.noble_id = Some(n);
        }
    }
    out
}
fn event_for(
    revision: u32,
    actor: u8,
    a: Action,
    o: &Observation,
    after: &Observation,
    human_seat: u8,
) -> GameEvent {
    let active = &o.players[actor as usize];
    let (kind, take, payment, returns, slot, tier, card_id, noble_id) = match a {
        Action::Take(v) => ("take", Some(v), None, None, None, None, None, None),
        Action::ReserveVisible(i) => (
            "reserve_visible",
            None,
            None,
            None,
            Some(i),
            None,
            Some(o.market[i as usize]).filter(|&id| id != NONE),
            None,
        ),
        Action::ReserveDeck(t) => (
            "reserve_deck",
            None,
            None,
            None,
            None,
            Some(t + 1),
            (actor == human_seat)
                .then(|| {
                    after.players[actor as usize].reserved
                        [o.reserved_counts[actor as usize] as usize]
                        .card
                })
                .filter(|&id| id != NONE),
            None,
        ),
        Action::BuyVisible(i) => (
            "buy_visible",
            None,
            None,
            None,
            Some(i),
            None,
            Some(o.market[i as usize]),
            None,
        ),
        Action::BuyReserved(i) => (
            "buy_reserved",
            None,
            None,
            None,
            None,
            None,
            active.reserved[i as usize]
                .card
                .ne(&NONE)
                .then_some(active.reserved[i as usize].card),
            None,
        ),
        Action::Pay(v) => (
            "pay",
            None,
            Some(v),
            None,
            None,
            None,
            pending_card(o).map(|c| c.id),
            None,
        ),
        Action::Return(v) => ("return", None, None, Some(v), None, None, None, None),
        Action::Noble(n) => ("noble", None, None, None, None, None, None, Some(n)),
    };
    GameEvent {
        revision,
        actor,
        action_id: action_id(a),
        kind,
        take,
        payment,
        gold_payment: if matches!(a, Action::Pay(_)) {
            Some(o.players[actor as usize].tokens[5] - after.players[actor as usize].tokens[5])
        } else {
            None
        },
        returns,
        slot,
        tier,
        card_id,
        noble_id,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    fn model() -> Vec<u8> {
        let path = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../research/e81/model/model.bin"
        );
        std::fs::read(path).expect("E81 production model is present in the source checkout")
    }
    fn strength_model() -> Vec<u8> {
        let path = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../web/public/models/57f6e227f8ac0382b7fa67dba6b58ec6663d1f635c7b9f583937867cd6692deb.bin"
        );
        std::fs::read(path)
            .expect("research-strength Entity model is present in the web asset tree")
    }
    fn game(seed: u64, human: u8, config: &str) -> WebGame {
        WebGame::new(seed.to_string(), human, model(), config.into()).unwrap()
    }
    fn snapshot(g: &WebGame) -> Value {
        serde_json::from_str(&g.snapshot().unwrap()).unwrap()
    }
    #[test]
    fn api_redacts_blind_reservations_and_only_lists_human_actions() {
        let mut g = game(9, 1, "{\"iterations\":2,\"depth\":2}");
        g.play_bot_turn().unwrap();
        let s = snapshot(&g);
        assert_eq!(s["activePlayer"], 1);
        assert!(!s["legalActions"].as_array().unwrap().is_empty());
        assert!(
            s["players"][0]["reserved"]
                .as_array()
                .unwrap()
                .iter()
                .all(|r| r.is_null() || r["card"].is_null())
        );
        assert!(s.get("seed").is_none());
    }

    #[test]
    fn training_record_keeps_high_seed_and_exact_arena_action_encoding() {
        let seed = u64::MAX;
        let mut g = game(seed, 0, "{}");
        let initial: Value = serde_json::from_str(&g.training_record().unwrap()).unwrap();
        assert_eq!(initial["schema"], "splendor-web-replay-v1");
        assert_eq!(initial["engine"], ENGINE_VERSION);
        assert_eq!(initial["players"], 2);
        assert_eq!(initial["seed"], seed.to_string());
        assert_eq!(initial["actions"], serde_json::json!([]));
        assert_eq!(initial["revision"], 0);
        assert_eq!(initial["turns"], 0);
        assert_eq!(initial["stateDebug"], format!("{:?}", g.state));
        assert!(initial["result"].is_null());
        assert!(snapshot(&g).get("seed").is_none());

        let action = g
            .legal()
            .into_iter()
            .find(|action| matches!(action, Action::Take(_)))
            .unwrap();
        g.act(action_id(action)).unwrap();
        let record: Value = serde_json::from_str(&g.training_record().unwrap()).unwrap();
        assert_eq!(record["actions"].as_array().unwrap().len(), 1);
        assert_eq!(record["revision"], 1);
        assert_eq!(
            record["actions"][0],
            serde_json::json!(splendor_arena::encode(action))
        );
    }

    #[test]
    fn journal_action_encoder_matches_arena_for_every_action_variant() {
        let actions = [
            Action::Take([1, 2, 3, 4, 5]),
            Action::ReserveVisible(4),
            Action::ReserveDeck(2),
            Action::BuyVisible(3),
            Action::BuyReserved(1),
            Action::Pay([1, 2, 3, 4, 5]),
            Action::Return([1, 2, 3, 4, 5, 6]),
            Action::Noble(9),
        ];
        for action in actions {
            assert_eq!(encode_action(action), splendor_arena::encode(action));
        }
    }

    #[test]
    fn invalid_human_action_preserves_last_events_and_snapshot() {
        let mut g = game(12, 0, "{}");
        let action = g
            .legal()
            .into_iter()
            .find(|action| matches!(action, Action::Take(_)))
            .unwrap();
        g.act(action_id(action)).unwrap();

        let before = g.snapshot().unwrap();
        let before_json: Value = serde_json::from_str(&before).unwrap();
        assert!(!before_json["lastEvents"].as_array().unwrap().is_empty());
        let record_before = g.training_record().unwrap();
        assert!(g.act("not-a-legal-action".into()).is_err());
        assert_eq!(g.snapshot().unwrap(), before);
        assert_eq!(g.training_record().unwrap(), record_before);
    }

    #[test]
    fn e81_web_api_first_bot_decision_matches_native_agent_profile() {
        let seed = 91_337;
        let model_bytes = model();
        let config = r#"{"searchAgent":"flywheel-gumbel","iterations":128,"depth":16,"worldPool":3,"gumbelMaxConsidered":16,"gumbelCvisit":50,"gumbelCscale":0.1,"gumbelRootNoise":0}"#;
        let mut web = WebGame::new("91337".into(), 0, model_bytes.clone(), config.into()).unwrap();
        let first_take = web
            .legal()
            .into_iter()
            .find(|a| matches!(a, Action::Take(_)))
            .unwrap();
        web.act(action_id(first_take)).unwrap();
        assert_eq!(web.state.current_player(), 1);

        let mut native_state = GameState::new(2, seed).unwrap();
        native_state.apply_action(first_take).unwrap();
        let mut native = splendor_agents::make_agent_with_model(
            "flywheel-gumbel",
            seed ^ 0x5350_4c45_4e44_4f52,
            &SearchConfig {
                iterations: 128,
                depth: 16,
                ..SearchConfig::default()
            },
            Some(load_model(&model_bytes).unwrap()),
        )
        .unwrap();
        let observation = native_state.observe(1);
        let legal = {
            let mut out = ActionSet::new();
            native_state.legal_actions(&mut out);
            out
        };
        let native_action = native.select_action(&observation, &legal);
        web.bot_step().unwrap();
        assert_eq!(action_id(native_action), "take:0,0,0,2,0");
        assert_eq!(
            web.events.last().unwrap().action_id,
            action_id(native_action)
        );
    }

    #[test]
    fn research_strength_entity_model_runs_with_puct_profile() {
        let config = r#"{"searchAgent":"flywheel-best","iterations":2,"depth":4,"worldPool":3}"#;
        let mut web = WebGame::new("91337".into(), 0, strength_model(), config.into()).unwrap();
        let action = web
            .legal()
            .into_iter()
            .find(|a| matches!(a, Action::Take(_)))
            .unwrap();
        web.act(action_id(action)).unwrap();
        web.bot_step().unwrap();
        assert!(!web.events.is_empty());
    }

    #[test]
    fn reachable_two_player_noble_choice_uses_the_web_api() {
        use splendor_agents::StrongHeuristicAgent;
        let mut g = game(10, 0, "{\"iterations\":2,\"depth\":3}");
        let mut human = StrongHeuristicAgent;
        let mut saw_forced_human_decision = false;
        for _ in 0..250 {
            if g.state.phase() == Phase::Noble {
                let before = snapshot(&g);
                let nobles = before["legalActions"].as_array().unwrap();
                assert!(nobles.len() > 1);
                let chosen = nobles[0]["id"].as_str().unwrap().to_owned();
                let after: Value = serde_json::from_str(&g.act(chosen).unwrap()).unwrap();
                assert_eq!(after["lastEvents"][0]["kind"], "noble");
                assert!(saw_forced_human_decision);
                return;
            }
            if g.state.is_terminal() || g.is_blocked() {
                break;
            }
            if g.state.current_player() == 0 {
                let observation = g.state.observe(0);
                let legal = g.legal();
                let action = human.select_action(&observation, &legal);
                let after: Value =
                    serde_json::from_str(&g.act(action_id(action)).unwrap()).unwrap();
                let human_events = after["lastEvents"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .filter(|event| event["actor"] == 0)
                    .count();
                saw_forced_human_decision |= human_events > 1;
                let journal: Value = serde_json::from_str(&g.training_record().unwrap()).unwrap();
                assert_eq!(
                    journal["actions"].as_array().unwrap().len(),
                    g.revision as usize
                );
                if after["activePlayer"] == 1
                    && after["stage"] != "finished"
                    && after["stage"] != "blocked"
                {
                    g.play_bot_turn().unwrap();
                }
            } else {
                g.play_bot_turn().unwrap();
            }
        }
        panic!("seed 10 did not reach a multiple-noble choice with the E81 opponent");
    }

    #[test]
    fn api_completes_games_without_inventing_blocked_winners() {
        let mut seen_kinds = std::collections::HashSet::new();
        let mut seen_stages = std::collections::HashSet::new();
        for seed in 1..=8 {
            let mut g = game(seed, 0, "{\"iterations\":2,\"depth\":3}");
            let mut chooser = seed;
            for _ in 0..500 {
                let s = snapshot(&g);
                if s["stage"] == "finished" || s["stage"] == "blocked" {
                    break;
                }
                if s["activePlayer"] == 0 {
                    seen_stages.insert(s["stage"].as_str().unwrap().to_owned());
                    let actions = s["legalActions"].as_array().unwrap();
                    assert!(!actions.is_empty());
                    chooser = chooser.wrapping_mul(6364136223846793005).wrapping_add(1);
                    let index = (chooser as usize) % actions.len();
                    let next: Value = serde_json::from_str(
                        &g.act(actions[index]["id"].as_str().unwrap().to_owned())
                            .unwrap(),
                    )
                    .unwrap();
                    for event in next["lastEvents"].as_array().unwrap() {
                        seen_kinds.insert(event["kind"].as_str().unwrap().to_owned());
                    }
                    if next["activePlayer"] == 1
                        && next["stage"] != "finished"
                        && next["stage"] != "blocked"
                    {
                        let bot: Value = serde_json::from_str(&g.play_bot_turn().unwrap()).unwrap();
                        for event in bot["lastEvents"].as_array().unwrap() {
                            seen_kinds.insert(event["kind"].as_str().unwrap().to_owned());
                        }
                    }
                } else {
                    let bot: Value = serde_json::from_str(&g.play_bot_turn().unwrap()).unwrap();
                    for event in bot["lastEvents"].as_array().unwrap() {
                        seen_kinds.insert(event["kind"].as_str().unwrap().to_owned());
                    }
                }
            }
            let s = snapshot(&g);
            assert!(matches!(s["stage"].as_str(), Some("finished" | "blocked")));
            if s["stage"] == "blocked" {
                assert_eq!(s["result"]["winnerMask"], 0);
                assert_eq!(s["result"]["status"], "blocked");
            }
        }
        for kind in [
            "take",
            "reserve_visible",
            "reserve_deck",
            "buy_visible",
            "buy_reserved",
            "pay",
            "return",
        ] {
            assert!(
                seen_kinds.contains(kind),
                "missing observed action kind {kind}: {seen_kinds:?}"
            );
        }
        for stage in ["payment", "return"] {
            assert!(
                seen_stages.contains(stage),
                "missing observed human stage {stage}: {seen_stages:?}"
            );
        }
    }

    #[test]
    fn stable_ids_cover_all_action_payloads() {
        assert_eq!(action_id(Action::Take([1, 0, 1, 0, 1])), "take:1,0,1,0,1");
        assert_eq!(
            action_id(Action::Return([0, 0, 0, 0, 0, 1])),
            "return:0,0,0,0,0,1"
        );
        assert_eq!(legal_view(Action::Noble(4)).noble_id, Some(4));
    }

    #[test]
    fn metadata_contains_the_engine_card_and_noble_catalogs() {
        let value: Value = serde_json::from_str(&metadata().unwrap()).unwrap();
        assert_eq!(value["colors"].as_array().unwrap().len(), 6);
        assert_eq!(value["cards"].as_array().unwrap().len(), 90);
        assert_eq!(value["nobles"].as_array().unwrap().len(), 10);
        assert_eq!(value["cards"][0]["tier"], 1);
        assert_eq!(
            value["nobles"][0]["requirements"].as_array().unwrap().len(),
            5
        );
    }

    #[test]
    fn config_rejects_unknown_fields_and_invalid_model_bytes() {
        assert!(WebGame::new("1".into(), 0, model(), "{\"mystery\":1}".into()).is_err());
        assert!(WebGame::new("1".into(), 0, vec![0; 8], "{}".into()).is_err());
        assert!(WebGame::new("1".into(), 0, model(), r#"{"worldPool":0}"#.into()).is_err());
        let override_config = r#"{"worldPool":2,"gumbelMaxConsidered":12,"gumbelCvisit":40,"gumbelCscale":0.2,"gumbelRootNoise":0.1}"#;
        assert!(WebGame::new("1".into(), 0, model(), override_config.into()).is_ok());
    }
}
