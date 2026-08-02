import { useState } from 'react';
import type { EntryDraft } from '../types/entry';
import { calcDurationMinutes, formatDuration } from '../utils/time';

interface EntryFormProps {
  initial: EntryDraft;
  hallNames: string[];
  machineNames: string[];
  onSave: (draft: EntryDraft) => void;
  onCancel: () => void;
  onDelete?: () => void;
}

const emptyDraft: EntryDraft = {
  hallName: '',
  machineName: '',
  investment: '',
  recovery: '',
  startTime: '',
  endTime: '',
};

export function EntryForm({ initial, hallNames, machineNames, onSave, onCancel, onDelete }: EntryFormProps) {
  const [draft, setDraft] = useState<EntryDraft>(initial);

  const duration = calcDurationMinutes(draft.startTime, draft.endTime);
  const canSave = draft.hallName.trim() !== '' && draft.machineName.trim() !== '';

  const set = <K extends keyof EntryDraft>(key: K, value: EntryDraft[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <form
      className="entry-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (canSave) onSave(draft);
      }}
    >
      <label className="field">
        <span>ホール名</span>
        <input
          list="hall-names"
          value={draft.hallName}
          onChange={(e) => set('hallName', e.target.value)}
          placeholder="例：〇〇ホール"
          required
        />
        <datalist id="hall-names">
          {hallNames.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </label>

      <label className="field">
        <span>機種名</span>
        <input
          list="machine-names"
          value={draft.machineName}
          onChange={(e) => set('machineName', e.target.value)}
          placeholder="例：〇〇スロット"
          required
        />
        <datalist id="machine-names">
          {machineNames.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </label>

      <div className="field-row">
        <label className="field">
          <span>投資額</span>
          <input
            type="number"
            inputMode="numeric"
            min="0"
            value={draft.investment}
            onChange={(e) => set('investment', e.target.value)}
            placeholder="0"
          />
        </label>
        <label className="field">
          <span>回収額</span>
          <input
            type="number"
            inputMode="numeric"
            min="0"
            value={draft.recovery}
            onChange={(e) => set('recovery', e.target.value)}
            placeholder="0"
          />
        </label>
      </div>

      <div className="field-row">
        <label className="field">
          <span>開始時間</span>
          <input type="time" value={draft.startTime} onChange={(e) => set('startTime', e.target.value)} />
        </label>
        <label className="field">
          <span>終了時間</span>
          <input type="time" value={draft.endTime} onChange={(e) => set('endTime', e.target.value)} />
        </label>
      </div>

      <div className="duration-display">
        稼働時間：<strong>{formatDuration(duration)}</strong>
      </div>

      <div className="form-actions">
        {onDelete && (
          <button type="button" className="button-danger" onClick={onDelete}>
            削除
          </button>
        )}
        <button type="button" className="button-secondary" onClick={onCancel}>
          キャンセル
        </button>
        <button type="submit" className="button-primary" disabled={!canSave}>
          保存
        </button>
      </div>
    </form>
  );
}

export { emptyDraft };
