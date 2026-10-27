/** The part of `HTMLAudioElement` the player uses (tests replace it with a fake). */
export interface AudioLike extends EventTarget {
  src: string;
  currentTime: number;
  readonly duration: number;
  readonly paused: boolean;
  volume: number;
  play(): Promise<void>;
  pause(): void;
  canPlayType(type: string): string;
}

let factory: () => AudioLike = () => new Audio();

export function createAudio(): AudioLike {
  return factory();
}

/** Tests: use another audio element. */
export function setAudioFactory(create: () => AudioLike): void {
  factory = create;
}
