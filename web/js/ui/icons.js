// 선 아이콘 — PC 앱 왼쪽 메뉴(python/planner/navicons.py)와 같은 그림을 SVG 로.
//
// 이모지는 폰마다 모양·색이 달라 메뉴가 들쭉날쭉하고 테마색을 못 따른다.
// 24칸 바둑판 위에 가는 선으로 그리고, 색은 글자색(currentColor)을 따른다.
const P = {
  grid: '<rect x="4" y="4" width="7" height="7" rx="2"/><rect x="13" y="4" width="7" height="7" rx="2"/>'
      + '<rect x="4" y="13" width="7" height="7" rx="2"/><rect x="13" y="13" width="7" height="7" rx="2"/>',
  folder: '<path d="M3.5 7Q3.5 5 5.5 5H9.5L11.5 7.5H18.5Q20.5 7.5 20.5 9.5V17.5Q20.5 19.5 18.5 19.5H5.5'
        + 'Q3.5 19.5 3.5 17.5Z"/>',
  people: '<circle cx="9.5" cy="8.5" r="3.4"/><path d="M3.5 19.5C3.5 15 15.5 15 15.5 19.5"/>'
        + '<path d="M15.3 5.6A3.1 3.1 0 0 1 17.6 11.4"/><path d="M17.5 14.6C19.5 15.2 20.6 16.8 20.6 19.5"/>',
  calc: '<rect x="5" y="3.5" width="14" height="17" rx="3"/><rect x="8" y="6.5" width="8" height="3.5" rx="1"/>'
      + '<path d="M8.8 13.5h.01M12 13.5h.01M15.2 13.5h.01M8.8 17h.01M12 17h.01M15.2 17h.01"/>',
  search: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15L20 20"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8h.01"/>',
  calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="3.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>'
          + '<path d="M8 14.5h.01M12 14.5h.01M16 14.5h.01M8 17.5h.01M12 17.5h.01"/>',
  tasks: '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="M7.5 12.2L10.6 15.2L16.5 9"/>',
  check: '<path d="M6 12.5L10 16.5L18 8"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6.5Q16 4 13.5 4H6.5Q4 4 4 6.5V13.5Q4 16 6.5 16H8"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4'
     + 'M5.6 18.4L7 17M17 7l1.4-1.4"/>',
  next: '<path d="M5 12h13M13 7l5 5-5 5"/>',
  logo: '<rect x="3.5" y="4.5" width="17" height="16" rx="4.5"/><path d="M3.5 9.5h17M8 2.8v3.4M16 2.8v3.4"/>'
      + '<path d="M8.5 14.6l2.4 2.3 4.6-4.6"/>',
  dot: '<circle cx="12" cy="12" r="4"/>',
};

export const NAMES = Object.keys(P);

/** <svg> 한 장. size 는 CSS px, 선 굵기는 PC 와 같은 1.7. */
export function icon(name, size = 22, cls = "ico") {
  return `<svg class="${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"`
       + ` stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"`
       + ` aria-hidden="true">${P[name] || P.dot}</svg>`;
}
