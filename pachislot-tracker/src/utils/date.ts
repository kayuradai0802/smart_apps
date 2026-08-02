export function toDateKey(year: number, month: number, day: number): string {
  const mm = String(month + 1).padStart(2, '0');
  const dd = String(day).padStart(2, '0');
  return `${year}-${mm}-${dd}`;
}

export function todayKey(): string {
  const now = new Date();
  return toDateKey(now.getFullYear(), now.getMonth(), now.getDate());
}

export function parseDateKey(key: string): { year: number; month: number; day: number } {
  const [y, m, d] = key.split('-').map(Number);
  return { year: y, month: m - 1, day: d };
}

const WEEKDAYS = ['日', '月', '火', '水', '木', '金', '土'] as const;

export function formatDateLabel(key: string): string {
  const { year, month, day } = parseDateKey(key);
  const weekday = WEEKDAYS[new Date(year, month, day).getDay()];
  return `${year}年${month + 1}月${day}日（${weekday}）`;
}

export function formatYearMonth(year: number, month: number): string {
  return `${year}年${month + 1}月`;
}

/** Weeks of Date objects (including leading/trailing days from adjacent months) for a month calendar grid. */
export function buildCalendarWeeks(year: number, month: number): Date[][] {
  const firstOfMonth = new Date(year, month, 1);
  const nextMonthStart = new Date(year, month + 1, 1);
  const gridStart = new Date(year, month, 1 - firstOfMonth.getDay());

  const weeks: Date[][] = [];
  const cursor = new Date(gridStart);
  while (cursor < nextMonthStart) {
    const week: Date[] = [];
    for (let i = 0; i < 7; i++) {
      week.push(new Date(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push(week);
  }
  return weeks;
}
