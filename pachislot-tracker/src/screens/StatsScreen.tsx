import { useMemo, useState } from 'react';
import { MonthlyBarChart } from '../components/MonthlyBarChart';
import { machineTotals, monthlyTotalsForYear } from '../hooks/useEntries';
import type { PachislotEntry } from '../types/entry';

interface StatsScreenProps {
  entries: PachislotEntry[];
  onBack: () => void;
}

function formatYen(amount: number): string {
  const sign = amount < 0 ? '-' : '';
  return `${sign}${Math.abs(amount).toLocaleString()}円`;
}

export function StatsScreen({ entries, onBack }: StatsScreenProps) {
  const [year, setYear] = useState(() => new Date().getFullYear());

  const monthly = useMemo(() => monthlyTotalsForYear(entries, year), [entries, year]);
  const machines = useMemo(() => machineTotals(entries), [entries]);

  return (
    <div className="screen">
      <header className="app-header">
        <button className="back-button" onClick={onBack} aria-label="戻る">
          ‹
        </button>
        <h1>統計</h1>
      </header>

      <div className="month-nav">
        <button className="month-nav-arrow" onClick={() => setYear((y) => y - 1)} aria-label="前の年">
          ‹
        </button>
        <div className="month-nav-center">
          <span className="month-label">{year}年</span>
        </div>
        <button className="month-nav-arrow" onClick={() => setYear((y) => y + 1)} aria-label="次の年">
          ›
        </button>
      </div>

      <div className="stats-section">
        <div className="stats-section-title">月別の投資・回収</div>
        <MonthlyBarChart data={monthly} />
      </div>

      <div className="stats-section">
        <div className="stats-section-title">機種別（全期間）</div>
        <div className="machine-rank-list">
          {machines.length === 0 && <p className="empty-message">まだ記録がありません</p>}
          {machines.map((m) => (
            <div className="machine-rank-row" key={m.machineName}>
              <div>
                <div className="machine-rank-name">{m.machineName}</div>
                <div className="machine-rank-meta">
                  投資 {m.investment.toLocaleString()}円 / 回収 {m.recovery.toLocaleString()}円 / {m.count}回
                </div>
              </div>
              <div className={`machine-rank-profit ${m.profit < 0 ? 'negative' : 'positive'}`}>
                {formatYen(m.profit)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
