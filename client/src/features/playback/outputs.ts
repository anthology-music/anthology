import type { PlaybackOutputRow } from '@anthology/api-types';
import { computed, type ComputedRef } from 'vue';

import { getServices } from '@/services';
import { useSubscription } from '@/sync/useSubscription';

export type OutputRow = PlaybackOutputRow;

export interface OutputZone extends OutputRow {
  rooms: OutputRow[];
  system: OutputRow | undefined;
}

export interface Outputs {
  systems: OutputRow[];
  zones: OutputZone[];
  /** Rooms in no zone, per system. */
  freeRooms: OutputRow[];
}

/** Output systems, their zones and rooms, live (stream `playback.outputs`, spec: playback,
 * Output picker). Outputs are few: the whole list is one window. */
export function useOutputs(): ComputedRef<Outputs> {
  const subscription = useSubscription('playback.outputs', {}, [0, 500], { cache: false });
  return computed(() => {
    const rows = [...subscription.value.rows.entries()]
      .sort(([a], [b]) => a - b)
      .map(([, row]) => row as unknown as OutputRow);
    const systems = rows.filter((row) => row.kind === 'system');
    const rooms = rows.filter((row) => row.kind === 'room');
    const zones = rows
      .filter((row) => row.kind === 'zone')
      .map((zone) => ({
        ...zone,
        rooms: rooms.filter((room) => room.zone_id === zone.id),
        system: systems.find((system) => system.id === zone.system_id),
      }));
    return { systems, zones, freeRooms: rooms.filter((room) => room.zone_id === null) };
  });
}

export type OutputProblem = 'output_offline' | 'output_failed' | 'unknown_output' | 'failed';

function problem(error: unknown, status: number): OutputProblem {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (detail === 'output_offline' || detail === 'output_failed' || detail === 'unknown_output')
    return detail;
  return status === 404 ? 'unknown_output' : 'failed';
}

/** Zone management for every signed-in user (spec: Zone management); null when it worked. */
export async function setZoneVolume(
  zoneId: string,
  change: { volume?: number; muted?: boolean },
): Promise<OutputProblem | null> {
  const { error, response } = await getServices().api.PUT(
    '/api/v1/playback/zones/{zone_id}/volume',
    {
      params: { path: { zone_id: zoneId } },
      body: change,
    },
  );
  return response.ok ? null : problem(error, response.status);
}

export async function setRoomVolume(
  roomId: string,
  change: { volume?: number; muted?: boolean },
): Promise<OutputProblem | null> {
  const { error, response } = await getServices().api.PUT(
    '/api/v1/playback/rooms/{room_id}/volume',
    {
      params: { path: { room_id: roomId } },
      body: change,
    },
  );
  return response.ok ? null : problem(error, response.status);
}

/** Add the room to a zone; null forms a new zone of the room alone. */
export async function joinZone(
  roomId: string,
  zoneId: string | null,
): Promise<OutputProblem | null> {
  const { error, response } = await getServices().api.PUT('/api/v1/playback/rooms/{room_id}/zone', {
    params: { path: { room_id: roomId } },
    body: { zone_id: zoneId },
  });
  return response.ok ? null : problem(error, response.status);
}

export async function leaveZone(roomId: string): Promise<OutputProblem | null> {
  const { error, response } = await getServices().api.DELETE(
    '/api/v1/playback/rooms/{room_id}/zone',
    {
      params: { path: { room_id: roomId } },
    },
  );
  return response.ok ? null : problem(error, response.status);
}

/** Admins: a system the server cannot discover (spec: Output discovery and addresses). */
export async function addSystem(address: string): Promise<'invalid_address' | 'failed' | null> {
  const { error, response } = await getServices().api.POST('/api/v1/playback/systems', {
    body: { adapter: 'raumfeld', address },
  });
  if (response.ok) return null;
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return detail === 'invalid_address' ? 'invalid_address' : 'failed';
}

export async function removeSystem(systemId: string): Promise<boolean> {
  const { response } = await getServices().api.DELETE('/api/v1/playback/systems/{system_id}', {
    params: { path: { system_id: systemId } },
  });
  return response.ok;
}
