import { useMemo } from 'react';
import { useLocalStorage } from './useLocalStorage';
import type { PachislotEntry } from '../types/entry';
import { parseDateKey } from '../utils/date';

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

export interface Totals {
  investment: number;
  recovery: number;
  profit: number;
  count: number;
}

function emptyTotals(): Totals {
  return { investment: 0, recovery: 0, profit: 0, count: 0 };
}

function addEntryToTotals(totals: Totals, entry: PachislotEntry): Totals {
  totals.investment += entry.investment;
  totals.recovery += entry.recovery;
  totals.profit += profit(entry);
  totals.count += 1;
  return totals;
}

export function sumTotals(entries: PachislotEntry[]): Totals {
  return entries.reduce(addEntryToTotals, emptyTotals());
}

export interface MonthlyTotals extends Totals {
  month: number;
}

export function monthlyTotalsForYear(entries: PachislotEntry[], year: number): MonthlyTotals[] {
  const months: MonthlyTotals[] = Array.from({ length: 12 }, (_, month) => ({ month, ...emptyTotals() }));
  for (const entry of entriesForYear(entries, year)) {
    const { month } = parseDateKey(entry.date);
    addEntryToTotals(months[month], entry);
  }
  return months;
}

function groupTotalsByProfit<K extends string, T extends Totals & Record<K, string>>(
  entries: PachislotEntry[],
  key: K,
  getGroupName: (entry: PachislotEntry) => string,
): T[] {
  const map = new Map<string, T>();
  for (const entry of entries) {
    const groupName = getGroupName(entry);
    const existing = map.get(groupName) ?? ({ [key]: groupName, ...emptyTotals() } as T);
    addEntryToTotals(existing, entry);
    map.set(groupName, existing);
  }
  return Array.from(map.values()).sort((a, b) => b.profit - a.profit);
}

export interface MachineTotals extends Totals {
  machineName: string;
}

export function machineTotals(entries: PachislotEntry[]): MachineTotals[] {
  return groupTotalsByProfit(entries, 'machineName', (e) => e.machineName);
}

export interface HallTotals extends Totals {
  hallName: string;
}

export function hallTotals(entries: PachislotEntry[]): HallTotals[] {
  return groupTotalsByProfit(entries, 'hallName', (e) => e.hallName);
}
