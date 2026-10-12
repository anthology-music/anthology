import type { ClientMessage, ServerMessage } from '@anthology/api-types';

import type { SocketFactory, SocketLike } from '@/sync/connection';

/** A WebSocket double controlled by the test acting as server. */
export class FakeSocket implements SocketLike {
  onopen: SocketLike['onopen'] = null;
  onmessage: SocketLike['onmessage'] = null;
  onclose: SocketLike['onclose'] = null;
  readonly sent: ClientMessage[] = [];
  closedByClient: number | null = null;

  constructor(readonly url: string) {}

  send(data: string): void {
    this.sent.push(JSON.parse(data) as ClientMessage);
  }

  close(code = 1000): void {
    this.closedByClient = code;
  }

  open(): void {
    this.onopen?.({});
  }

  receive(message: ServerMessage): void {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  serverClose(code: number): void {
    this.onclose?.({ code });
  }

  last<T extends ClientMessage['type']>(type: T): Extract<ClientMessage, { type: T }> | undefined {
    return [...this.sent].reverse().find((message) => message.type === type) as
      Extract<ClientMessage, { type: T }> | undefined;
  }
}

export function fakeSockets() {
  const sockets: FakeSocket[] = [];
  const factory: SocketFactory = (url) => {
    const socket = new FakeSocket(url);
    sockets.push(socket);
    return socket;
  };
  return { sockets, factory, latest: () => sockets.at(-1)! };
}

export function welcome(): ServerMessage {
  return { type: 'welcome', data: { protocol: 1, current_seq: 0, oldest_seq: null } };
}
