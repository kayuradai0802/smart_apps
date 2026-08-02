import { useState } from 'react';
import type { EntryDraft, PachislotEntry } from '../types/entry';
import { emptyDraft, EntryForm } from '../components/EntryForm';
import { formatDateLabel } from '../utils/date';
import { calcDurationMinutes, formatDuration } from '../utils/time';
import { profit as entryProfit } from '../hooks/useEntries';

interface DayScreenProps {
  dateKey: string;
  entries: PachislotEntry[];
  hallNames: string[];
  machineNames: string[];
  onBack: () => void;
  onAdd: (draft: EntryDraft) => void;
  onUpdate: (id: string, draft: EntryDraft) => void;
  onDelete: (id: string) => void;
}

function formatYen(amount: number): string {
  const sign = amount < 0 ? '-' : '';
  return `${sign}${Math.abs(amount).toLocaleString()}円`;
}

function toDraft(entry: PachislotEntry): EntryDraft {
  return {
    hallName: entry.hallName,
    machineName: entry.machineName,
    investment: String(entry.investment),
    recovery: String(entry.recovery),
    startTime: entry.startTime,
    endTime: entry.endTime,
  };
}

export function DayScreen({
  dateKey,
  entries,
  hallNames,
  machineNames,
  onBack,
  onAdd,
  onUpdate,
  onDelete,
}: DayScreenProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [isAdding, setIsAdding] = useState(false);

  const dayTotal = entries.reduce((total, e) => total + entryProfit(e), 0);
  const showingForm = isAdding || editingId !== null;
  const editingEntry = entries.find((e) => e.id === editingId) ?? null;

  const closeForm = () => {
    setIsAdding(false);
    setEditingId(null);
  };

  return (
    <div className="screen">
      <header className="app-header">
        <button className="back-button" onClick={onBack} aria-label="戻る">
          ‹
        </button>
        <h1>{formatDateLabel(dateKey)}</h1>
      </header>

      <div className="day-summary">
        <span>その日の収支</span>
        <span className={dayTotal < 0 ? 'negative' : 'positive'}>{formatYen(dayTotal)}</span>
      </div>

      {showingForm ? (
        <EntryForm
          initial={editingEntry ? toDraft(editingEntry) : emptyDraft}
          hallNames={hallNames}
          machineNames={machineNames}
          onSave={(draft) => {
            if (editingId) {
              onUpdate(editingId, draft);
            } else {
              onAdd(draft);
            }
            closeForm();
          }}
          onCancel={closeForm}
          onDelete={editingId ? () => {
            onDelete(editingId);
            closeForm();
          } : undefined}
        />
      ) : (
        <>
          <div className="entry-list">
            {entries.length === 0 && <p className="empty-message">この日の記録はまだありません</p>}
            {entries.map((entry) => {
              const duration = calcDurationMinutes(entry.startTime, entry.endTime);
              const p = entryProfit(entry);
              return (
                <div key={entry.id} className="entry-card" onClick={() => setEditingId(entry.id)}>
                  <div className="entry-card-top">
                    <span className="entry-hall">{entry.hallName}</span>
                    <span className={`entry-profit ${p < 0 ? 'negative' : 'positive'}`}>{formatYen(p)}</span>
                  </div>
                  <div className="entry-machine">{entry.machineName}</div>
                  <div className="entry-meta">
                    <span>
                      投資 {entry.investment.toLocaleString()}円 / 回収 {entry.recovery.toLocaleString()}円
                    </span>
                    {entry.startTime && entry.endTime && (
                      <span>
                        {entry.startTime}〜{entry.endTime}（{formatDuration(duration)}）
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <button className="button-primary add-entry-button" onClick={() => setIsAdding(true)}>
            収支を入力する
          </button>
        </>
      )}
    </div>
  );
}
