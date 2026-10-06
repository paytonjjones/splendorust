import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import type { ReactNode } from 'react';
import { createGameClient } from './game-client';
import { useBoardKeyboard } from './keyboard-navigation';
import type { GameClient } from './game-client';
import type { Card, GameClientUpdate, GameSnapshot, LegalAction, PlayerSnapshot } from './types';
import { COLOR_NAMES, Gem, Engraving, Seal, Cost, cardLabel, colorStyle } from './art';

const EMPTY: GameClientUpdate = { state: null, status: 'loading', requestPending: false, champion: null, metrics: { wasmInitMs: null, modelLoadMs: null, botDecisionMs: [], botSimulations: [], botTurnMs: [] }, recorder: { status: 'idle', pendingUploads: 0, storedGames: 0 } };
const equal = (a: number[], b: number[]) => a.every((n, i) => n === b[i]);
const total = (a: number[]) => a.reduce((n, v) => n + v, 0);
const bundleText = (a: number[]) => a.map((n, c) => n ? `${n} ${COLOR_NAMES[c].toLowerCase()}` : '').filter(Boolean).join(', ');

function describeMove(state: GameSnapshot) {
  const events = state.lastEvents.filter(e => e.actor !== state.humanSeat);
  if (!events.length) return '';
  const buy = events.find(e => e.kind === 'buy_visible' || e.kind === 'buy_reserved');
  if (buy) {
    const card = state.players[1 - state.humanSeat].ownedCards.find(c => c.id === buy.cardId);
    return card ? `Bought a ${COLOR_NAMES[card.bonus].toLowerCase()} card${card.points ? ` for ${card.points} prestige` : ''}.` : 'Bought a development card.';
  }
  const reserve = events.find(e => e.kind.startsWith('reserve'));
  if (reserve) return reserve.kind === 'reserve_deck' ? `Reserved a hidden tier ${reserve.tier} card.` : 'Reserved a market card.';
  const take = events.find(e => e.kind === 'take');
  if (take?.take) return `Took ${bundleText(take.take)}.`;
  const noble = events.find(e => e.kind === 'noble');
  if (noble) return 'Gained a noble and 3 prestige.';
  return '';
}

/** Animate copies between real board locations. Reset cancels the whole sequence. */
function animateBoard(previous: GameSnapshot, next: GameSnapshot, animations: Set<Animation>) {
  const flights: { element: HTMLElement; target: string }[] = [];
  const changed: HTMLElement[] = [];
  const capture = (selector: string, target: string) => {
    const el = document.querySelector<HTMLElement>(selector);
    if (el) flights.push({ element: el.cloneNode(true) as HTMLElement, target });
    if (el) {
      const rect = el.getBoundingClientRect();
      const copy = flights[flights.length - 1]?.element;
      if (copy) Object.assign(copy.style, { position: 'fixed', top: `${rect.top}px`, left: `${rect.left}px`, width: `${rect.width}px`, height: `${rect.height}px`, margin: '0', zIndex: '90', pointerEvents: 'none' });
    }
  };
  for (const player of next.players) {
    const old = previous.players[player.seat];
    for (const card of player.ownedCards) if (!old.ownedCards.some(c => c.id === card.id)) {
      const target = `[data-tableau-seat="${player.seat}"] [data-bonus="${card.bonus}"]`;
      const source = `[data-card-id="${card.id}"] .card-buy`;
      if (document.querySelector(source)) capture(source, target);
      else {
        const purchase = previous.lastEvents.find(e => e.actor === player.seat && e.kind === 'buy_reserved');
        const slot = purchase?.slot ?? old.reserved.findIndex(r => r?.card?.id === card.id);
        if (slot >= 0) capture(`[data-reserve-seat="${player.seat}"] [data-reserved-slot="${slot}"]`, target);
      }
    }
    for (let color = 0; color < 6; color++) {
      if (player.tokens[color] > old.tokens[color] && next.bank[color] < previous.bank[color]) {
        capture(`[data-bank-color="${color}"] .gem`, `[data-wallet-seat="${player.seat}"] [data-color="${color}"]`);
      }
    }
    player.reserved.forEach((reservation, index) => {
      if (reservation?.hidden && index >= old.reservedCount) capture(`[data-deck-tier="${reservation.tier}"]`, `[data-reserve-seat="${player.seat}"] [data-reserved-slot="${index}"]`);
      if (reservation?.card && !old.reserved.some(r => r?.card?.id === reservation.card?.id)) capture(`[data-card-id="${reservation.card.id}"] .card-buy`, `[data-reserve-seat="${player.seat}"] [data-reserved-slot="${index}"]`);
    });
    if (player.score > old.score && previous.nobles.length > next.nobles.length) {
      const noble = previous.nobles.find(n => !next.nobles.some(x => x.id === n.id));
      if (noble) capture(`[data-noble="${noble.id}"]`, `[data-score-seat="${player.seat}"]`);
    }
  }
  return () => {
    for (const flight of flights) {
      const target = document.querySelector<HTMLElement>(flight.target);
      if (!target) continue;
      flight.element.setAttribute('aria-hidden', 'true'); flight.element.inert = true;
      document.body.append(flight.element);
      const from = flight.element.getBoundingClientRect(), to = target.getBoundingClientRect();
      const a = flight.element.animate([
        { transform: 'translate(0,0) scale(1)', opacity: 1 },
        { transform: `translate(${to.left + to.width / 2 - from.left - from.width / 2}px,${to.top + to.height / 2 - from.top - from.height / 2}px) scale(.38)`, opacity: .15 },
      ], { duration: 390, easing: 'cubic-bezier(.2,.75,.2,1)' });
      animations.add(a);
      void a.finished.catch(() => {}).finally(() => { flight.element.remove(); animations.delete(a); });
    }
    next.market.forEach((card, slot) => {
      if (card && previous.market[slot]?.id !== card.id) {
        const el = document.querySelector<HTMLElement>(`[data-market-slot="${slot}"]`);
        if (el) changed.push(el);
      }
    });
    for (const el of changed) {
      const a = el.animate([{ opacity: .15, transform: 'translateY(-8px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 350, delay: 100, easing: 'ease-out' });
      animations.add(a); void a.finished.catch(() => {}).finally(() => animations.delete(a));
    }
  };
}

function useGame() {
  const [update, setUpdate] = useState(EMPTY);
  const [moving, setMoving] = useState(false);
  const client = useRef<GameClient | null>(null);
  const visible = useRef<GameSnapshot | null>(null);
  useEffect(() => {
    const game = createGameClient(); client.current = game;
    let generation = 0, active = true, pending = 0;
    let chain = Promise.resolve();
    let queuedRevision = -1;
    const animations = new Set<Animation>();
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    const unsub = game.subscribe(incoming => {
      if (!active) return;
      if (!incoming.state) {
        generation++; pending = 0; visible.current = null; queuedRevision = -1;
        for (const a of animations) a.cancel(); animations.clear();
        setMoving(false); setUpdate(incoming); return;
      }
      if (incoming.state.revision === queuedRevision) {
        setUpdate(old => ({ ...incoming, state: old.state })); return;
      }
      queuedRevision = incoming.state.revision;
      const stamp = generation;
      pending++; setMoving(true);
      chain = chain.then(async () => {
        if (!active || stamp !== generation) return;
        const previous = visible.current;
        const next = incoming.state!;
        const motion = previous && !game.skipWaits && !reduced.matches ? animateBoard(previous, next, animations) : null;
        flushSync(() => { setUpdate(incoming); visible.current = next; });
        motion?.();
        if (motion) await new Promise(resolve => setTimeout(resolve, 430));
        if (!active || stamp !== generation) return;
        pending--; if (pending === 0) { setMoving(false); setUpdate(old => ({ ...game.getUpdate(), state: old.state })); }
      });
    });
    void game.start().catch(error => { if (error.name !== 'AbortError') console.error(error); });
    return () => { active = false; generation++; unsub(); game.dispose(); for (const a of animations) a.cancel(); };
  }, []);
  return { ...update, moving, client };
}

function Modal({ title, children, onClose, className = '', dismissible = true }: { title: string; children: ReactNode; onClose: () => void; className?: string; dismissible?: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = useRef(onClose); close.current = onClose;
  useEffect(() => {
    const element = dialog.current!;
    const last = document.activeElement as HTMLElement | null;
    element.showModal();
    return () => {
      element.close();
      const target = last?.isConnected && last !== document.body && !last.matches(':disabled')
        ? last : document.querySelector<HTMLElement>('nav[aria-label="Game menu"] button:last-child');
      target?.focus({ preventScroll: true });
    };
  }, []);
  return <dialog ref={dialog} className={`modal ${className}`} aria-labelledby="dialog-title" onCancel={event => { event.preventDefault(); if (dismissible) close.current(); }} onClick={event => { if (dismissible && event.target === event.currentTarget) close.current(); }}>
    <div className="modal-head"><h2 id="dialog-title">{title}</h2>{dismissible && <button className="text-button" onClick={onClose} aria-label={`Close ${title}`}>Close</button>}</div>
    {children}
  </dialog>;
}

function DevelopmentCard({ card, label, buy, reserve, onAction, onInspect, slot, compact = false, disabled = false }: { card: Card; label: string; buy?: LegalAction; reserve?: LegalAction; onAction: (action: LegalAction) => void; onInspect: () => void; slot?: number; compact?: boolean; disabled?: boolean }) {
  return <div className={`development-card ${buy ? 'affordable' : ''} ${compact ? 'compact-card' : ''}`} style={colorStyle(card.bonus)} data-card-id={card.id} data-market-slot={slot}>
    <button className="card-buy" disabled={disabled} onClick={() => buy ? onAction(buy) : onInspect()} aria-label={`${buy ? 'Buy' : 'View'} ${cardLabel(card, label)}.${buy ? ' Purchase available.' : ' Purchase unavailable.'}`}>
      <span className="card-top"><span className="prestige" title={`${card.points} prestige`}>{card.points || null}</span><Gem color={card.bonus}/></span>
      <Engraving card={card}/><span className="card-footer"><Cost amounts={card.cost}/>{buy && <span className="buy-mark">Buy</span>}</span>
    </button>
    {reserve && <button className="reserve-card" disabled={disabled} onClick={() => onAction(reserve)} aria-label={`Reserve ${cardLabel(card, label)}`} title="Reserve this card. Take 1 gold if available.">Reserve</button>}
  </div>;
}

function PlayerArea({ player, human, active, children, botMove, onCollection }: { player: PlayerSnapshot; human: boolean; active: boolean; children?: ReactNode; botMove?: string; onCollection: () => void }) {
  return <section className={`player-area ${human ? 'human-area' : 'opponent-area'} ${active ? 'active-player' : ''}`} aria-label={human ? 'Your tableau' : 'SplendoRust tableau'}>
    <div className="player-heading"><div className="player-identity"><span className="eyebrow">{human ? 'Your table' : 'Champion'}</span><span className="player-name">{human ? 'You' : 'SplendoRust'}{active && <span className="turn-dot" aria-hidden="true"/>}</span></div>
      <button className="bonus-row" data-tableau-seat={player.seat} onClick={onCollection} aria-label={`${human ? 'View your' : 'View SplendoRust'} purchased cards. ${player.ownedCards.length} ${player.ownedCards.length === 1 ? 'card' : 'cards'}. Bonuses: ${bundleText(player.bonuses) || 'none'}`}>
        {player.bonuses.map((n, c) => <span className="bonus-stack" data-bonus={c} key={c} style={colorStyle(c)}><Gem color={c}/><span>{n}</span></span>)}
      </button>
      <span className="score" data-score-seat={player.seat}><span key={player.score} className="score-number">{player.score}</span><span className="score-goal">/ 15<span className="sr-only"> prestige</span></span></span>
    </div>
    <div className="player-details"><div className="wallet" data-wallet-seat={player.seat} aria-label={`${human ? 'Your' : 'SplendoRust'} gem tokens`}>{player.tokens.map((n, c) => <span className={`wallet-token ${n === 0 ? 'empty-wallet-token' : ''}`} key={c} data-color={c} aria-label={`${COLOR_NAMES[c]}: ${n}`}><Gem color={c}/><span key={n}>{n}</span></span>)}<span className="wallet-total">{total(player.tokens)} / 10</span></div>{!human && <span className="bot-move" aria-live="polite">{botMove || 'Make your first move.'}</span>}</div>
    {children}
  </section>;
}

function PaymentChooser({ state, disabled, onAction }: { state: GameSnapshot; disabled: boolean; onAction: (a: LegalAction) => void }) {
  const player = state.players[state.humanSeat];
  const required = state.pendingCard?.cost.map((n, c) => Math.max(0, n - player.bonuses[c])) || [];
  const cost = total(required);
  const counts = [...new Set(state.legalActions.map(a => cost - total(a.payment || [])))].sort((a, b) => a - b);
  const [gold, setGold] = useState(counts[0] || 0);
  const choices = state.legalActions.filter(a => cost - total(a.payment || []) === gold);
  return <div className="payment-chooser"><p>Your bonuses have reduced the cost. You can use gold in place of colored gems.</p><label className="select-label">Gold to spend<select value={gold} onChange={e => setGold(Number(e.target.value))} onKeyDown={event => {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    const index = counts.indexOf(gold);
    setGold(counts[Math.max(0, Math.min(counts.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)))]);
  }}>{counts.map(n => <option key={n} value={n}>{n} gold</option>)}</select></label><div className="payment-options">{choices.map(a => <button className="payment-option" key={a.id} disabled={disabled} onClick={() => onAction(a)} aria-label={`Pay ${bundleText([...(a.payment || []), gold]) || 'nothing'}`}><Cost amounts={[...(a.payment || []), gold]}/><span>Pay</span></button>)}</div></div>;
}

export function App() {
  const game = useGame();
  const { state, client } = game;
  const [help, setHelp] = useState(false);
  const [restart, setRestart] = useState(false);
  const [inspect, setInspect] = useState<{ card: Card; location: string; reserve?: LegalAction } | null>(null);
  const [collection, setCollection] = useState<PlayerSnapshot | null>(null);
  const [selection, setSelection] = useState<number[]>([0, 0, 0, 0, 0, 0]);
  const [actionError, setActionError] = useState('');
  const [exportError, setExportError] = useState('');
  const [exporting, setExporting] = useState(false);
  const [hideResult, setHideResult] = useState(false);
  const [lastMove, setLastMove] = useState('');
  const previousTurn = useRef(-1);
  const priorBot = useRef<PlayerSnapshot | null>(null);
  const busy = game.status !== 'ready' || game.moving || game.requestPending;
  useBoardKeyboard(!busy, state?.revision ?? -1);
  const humanTurn = state?.activePlayer === state?.humanSeat;
  const disabled = busy || !humanTurn || state?.stage !== 'main';
  useEffect(() => { setSelection([0, 0, 0, 0, 0, 0]); setInspect(null); setActionError(''); }, [state?.revision]);
  useEffect(() => {
    if (!state) { setLastMove(''); previousTurn.current = -1; priorBot.current = null; setHideResult(false); return; }
    const bot = state.players[1 - state.humanSeat];
    const acquired = priorBot.current && bot.ownedCards.find(c => !priorBot.current!.ownedCards.some(x => x.id === c.id));
    priorBot.current = bot;
    const move = acquired ? `Bought a ${COLOR_NAMES[acquired.bonus].toLowerCase()} card${acquired.points ? ` for ${acquired.points} prestige` : ''}.` : describeMove(state);
    if (move) setLastMove(move);
    if (state.turn < previousTurn.current) setHideResult(false);
    previousTurn.current = state.turn;
  }, [state]);
  const act = (action: LegalAction) => {
    setInspect(null); setActionError('');
    void client.current?.act(action.id).catch(error => { if (error.name !== 'AbortError') setActionError(error.message); });
  };
  const newGame = () => {
    setRestart(false); setHideResult(false); setCollection(null); setInspect(null); setLastMove('');
    void client.current?.newGame().catch(error => { if (error.name !== 'AbortError') setActionError(error.message); });
  };
  const vectorActions = state?.legalActions.filter(a => a.kind === (state.stage === 'return' ? 'return' : 'take')) || [];
  const vector = (a: LegalAction) => a.take || a.returns || [];
  const selectedAction = total(selection) > 0 ? vectorActions.find(a => equal(selection.slice(0, vector(a).length), vector(a))) : undefined;
  const toggleGem = (color: number) => {
    let next = [...selection];
    if (state?.stage === 'return') next[color] = (next[color] + 1) % ((state.players[state.humanSeat].tokens[color] || 0) + 1);
    else if (selection[color] === 1 && total(selection) === 1 && vectorActions.some(a => a.take?.[color] === 2)) next[color] = 2;
    else if (selection[color]) next[color] = 0;
    else { if (next.some(n => n === 2)) next = [0, 0, 0, 0, 0, 0]; next[color] = 1; }
    if (!vectorActions.some(a => vector(a).every((n, c) => next[c] <= n))) next[color] = 0;
    setSelection(next);
  };
  const excess = state ? total(state.players[state.humanSeat].tokens) - 10 : 0;
  const title = state?.result ? 'Game complete' : !state ? 'Setting the table' : game.status === 'thinking' || !humanTurn ? 'SplendoRust is thinking' : state.stage === 'payment' ? 'Choose your payment' : state.stage === 'return' ? `Return ${excess} ${excess === 1 ? 'gem' : 'gems'}` : state.stage === 'noble' ? 'Choose a noble' : 'Your turn';
  const instruction = state?.result ? 'View the final board, or start another game.' : state?.stage === 'return' ? 'Select the gems you want to return to the bank.' : state?.stage === 'noble' ? 'Your collection has earned a visit. Choose one noble above.' : total(selection) ? bundleText(selection) : 'Take gems, buy a card, or reserve one for later.';
  const chosenNobles = new Set(state?.legalActions.filter(a => a.kind === 'noble').map(a => a.nobleId));
  const downloadGames = async () => {
    if (!client.current) return;
    setExporting(true); setExportError('');
    try {
      const jsonl = await client.current.exportGames();
      if (!jsonl.trim()) { setExportError('No game records are ready yet.'); return; }
      const url = URL.createObjectURL(new Blob([jsonl], { type: 'application/x-ndjson' }));
      const link = document.createElement('a'); link.href = url;
      link.download = `splendorust-games-${new Date().toISOString().slice(0, 10)}.jsonl`;
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setExportError('The download failed. Try again.'); }
    finally { setExporting(false); }
  };
  const logStatus = exportError || (game.recorder.status === 'error' ? 'Game log unavailable. Try downloading a backup.' : game.recorder.status === 'queued' ? 'Moves saved on this device. Upload pending.' : game.recorder.status === 'saved' ? 'Moves saved for research.' : game.recorder.status === 'idle' ? 'Starting game log…' : 'Saving game log…');

  return <>
    <a className="skip-link" href="#game-controls">Skip to game controls</a>
    <header className="site-header"><div className="brand"><h1>Splendo<span>Rust</span></h1><p>Can you beat the champion?</p></div><nav aria-label="Game menu"><button onClick={() => setHelp(true)}>How to play</button><button onClick={() => state && state.turn > 0 && !state.result ? setRestart(true) : newGame()}>New game</button></nav></header>
    {!state ? <main className="loading-table"><Seal/><h2>{game.status === 'error' ? 'The table is not ready' : 'Preparing the game'}</h2><p role="status">{game.status === 'error' ? game.error : game.champion ? 'Preparing your opponent…' : 'Loading the champion…'}</p>{game.status === 'error' ? <button className="primary-button" onClick={() => void client.current?.retry().catch(() => {})}>Try again</button> : <span className="loading-rule"/>}<p className="loading-note">A two-player challenge. No account needed.</p></main> : <main className="game-table" aria-label="Two-player Splendor game">
      <PlayerArea player={state.players[1 - state.humanSeat]} human={false} active={!humanTurn} botMove={lastMove} onCollection={() => setCollection(state.players[1 - state.humanSeat])}>
        <div className="opponent-reserves" data-reserve-seat={1 - state.humanSeat}>{state.players[1 - state.humanSeat].reserved.filter(Boolean).map((r, i) => <span className="opponent-reserve" key={i} data-reserved-slot={i} aria-label={`SplendoRust reservation ${i + 1}: ${r?.hidden ? `hidden tier ${r.tier}` : r?.card ? cardLabel(r.card, 'public reserved card') : 'unknown'}`}><span>Reserved {r?.tier ? 'ⅠⅡⅢ'[r.tier - 1] : ''}</span>{r?.card ? <Gem color={r.card.bonus}/> : <span className="blind-mark">?</span>}</span>)}</div>
      </PlayerArea>
      <section className={`noble-row ${state.stage === 'noble' ? 'noble-choice' : ''}`} aria-label="Available nobles"><span className="board-label">Patrons</span><div className="noble-tiles">{state.nobles.map(n => <button key={n.id} className={`noble-tile ${chosenNobles.has(n.id) ? 'eligible-noble' : ''}`} data-noble={n.id} disabled={!chosenNobles.has(n.id) || busy} aria-label={`Noble ${n.id + 1}, 3 prestige. Requires ${bundleText(n.requirements)} bonuses.${chosenNobles.has(n.id) ? ' Choose this noble.' : ' Not yet eligible.'}`} onClick={() => { const a = state.legalActions.find(a => a.nobleId === n.id); if (a) act(a); }}><Seal variant={n.id}/><span className="noble-prestige">3</span><Cost amounts={n.requirements}/></button>)}</div><span className="board-label noble-hint">3 prestige each</span></section>
      <section className="market" aria-label="Development card market">{[3, 2, 1].map(tier => <div className="market-tier" key={tier} aria-label={`Tier ${tier} market`}>
        <button className="deck" data-deck-tier={tier} disabled={disabled || !state.legalActions.some(a => a.kind === 'reserve_deck' && a.tier === tier)} aria-label={`Reserve a hidden tier ${tier} card. ${state.deckCounts[tier - 1]} cards in deck.${state.legalActions.some(a => a.kind === 'reserve_deck' && a.tier === tier) ? ' Available.' : ' Unavailable.'}`} onClick={() => { const a = state.legalActions.find(a => a.kind === 'reserve_deck' && a.tier === tier); if (a) act(a); }}><span className="deck-tier">{'ⅠⅡⅢ'[tier - 1]}</span><span className="deck-count">{state.deckCounts[tier - 1]}</span><span className="deck-label">Reserve</span></button>
        {Array.from({ length: 4 }, (_, column) => { const slot = (tier - 1) * 4 + column; const card = state.market[slot]; return card ? <DevelopmentCard key={slot} card={card} slot={slot} label={`market slot ${column + 1}`} disabled={busy || !humanTurn || state.stage !== 'main'} buy={state.legalActions.find(a => a.kind === 'buy_visible' && a.slot === slot)} reserve={state.legalActions.find(a => a.kind === 'reserve_visible' && a.slot === slot)} onAction={act} onInspect={() => setInspect({ card, location: `Tier ${tier}, slot ${column + 1}`, reserve: state.legalActions.find(a => a.kind === 'reserve_visible' && a.slot === slot) })}/> : <div key={slot} className="empty-card" aria-label={`Tier ${tier}, slot ${column + 1}: empty`}/>; })}
      </div>)}</section>
      <section className="gem-bank" aria-label="Shared gem bank"><span className="board-label bank-label">Gem bank</span><div className="bank-tokens">{state.bank.map((count, color) => <div className="bank-pile" key={color}><button className={`gem-token ${selection[color] ? 'selected-token' : ''}`} data-bank-color={color} style={colorStyle(color)} aria-pressed={Boolean(selection[color])} aria-label={`${COLOR_NAMES[color]} gems, ${count} in bank. ${selection[color] ? `${selection[color]} selected.` : ''}${color === 5 ? ' Gold is available only when reserving.' : ''}`} disabled={disabled || color === 5 || !vectorActions.some(a => (a.take?.[color] || 0) > 0)} onClick={() => toggleGem(color)}><Gem color={color}/><span className="pile-count">{count}</span>{selection[color] > 0 && <span className="selected-count">+{selection[color]}</span>}</button><span className="gem-name">{COLOR_NAMES[color]}</span></div>)}</div></section>
      <section className={`action-dock ${busy ? 'thinking-dock' : ''}`} id="game-controls" tabIndex={-1} aria-label="Game controls"><div className="action-copy"><span className="action-title" role="status">{title}{busy && <span className="thinking-dots" aria-hidden="true">···</span>}</span><span className="action-instruction">{game.status === 'thinking' || !humanTurn ? 'Planning the next move.' : busy ? 'Moving the pieces.' : instruction}</span></div>{state.stage === 'main' && humanTurn && <div className="selection-actions">{total(selection) > 0 && <button className="text-button" onClick={() => setSelection([0, 0, 0, 0, 0, 0])}>Clear</button>}<button className="primary-button" disabled={!selectedAction || busy} onClick={() => selectedAction && act(selectedAction)}>Take {total(selection) || ''} {total(selection) === 1 ? 'gem' : 'gems'}</button></div>}{state.stage === 'payment' && humanTurn && <span className="dock-note">Your card is waiting.</span>}{state.finalRound && <span className="final-round">Final round · equal turns</span>}</section>
      {actionError && <p className="inline-error" role="alert">{actionError}</p>}
      {game.status === 'error' && <div className="inline-error" role="alert"><p>{game.error}</p><button onClick={() => void client.current?.retry().catch(() => {})}>Restart this game</button></div>}
      {state.stage === 'return' && humanTurn && <section className="return-chooser" aria-label="Choose gems to return"><div className="return-tokens">{state.players[state.humanSeat].tokens.map((n, c) => <button key={c} className={`return-token ${selection[c] ? 'selected-return' : ''}`} disabled={!n || busy} onClick={() => toggleGem(c)} aria-label={`Return ${COLOR_NAMES[c]} gems, ${n} held, ${selection[c]} selected`}><Gem color={c}/><span>{selection[c]} / {n}</span></button>)}</div><button className="primary-button" disabled={!selectedAction || busy} onClick={() => selectedAction && act(selectedAction)}>Return {total(selection) || ''} {total(selection) === 1 ? 'gem' : 'gems'}</button><button className="text-button" onClick={() => setSelection([0, 0, 0, 0, 0, 0])}>Clear</button></section>}
      <PlayerArea player={state.players[state.humanSeat]} human active={Boolean(humanTurn)} onCollection={() => setCollection(state.players[state.humanSeat])}>
        <div className="human-reserves" data-reserve-seat={state.humanSeat} aria-label="Your reserved cards"><span className="board-label">Reserved <span>{state.players[state.humanSeat].reservedCount} / 3</span></span>{state.players[state.humanSeat].reserved.filter(Boolean).map((r, i) => r?.card && <div key={r.card.id} data-reserved-slot={i}><DevelopmentCard card={r.card} label={`your reserved card ${i + 1}`} compact disabled={busy || !humanTurn || state.stage !== 'main'} buy={state.legalActions.find(a => a.kind === 'buy_reserved' && a.reservedIndex === i)} onAction={act} onInspect={() => setInspect({ card: r.card!, location: `Your reserved card ${i + 1}` })}/></div>)}</div>
      </PlayerArea>
      <footer className="table-footer"><a href="https://github.com/paytonjjones/splendorust" target="_blank" rel="noreferrer">Research & code</a><span title="The confirmed model and search configuration loaded for this game.">Champion {game.champion?.id || '…'} <span className="footer-dot">·</span> Local play</span><div className="game-log-row"><span role="status">{logStatus}</span><button className="text-button" disabled={exporting} onClick={() => void downloadGames()}>{exporting ? 'Preparing download…' : 'Download your games'}</button></div></footer>
    </main>}
    {help && <Modal title="How to play" onClose={() => setHelp(false)}><p className="help-intro">Build a collection of gem cards. Reach 15 prestige to trigger the final round. Both players get the same number of turns.</p><ol className="rules-list"><li><strong>Take gems.</strong> Take 3 different colors, or 2 of one color when that pile has at least 4. If fewer than 3 colors remain, take one from each available color.</li><li><strong>Buy a card.</strong> Spend its gem cost. Every purchased card gives a permanent discount in its bonus color. Some also give prestige.</li><li><strong>Reserve for later.</strong> Keep up to 3 cards. Reserve from the market or a hidden deck, and take 1 gold if the bank has any. Gold can pay for any color.</li><li><strong>Earn a patron.</strong> Meet a noble’s bonus requirements to gain 3 prestige. A noble uses no gems or bonuses.</li></ol><p className="rule-fine">Keep at most 10 tokens, including gold. Return any excess at the end of your turn. Highest prestige wins; a tie goes to the player with fewer purchased cards. An exact tie is shared.</p><p className="rule-fine">Keyboard: use the arrow keys to move around the board. Press Enter to select a gem or use a control. Select gems, then move to Take gems and press Enter. Use a card’s Reserve control to keep it for later. Tab and Space also work. In a payment list, use Up and Down to choose gold. Use Left or Right to move to a payment button. Escape closes help and card details.</p><p className="rule-fine">Game moves are saved for training research. No player names or accounts are collected. Use Download your games for a copy of the records from this browser.</p><button className="primary-button" onClick={() => setHelp(false)}>Back to the table</button></Modal>}
    {restart && <Modal title="Start a fresh game?" onClose={() => setRestart(false)}><p>Your current collection will be cleared.</p><div className="modal-actions"><button className="text-button" onClick={() => setRestart(false)}>Keep playing</button><button className="primary-button" onClick={newGame}>New game</button></div></Modal>}
    {inspect && state && <Modal title={inspect.location} onClose={() => setInspect(null)}><div className="card-inspection"><DevelopmentCard card={inspect.card} label={inspect.location} disabled onAction={act} onInspect={() => {}}/><div><p>{inspect.card.points} prestige · {COLOR_NAMES[inspect.card.bonus]} bonus</p><p className="detail-label">Printed cost</p><Cost amounts={inspect.card.cost}/><p className="detail-label">After your bonuses</p><Cost amounts={inspect.card.cost.map((n, c) => Math.max(0, n - state.players[state.humanSeat].bonuses[c]))}/><p className="rule-fine">Your gems and gold cannot pay this cost yet.</p></div></div>{inspect.reserve && <button className="primary-button" disabled={busy} onClick={() => act(inspect.reserve!)}>Reserve card{state.bank[5] ? ' + take 1 gold' : ''}</button>}</Modal>}
    {collection && <Modal title={collection.seat === state?.humanSeat ? 'Your collection' : 'The champion’s collection'} onClose={() => setCollection(null)}><p>{collection.ownedCards.length} purchased {collection.ownedCards.length === 1 ? 'card' : 'cards'} · {collection.score} prestige</p><div className="collection-grid">{collection.ownedCards.length ? collection.ownedCards.map(card => <DevelopmentCard key={card.id} card={card} label="purchased card" compact disabled onAction={() => {}} onInspect={() => {}}/>) : <p className="rule-fine">The collection is waiting for its first card.</p>}</div></Modal>}
    {state?.stage === 'payment' && humanTurn && <Modal title="How would you like to pay?" onClose={() => {}} dismissible={false}><PaymentChooser key={state.revision} state={state} disabled={busy} onAction={act}/></Modal>}
    {state?.result && !hideResult && <Modal title={state.result.status === 'blocked' ? state.result.reason === 'decision_limit' ? 'The game reached its decision limit.' : 'The game has no legal next move.' : state.result.winnerMask === 3 ? 'An even match.' : state.result.winnerMask & (1 << state.humanSeat) ? 'You win' : 'SplendoRust wins'} className="result-modal" onClose={() => setHideResult(true)}><Seal variant={state.turn}/>{state.result.status === 'blocked' ? <p>{state.result.reason === 'decision_limit' ? 'This game stopped at the decision limit. No winner has been assigned.' : 'The published rules do not give a result for this position. No winner has been assigned.'}</p> : <><p className="result-line">{state.result.winnerMask === 3 ? 'You and SplendoRust share the victory.' : state.result.winnerMask & (1 << state.humanSeat) ? 'You beat SplendoRust.' : 'SplendoRust wins this one.'}</p><div className="result-scores"><span>You <strong>{state.players[state.humanSeat].score}</strong></span><span>SplendoRust <strong>{state.players[1 - state.humanSeat].score}</strong></span></div><p className="rule-fine">{state.players[0].score === state.players[1].score ? 'The player with fewer purchased cards wins a prestige tie.' : 'The final round gave both players the same number of turns.'}</p></>}<div className="modal-actions"><button className="text-button" onClick={() => setHideResult(true)}>View the board</button><button className="primary-button" onClick={newGame}>Play again</button></div></Modal>}
  </>;
}
