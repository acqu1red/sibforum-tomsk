const badge = document.querySelector('.badge');
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

document.getElementById('print-badge').addEventListener('click', printBadge);
window.addEventListener('load', printBadge, { once: true });
