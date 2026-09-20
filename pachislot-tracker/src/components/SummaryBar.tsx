import type { Totals } from '../hooks/useEntries';

interface SummaryBarProps {
  year: number;
  yearTotals: Totals;
  monthTotals: Totals;
}

function formatYen(amount: number): string {
  const sign = amount < 0 ? '-' : '';
  return `${sign}${Math.abs(amount).toLocaleString()}円`;
}

function SummaryCard({ label, totals }: { label: string; totals: Totals }) {
  return (
    <div className="summary-card">
      <div className="summary-label">{label}</div>
      <div className={`summary-value ${totals.profit < 0 ? 'negative' : 'positive'}`}>
        {formatYen(totals.profit)}
      </div>
      <div className="summary-breakdown">
        <span>投資合計 {totals.investment.toLocaleString()}円</span>
        <span>回収合計 {totals.recovery.toLocaleString()}円</span>
      </div>
    </div>
  );
}

export function SummaryBar({ year, yearTotals, monthTotals }: SummaryBarProps) {
  return (
    <div className="summary-bar">
      <SummaryCard label={`${year}年 年間収支`} totals={yearTotals} />
      <SummaryCard label="今月の収支" totals={monthTotals} />
    </div>
  );
}
