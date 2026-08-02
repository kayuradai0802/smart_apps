import { useMemo } from 'react';
import { useLocalStorage } from './useLocalStorage';
import type { PachislotEntry } from '../types/entry';

const STORAGE_KEY = 'pachislot-entries';

function createId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function profit(entry: PachislotEntry): number {
  return entry.recovery - entry.investment;
}

export function useEntries() {
  const [entries, setEntries] = useLocalStorage<PachislotEntry[]>(STORAGE_KEY, []);

  const addEntry = (entry: Omit<PachislotEntry, 'id'>) => {
    setEntries((prev) => [...prev, { ...entry, id: createId() }]);
  };

  const updateEntry = (id: string, patch: Omit<PachislotEntry, 'id'>) => {
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...patch, id } : e)));
  };

  const deleteEntry = (id: string) => {
    setEntries((prev) => prev.filter((e) => e.id !== id));
  };

  const entriesByDate = useMemo(() => {
    const map = new Map<string, PachislotEntry[]>();
    for (const entry of entries) {
      const list = map.get(entry.date) ?? [];
      list.push(entry);
      map.set(entry.date, list);
    }
    return map;
  }, [entries]);

  const hallNames = useMemo(
    () => Array.from(new Set(entries.map((e) => e.hallName).filter(Boolean))).sort(),
    [entries],
  );

  const machineNames = useMemo(
    () => Array.from(new Set(entries.map((e) => e.machineName).filter(Boolean))).sort(),
    [entries],
  );

  return { entries, entriesByDate, hallNames, machineNames, addEntry, updateEntry, deleteEntry };
}

export function sumProfit(entries: PachislotEntry[]): number {
  return entries.reduce((total, e) => total + profit(e), 0);
}

export function entriesForMonth(entries: PachislotEntry[], year: number, month: number): PachislotEntry[] {
  const prefix = `${year}-${String(month + 1).padStart(2, '0')}`;
  return entries.filter((e) => e.date.startsWith(prefix));
}

export function entriesForYear(entries: PachislotEntry[], year: number): PachislotEntry[] {
  const prefix = `${year}-`;
  return entries.filter((e) => e.date.startsWith(prefix));
}
