// In-memory notes store plus change fan-out to resource watchers.

export interface Note {
  id: string;
  notebook: string;
  title: string;
  body: string;
}

export const INDEX_URI = "notes://index";
export const noteUri = (id: string) => `notes://notes/${id}`;

type Listener = (uri: string) => void;

export class NoteStore {
  private notes = new Map<string, Note>();
  private counter = 0;
  private listeners = new Set<Listener>();

  constructor() {
    this.add("work", "Standup", "Discussed the release schedule and blockers.");
    this.add("work", "Retro actions", "Automate the changelog. Rotate the on-call.");
    this.add("personal", "Groceries", "Eggs, flour, coffee.");
  }

  /** Notes in numeric id order (ids are assigned increasing and never reused). */
  list(): Note[] {
    return [...this.notes.values()];
  }

  get(id: string): Note | undefined {
    return this.notes.get(id);
  }

  add(notebook: string, title: string, body: string): Note {
    const note = { id: `n${++this.counter}`, notebook, title, body };
    this.notes.set(note.id, note);
    this.emit(INDEX_URI);
    return note;
  }

  delete(id: string): boolean {
    if (!this.notes.delete(id)) return false;
    this.emit(INDEX_URI);
    this.emit(noteUri(id));
    return true;
  }

  onChange(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(uri: string) {
    for (const l of this.listeners) l(uri);
  }
}

export function renderNote(note: Note): string {
  return `# ${note.title}\n\n${note.body}\n`;
}
