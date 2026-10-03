import { expect, type Locator, type Page } from '@playwright/test';

/** Find a route from the visible layout, then use real keys for every focus change.
 * Targets are semantic locators. There are no fixed coordinates or focus() calls.
 * A missing route is a failure: every game control must be reachable with arrows.
 */
export async function arrowTo(page: Page, target: Locator): Promise<void> {
  await expect(target).toBeEnabled();
  await target.evaluate(element => element.setAttribute('data-keyboard-test-target', 'true'));
  try {
    const route = await page.evaluate(() => {
      const scope = document.querySelector('dialog[open]') ?? document.body;
      const items = [...scope.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], select:not(:disabled), input:not(:disabled), [tabindex="0"]')]
        .filter(element => !element.matches('.skip-link') && element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden' && !element.closest('[inert], [aria-hidden="true"]'));
      const goal = items.findIndex(element => element.hasAttribute('data-keyboard-test-target'));
      if (goal < 0) throw new Error('The keyboard target is not an available control.');
      let start = items.indexOf(document.activeElement as HTMLElement);
      const prefix: string[] = [];
      if (start < 0) {
        start = items.findIndex(element => element.matches('.eligible-noble, .return-token, .payment-option'));
        if (start < 0) start = items.findIndex(element => element.matches('[data-bank-color]'));
        if (start < 0) start = 0;
        prefix.push('ArrowRight');
      }
      const keys = ['ArrowUp', 'ArrowLeft', 'ArrowRight', 'ArrowDown'];
      const queue = [{ index: start, path: prefix }];
      const visited = new Set<number>();
      while (queue.length) {
        const current = queue.shift()!;
        if (current.index === goal) return current.path;
        if (visited.has(current.index)) continue;
        visited.add(current.index);
        const active = items[current.index];
        const rect = active.getBoundingClientRect();
        for (const key of keys) {
          if (active.matches('select') && ['ArrowUp', 'ArrowDown'].includes(key)) continue;
          let next: HTMLElement | undefined;
          const group = active.closest('.bank-tokens, .return-tokens');
          if (group) {
            const row = items.filter(element => group.contains(element));
            const position = row.indexOf(active);
            const submit = group.matches('.bank-tokens')
              ? document.querySelector<HTMLElement>('#game-controls .selection-actions .primary-button:not(:disabled)')
              : group.parentElement?.querySelector<HTMLElement>('.primary-button:not(:disabled)');
            if (key === 'ArrowDown' && submit) next = submit;
            if (key === 'ArrowRight' || key === 'ArrowLeft') {
              next = key === 'ArrowRight' && position === row.length - 1 && submit
                ? submit : row[(position + (key === 'ArrowRight' ? 1 : -1) + row.length) % row.length];
            }
          }
          if (!next) {
            const horizontal = key === 'ArrowLeft' || key === 'ArrowRight';
            const sign = key === 'ArrowLeft' || key === 'ArrowUp' ? -1 : 1;
            next = items.filter(element => element !== active).map(element => {
              const box = element.getBoundingClientRect();
              const dx = box.left + box.width / 2 - rect.left - rect.width / 2;
              const dy = box.top + box.height / 2 - rect.top - rect.height / 2;
              return { element, along: (horizontal ? dx : dy) * sign, score: (horizontal ? dx : dy) * sign + Math.abs(horizontal ? dy : dx) * 3 };
            }).filter(candidate => candidate.along > 4).sort((a, b) => a.score - b.score)[0]?.element;
          }
          if (next && items.includes(next)) queue.push({ index: items.indexOf(next), path: [...current.path, key] });
        }
      }
      throw new Error(`No arrow route reaches ${items[goal].getAttribute('aria-label') ?? items[goal].textContent}.`);
    });
    for (const key of route) await page.keyboard.press(key);
    await expect(target).toBeFocused();
  } finally {
    await target.evaluate(element => element.removeAttribute('data-keyboard-test-target')).catch(() => {});
  }
}
