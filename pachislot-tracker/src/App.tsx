import { useState } from 'react';
import { CalendarScreen } from './screens/CalendarScreen';
import { DayScreen } from './screens/DayScreen';
import { StatsScreen } from './screens/StatsScreen';
import { useEntries } from './hooks/useEntries';
import type { EntryDraft } from './types/entry';

function toEntryFields(dateKey: string, draft: EntryDraft) {
  return {
    date: dateKey,
    hallName: draft.hallName.trim(),
    machineName: draft.machineName.trim(),
    investment: Number(draft.investment) || 0,
    recovery: Number(draft.recovery) || 0,
    startTime: draft.startTime,
    endTime: draft.endTime,
  };
}

function App() {
  const { entries, entriesByDate, hallNames, machineNames, addEntry, updateEntry, deleteEntry } = useEntries();
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [showStats, setShowStats] = useState(false);

  if (selectedDate) {
    const dayEntries = entriesByDate.get(selectedDate) ?? [];
    return (
      <DayScreen
        dateKey={selectedDate}
        entries={dayEntries}
        hallNames={hallNames}
        machineNames={machineNames}
        onBack={() => setSelectedDate(null)}
        onAdd={(draft) => addEntry(toEntryFields(selectedDate, draft))}
        onUpdate={(id, draft) => updateEntry(id, toEntryFields(selectedDate, draft))}
        onDelete={deleteEntry}
      />
    );
  }

  if (showStats) {
    return <StatsScreen entries={entries} onBack={() => setShowStats(false)} />;
  }

  return <CalendarScreen entries={entries} onSelectDate={setSelectedDate} onOpenStats={() => setShowStats(true)} />;
}

export default App;
