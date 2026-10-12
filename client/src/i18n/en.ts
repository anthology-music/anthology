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
