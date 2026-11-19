const badge = document.querySelector('.badge-sheet');
const badgeName = badge.querySelector('span');

function printBadge() {
  const style = getComputedStyle(badge);
  const availableWidth = badge.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  const textWidth = badgeName.getBoundingClientRect().width;
  if (textWidth > availableWidth) {
    badgeName.style.fontSize = `${parseFloat(getComputedStyle(badgeName).fontSize) * availableWidth / textWidth}px`;
  }
  window.print();
}

document.querySelectorAll('[data-print-badge]').forEach((control) => {
  control.addEventListener('click', (event) => {
    if (typeof window.print !== 'function') return;
    event.preventDefault();
    printBadge();
  });
});
