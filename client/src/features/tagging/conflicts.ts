/** A group of the conflict list: the stream parameter and its value. */
export interface ConflictGroup {
  param: 'field' | 'release_id' | 'artist_id' | 'source';
  value: string;
}
