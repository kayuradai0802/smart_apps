import type { MonthlyTotals } from '../hooks/useEntries';

interface MonthlyBarChartProps {
  data: MonthlyTotals[];
}

function formatYenShort(amount: number): string {
  if (amount === 0) return '0';
  if (Math.abs(amount) >= 10000) return `${Math.round(amount / 1000) / 10}万`;
  return amount.toLocaleString();
}

export function MonthlyBarChart({ data }: MonthlyBarChartProps) {
  const maxValue = Math.max(1, ...data.map((m) => Math.max(m.investment, m.recovery)));

  return (
    <div className="bar-chart-wrap">
      <div className="bar-chart-legend">
        <span className="legend-item">
          <span className="legend-swatch investment" />
          投資
        </span>
        <span className="legend-item">
          <span className="legend-swatch recovery" />
          回収
        </span>
      </div>
      <div className="bar-chart-scale">最大 {formatYenShort(maxValue)}円</div>
      <div className="bar-chart">
        {data.map((m) => (
          <div className="bar-chart-col" key={m.month}>
            <div className="bar-chart-bars">
              <div
                className="bar-chart-bar investment"
                style={{ height: `${(m.investment / maxValue) * 100}%` }}
                title={`投資 ${m.investment.toLocaleString()}円`}
              />
              <div
                className="bar-chart-bar recovery"
                style={{ height: `${(m.recovery / maxValue) * 100}%` }}
                title={`回収 ${m.recovery.toLocaleString()}円`}
              />
            </div>
            <span className="bar-chart-month-label">{m.month + 1}月</span>
          </div>
        ))}
      </div>
    </div>
  );
}
