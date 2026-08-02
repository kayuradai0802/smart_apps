interface SummaryBarProps {
  year: number;
  yearProfit: number;
  monthProfit: number;
}

function formatYen(amount: number): string {
  const sign = amount < 0 ? '-' : '';
  return `${sign}${Math.abs(amount).toLocaleString()}円`;
}

export function SummaryBar({ year, yearProfit, monthProfit }: SummaryBarProps) {
  return (
    <div className="summary-bar">
      <div className="summary-card">
        <div className="summary-label">{year}年 年間収支</div>
        <div className={`summary-value ${yearProfit < 0 ? 'negative' : 'positive'}`}>
          {formatYen(yearProfit)}
        </div>
      </div>
      <div className="summary-card">
        <div className="summary-label">今月の収支</div>
        <div className={`summary-value ${monthProfit < 0 ? 'negative' : 'positive'}`}>
          {formatYen(monthProfit)}
        </div>
      </div>
    </div>
  );
}
