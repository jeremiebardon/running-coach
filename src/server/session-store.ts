import type { ModelMessage } from "ai";

/**
 * Conversation history per session.
 *
 * Port + in-memory adapter: good enough for a single-container POC. When you
 * run several replicas (or want history to survive restarts), implement the
 * same interface with Redis/Postgres — the server code doesn't change.
 */
export interface SessionStore {
  get(sessionId: string): Promise<ModelMessage[]>;
  save(sessionId: string, messages: ModelMessage[]): Promise<void>;
  delete(sessionId: string): Promise<void>;
}

export class InMemorySessionStore implements SessionStore {
  private readonly sessions = new Map<string, { messages: ModelMessage[]; touchedAt: number }>();

  constructor(
    private readonly opts = { maxMessages: 40, ttlMs: 2 * 60 * 60 * 1000 },
  ) {}

  async get(sessionId: string): Promise<ModelMessage[]> {
    this.evictExpired();
    return [...(this.sessions.get(sessionId)?.messages ?? [])];
  }

  async save(sessionId: string, messages: ModelMessage[]): Promise<void> {
    // Keep the tail only: bounds token cost and memory for long chats.
    this.sessions.set(sessionId, { messages: messages.slice(-this.opts.maxMessages), touchedAt: Date.now() });
  }

  async delete(sessionId: string): Promise<void> {
    this.sessions.delete(sessionId);
  }

  private evictExpired(): void {
    const cutoff = Date.now() - this.opts.ttlMs;
    for (const [id, s] of this.sessions) if (s.touchedAt < cutoff) this.sessions.delete(id);
  }
}
