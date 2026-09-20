import { useMemo, useState } from 'react';
import { SummaryBar } from '../components/SummaryBar';
import { CalendarGrid } from '../components/CalendarGrid';
import { formatYearMonth, todayKey } from '../utils/date';
import { entriesForMonth, entriesForYear, sumTotals, profit as entryProfit } from '../hooks/useEntries';
import type { PachislotEntry } from '../types/entry';

interface CalendarScreenProps {
  entries: PachislotEntry[];
  onSelectDate: (key: string) => void;
  onOpenStats: () => void;
}

export function CalendarScreen({ entries, onSelectDate, onOpenStats }: CalendarScreenProps) {
  const today = useMemo(() => todayKey(), []);
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());

  const yearTotals = useMemo(() => sumTotals(entriesForYear(entries, year)), [entries, year]);
  const monthTotals = useMemo(() => sumTotals(entriesForMonth(entries, year, month)), [entries, year, month]);

  const dailyProfit = useMemo(() => {
    const map = new Map<string, number>();
    for (const entry of entriesForMonth(entries, year, month)) {
      map.set(entry.date, (map.get(entry.date) ?? 0) + entryProfit(entry));
    }
    return map;
  }, [entries, year, month]);

  const goToMonth = (delta: number) => {
    const next = new Date(year, month + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth());
  };

  const goToday = () => {
    const now = new Date();
    setYear(now.getFullYear());
    setMonth(now.getMonth());
  };

  return (
    <div className="screen">
      <header className="app-header">
        <h1>収支管理</h1>
        <button className="stats-button" onClick={onOpenStats} aria-label="統計">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 20V10M12 20V4M20 20v-7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </header>

      <SummaryBar year={year} yearTotals={yearTotals} monthTotals={monthTotals} />

      <div className="month-nav">
        <button className="month-nav-arrow" onClick={() => goToMonth(-1)} aria-label="前の月">
          ‹
        </button>
        <div className="month-nav-center">
          <span className="month-label">{formatYearMonth(year, month)}</span>
          <button className="today-button" onClick={goToday}>
            今日
          </button>
        </div>
        <button className="month-nav-arrow" onClick={() => goToMonth(1)} aria-label="次の月">
          ›
        </button>
      </div>

      <CalendarGrid
        year={year}
        month={month}
        todayKey={today}
        selectedKey={null}
        dailyProfit={dailyProfit}
        onSelectDate={onSelectDate}
      />
    </div>
  );
}
