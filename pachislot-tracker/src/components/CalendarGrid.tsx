import { buildCalendarWeeks, toDateKey } from '../utils/date';

const WEEKDAYS = ['日', '月', '火', '水', '木', '金', '土'];

interface CalendarGridProps {
  year: number;
  month: number;
  todayKey: string;
  selectedKey: string | null;
  dailyProfit: Map<string, number>;
  onSelectDate: (key: string) => void;
}

function formatYen(amount: number): string {
  const sign = amount < 0 ? '-' : '';
  return `${sign}${Math.abs(amount).toLocaleString()}`;
}

export function CalendarGrid({ year, month, todayKey, selectedKey, dailyProfit, onSelectDate }: CalendarGridProps) {
  const weeks = buildCalendarWeeks(year, month);

  return (
    <table className="calendar-grid">
      <thead>
        <tr>
          {WEEKDAYS.map((w, i) => (
            <th key={w} className={i === 0 ? 'sunday' : i === 6 ? 'saturday' : ''}>
              {w}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {weeks.map((week, wi) => (
          <tr key={wi}>
            {week.map((date) => {
              const key = toDateKey(date.getFullYear(), date.getMonth(), date.getDate());
              const inMonth = date.getMonth() === month;
              const profit = dailyProfit.get(key);
              const classes = [
                'calendar-cell',
                inMonth ? '' : 'outside-month',
                key === todayKey ? 'is-today' : '',
                key === selectedKey ? 'is-selected' : '',
              ]
                .filter(Boolean)
                .join(' ');
              return (
                <td key={key} className={classes} onClick={() => onSelectDate(key)}>
                  <span className="date-number">{date.getDate()}</span>
                  {profit !== undefined && (
                    <span className={`date-profit ${profit < 0 ? 'negative' : 'positive'}`}>
                      {formatYen(profit)}
                    </span>
                  )}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
