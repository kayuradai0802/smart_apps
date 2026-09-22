import type { HallTotals } from '../hooks/useEntries';

interface HallProfitChartProps {
  data: HallTotals[];
}

function formatYen(amount: number): string {
  const sign = amount < 0 ? '-' : '';
  return `${sign}${Math.abs(amount).toLocaleString()}円`;
}

export function HallProfitChart({ data }: HallProfitChartProps) {
  const maxAbs = Math.max(1, ...data.map((h) => Math.abs(h.profit)));

  return (
    <div className="hall-chart">
      {data.map((h) => (
        <div className="hall-chart-row" key={h.hallName}>
          <div className="hall-chart-head">
            <span className="hall-chart-name">{h.hallName}</span>
            <span className={`hall-chart-value ${h.profit < 0 ? 'negative' : 'positive'}`}>
              {formatYen(h.profit)}
            </span>
          </div>
          <div className="hall-chart-track">
            <div
              className={`hall-chart-bar ${h.profit < 0 ? 'negative' : 'positive'}`}
              style={{ width: `${(Math.abs(h.profit) / maxAbs) * 100}%` }}
            />
          </div>
          <div className="hall-chart-meta">
            投資 {h.investment.toLocaleString()}円 / 回収 {h.recovery.toLocaleString()}円 / {h.count}回
          </div>
        </div>
      ))}
    </div>
  );
}
