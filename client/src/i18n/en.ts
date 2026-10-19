import type de from './de';

// English is the second UI language; keys must match de.ts (checked by a test).
const en: typeof de = {
  app: { name: 'Anthology' },
  nav: {
    streaming: 'Streaming',
    local: 'Local',
    works: 'Works',
    settings: 'Settings',
    demo: 'Demo list',
    main: 'Main navigation',
  },
  connection: {
    offline: 'Not connected',
    connecting: 'Connecting …',
    live: 'Connected · live',
    reconnecting: 'Reconnecting',
    outdated: 'App outdated – please update',
  },
  auth: {
    username: 'User name',
    displayName: 'Display name',
    password: 'Password',
    passwordHint: 'At least 8 characters',
    login: { title: 'Sign in', submit: 'Sign in' },
    logout: 'Sign out',
    setup: {
      title: 'Set up Anthology',
      hint: 'Create the first account. It becomes the administrator of this installation.',
      submit: 'Create account',
    },
    errors: {
      required: 'Please fill in',
      username: 'Only letters, digits, dot, hyphen and underscore',
      invalid_credentials: 'User name or password is wrong.',
      setup_not_allowed: 'Setup has already been completed.',
      server_unreachable: 'The server cannot be reached.',
      signed_out: 'You have been signed out.',
      failed: 'That did not work. Please try again.',
    },
  },
  devices: {
    title: 'My devices',
    current: 'This device',
    lastUsed: 'Last used: {date}',
    signOut: 'Sign out',
    signOutNamed: 'Sign out {name}',
  },
  users: {
    title: 'Accounts',
    role: 'Role',
    roleOf: 'Role of {name}',
    active: 'Active',
    inactive: 'Deactivated',
    create: 'Create account',
    createSubmit: 'Create',
    errors: {
      last_admin: 'The last administrator cannot be demoted or deactivated.',
      conflict: 'This user name is already taken.',
      failed: 'That did not work. Please try again.',
    },
  },
  roles: { admin: 'Administrator', editor: 'Editor', listener: 'Listener' },
  userMenu: 'Account menu',
  demo: {
    title: 'Demo list',
    description: 'Generated list to test virtual scrolling and jumps (development only).',
    rows: 'rows',
    cached: 'from cache',
    unavailable:
      'The server does not offer the demo. Start it with ANTHOLOGY_DEV_DEMO=true and fill the table with "anthology dev seed-demo".',
  },
  jobs: {
    title: 'Jobs',
    overview: 'Job overview',
    counters: {
      total: 'Total',
      done: 'Done',
      running: 'Running',
      waiting: 'Waiting',
      failed: 'Failed',
    },
    status: {
      queued: 'Queued',
      running: 'Running',
      paused: 'Paused',
      done: 'Done',
      failed: 'Failed',
      cancelled: 'Cancelled',
    },
    by: 'by {name}',
    progressOf: 'Progress of {title}',
    showItems: 'Show items of {title}',
    hideItems: 'Hide items of {title}',
    itemsOf: 'Items of {title}',
    actions: {
      pause: 'Pause {title}',
      resume: 'Resume {title}',
      cancel: 'Cancel {title}',
    },
    empty: 'No jobs yet.',
    startDemo: 'Start demo job',
    errors: {
      forbidden: 'Only the creator of a job or an administrator may control it.',
      invalid_transition: 'The job has changed its status in the meantime.',
      demo_unavailable: 'The server does not offer the demo job (ANTHOLOGY_DEV_DEMO=true).',
      failed: 'That did not work. Please try again.',
    },
  },
  services: {
    title: 'Services',
    names: { tagger: 'Tagger (reads and writes tags)' },
    status: {
      available: 'Available',
      unavailable: 'Unreachable',
      incompatible: 'Incompatible version',
    },
    versions: 'Version {version} · interface {api}',
    none: 'No services checked yet.',
  },
  library: {
    title: 'Library',
    path: 'Path',
    sections: { releases: 'Albums', artists: 'Artists', tracks: 'Tracks' },
    artist: 'Artist',
    album: 'Album',
    releasesOf: 'Albums by {name}',
    tracksOf: 'Tracks of {title}',
    count: {
      releases: '{n} album | {n} albums',
      tracks: '{n} track | {n} tracks',
      discs: '{n} disc | {n} discs',
    },
    empty: {
      releases: 'The library has no albums yet.',
      artists: 'The library has no artists yet.',
      tracks: 'The library has no tracks yet.',
      artistReleases: 'This artist has no albums.',
      releaseTracks: 'This album has no tracks.',
    },
    missing: {
      artist: 'This artist does not exist.',
      release: 'This album does not exist.',
    },
    removed: {
      artist: 'This artist no longer exists.',
      release: 'This album no longer exists.',
    },
    back: 'Back to the library',
  },
  user: { signedOut: 'Not signed in' },
  pages: {
    streaming: {
      title: 'Streaming',
      description:
        'Acquire music from several sources. The server works through the orders even when you close the app.',
    },
    local: {
      title: 'Local',
      description: 'Listen to and edit the shared library.',
    },
    works: {
      title: 'Works',
      description: 'Works, arrangements and medleys with sheet music.',
    },
    settings: {
      title: 'Settings',
      description: 'This device and your account.',
    },
    notFound: { title: 'Page not found', back: 'To the library' },
  },
};

export default en;
