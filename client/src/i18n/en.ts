import type de from './de';

// English is the second UI language; keys must match de.ts (checked by a test).
const en: typeof de = {
  app: { name: 'Anthology' },
  nav: {
    streaming: 'Streaming',
    local: 'Local',
    works: 'Works',
    settings: 'Settings',
    main: 'Main navigation',
  },
  connection: {
    offline: 'Not connected',
    connecting: 'Connecting …',
    live: 'Connected · live',
    reconnecting: 'Reconnecting',
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
