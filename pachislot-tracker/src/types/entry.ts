export interface PachislotEntry {
  id: string;
  /** YYYY-MM-DD */
  date: string;
  hallName: string;
  machineName: string;
  investment: number;
  recovery: number;
  /** HH:mm */
  startTime: string;
  /** HH:mm */
  endTime: string;
}

export interface EntryDraft {
  hallName: string;
  machineName: string;
  investment: string;
  recovery: string;
  startTime: string;
  endTime: string;
}
