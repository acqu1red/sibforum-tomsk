const badge = document.querySelector('.badge-sheet');
const ready = () => badge.complete && badge.naturalWidth > 0;

document.querySelectorAll('[data-print-badge]').forEach((control) => {
  if (control instanceof HTMLButtonElement) {
    control.disabled = !ready();
    badge.addEventListener('load', () => { control.disabled = false; }, { once: true });
  }
  control.addEventListener('click', (event) => {
    if (!ready() || typeof window.print !== 'function') return;
    event.preventDefault();
    window.print();
  });
});
