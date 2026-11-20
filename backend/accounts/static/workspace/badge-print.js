const badge = document.querySelector('.badge-sheet');
function fitBadge() {
  const style = getComputedStyle(badge);
  const availableWidth = badge.getBoundingClientRect().width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  for (const line of badge.querySelectorAll('span')) {
    const textWidth = line.getBoundingClientRect().width;
    if (textWidth > availableWidth) {
      line.style.fontSize = `${parseFloat(getComputedStyle(line).fontSize) * availableWidth / textWidth}px`;
    }
  }
}

fitBadge();
document.querySelectorAll('[data-print-badge]').forEach((control) => {
  control.addEventListener('click', (event) => {
    if (typeof window.print !== 'function') return;
    event.preventDefault();
    fitBadge();
    window.print();
  });
});
