import { useEffect, useRef } from 'react';

const controls = 'button:not(:disabled), a[href], select:not(:disabled), input:not(:disabled), [tabindex="0"]';

function visibleControls(scope: ParentNode): HTMLElement[] {
  return [...scope.querySelectorAll<HTMLElement>(controls)].filter(element => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return !element.matches('.skip-link') && rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' &&
      !element.closest('[inert], [aria-hidden="true"]');
  });
}

function navigationScope(): HTMLElement {
  return document.querySelector<HTMLElement>('dialog[open]') ?? document.body;
}

function firstGameControl(items: HTMLElement[]): HTMLElement | undefined {
  return items.find(element => element.matches('.eligible-noble, .return-token, .payment-option')) ??
    items.find(element => element.matches('[data-bank-color]')) ?? items[0];
}

/** Arrow keys move the focus in the direction shown on the board. Enter stays native. */
export function useBoardKeyboard(ready: boolean, revision: number) {
  const keyboard = useRef(false);
  const lastFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const pointer = () => { keyboard.current = false; };
    const focus = (event: FocusEvent) => {
      if (event.target instanceof HTMLElement && event.target !== document.body) lastFocused.current = event.target;
    };
    const key = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (['Tab', 'Enter', ' '].includes(event.key)) keyboard.current = true;
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
      const active = document.activeElement as HTMLElement | null;
      // Up and Down change a native list. Left and Right let the player leave it.
      if (active?.matches('select') && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) return;
      if (active?.matches('input, textarea, [contenteditable="true"]')) return;
      const items = visibleControls(navigationScope());
      if (!items.length) return;
      keyboard.current = true;
      event.preventDefault();
      if (!active || !items.includes(active)) {
        firstGameControl(items)?.focus();
        return;
      }
      const tokenGroup = active.closest('.bank-tokens, .return-tokens');
      if (tokenGroup) {
        const tokens = items.filter(element => tokenGroup.contains(element));
        const index = tokens.indexOf(active);
        const submit = tokenGroup.matches('.bank-tokens')
          ? document.querySelector<HTMLElement>('#game-controls .selection-actions .primary-button:not(:disabled)')
          : tokenGroup.parentElement?.querySelector<HTMLElement>('.primary-button:not(:disabled)');
        if (event.key === 'ArrowDown' && submit) { submit.focus(); return; }
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
          if (event.key === 'ArrowRight' && index === tokens.length - 1 && submit) submit.focus();
          else tokens[(index + (event.key === 'ArrowRight' ? 1 : -1) + tokens.length) % tokens.length]?.focus();
          return;
        }
      }
      const rect = active.getBoundingClientRect();
      const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
      const horizontal = event.key === 'ArrowLeft' || event.key === 'ArrowRight';
      const sign = event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 1;
      const candidates = items.filter(element => element !== active).map(element => {
        const next = element.getBoundingClientRect();
        const dx = next.left + next.width / 2 - x, dy = next.top + next.height / 2 - y;
        const along = (horizontal ? dx : dy) * sign;
        const across = Math.abs(horizontal ? dy : dx);
        return { element, along, score: along + across * 3 };
      }).filter(candidate => candidate.along > 4).sort((a, b) => a.score - b.score);
      candidates[0]?.element.focus();
    };
    document.addEventListener('keydown', key);
    document.addEventListener('pointerdown', pointer);
    document.addEventListener('focusin', focus);
    return () => {
      document.removeEventListener('keydown', key);
      document.removeEventListener('pointerdown', pointer);
      document.removeEventListener('focusin', focus);
    };
  }, []);

  useEffect(() => {
    if (!ready || !keyboard.current) return;
    const scope = navigationScope();
    const items = visibleControls(scope);
    if (items.includes(document.activeElement as HTMLElement)) return;
    const previous = lastFocused.current;
    (previous && items.includes(previous) ? previous : firstGameControl(items))?.focus();
  }, [ready, revision]);
}
