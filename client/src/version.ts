// The client's version, built in (change first-release): Settings › About Anthology shows it next
// to the server's, so that a cached client older than its server is visible.
import { version } from '../package.json';

export const CLIENT_VERSION: string = version;
