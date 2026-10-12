// German is the first UI language (AGENTS.md).
export default {
  app: { name: 'Anthology' },
  nav: {
    streaming: 'Streaming',
    local: 'Lokal',
    works: 'Werke',
    settings: 'Einstellungen',
    main: 'Hauptnavigation',
  },
  connection: {
    offline: 'Nicht verbunden',
    connecting: 'Verbinde …',
    live: 'Verbunden · live',
    reconnecting: 'Verbindung wird wiederhergestellt',
    outdated: 'App veraltet – bitte aktualisieren',
  },
  auth: {
    username: 'Benutzername',
    displayName: 'Anzeigename',
    password: 'Passwort',
    passwordHint: 'Mindestens 8 Zeichen',
    login: { title: 'Anmelden', submit: 'Anmelden' },
    logout: 'Abmelden',
    setup: {
      title: 'Anthology einrichten',
      hint: 'Lege das erste Konto an. Es wird Administrator dieser Installation.',
      submit: 'Konto anlegen',
    },
    errors: {
      required: 'Bitte ausfüllen',
      username: 'Nur Buchstaben, Ziffern, Punkt, Binde- und Unterstrich',
      invalid_credentials: 'Benutzername oder Passwort ist falsch.',
      setup_not_allowed: 'Die Einrichtung ist bereits abgeschlossen.',
      server_unreachable: 'Der Server ist nicht erreichbar.',
      signed_out: 'Du wurdest abgemeldet.',
      failed: 'Das hat nicht geklappt. Bitte versuche es noch einmal.',
    },
  },
  devices: {
    title: 'Meine Geräte',
    current: 'Dieses Gerät',
    lastUsed: 'Zuletzt genutzt: {date}',
    signOut: 'Abmelden',
    signOutNamed: '{name} abmelden',
  },
  users: {
    title: 'Konten',
    role: 'Rolle',
    roleOf: 'Rolle von {name}',
    active: 'Aktiv',
    inactive: 'Deaktiviert',
    create: 'Konto anlegen',
    createSubmit: 'Anlegen',
    errors: {
      last_admin: 'Der letzte Administrator kann nicht herabgestuft oder deaktiviert werden.',
      conflict: 'Dieser Benutzername ist bereits vergeben.',
      failed: 'Das hat nicht geklappt. Bitte versuche es noch einmal.',
    },
  },
  roles: { admin: 'Administrator', editor: 'Redaktion', listener: 'Hören' },
  userMenu: 'Konto-Menü',
  user: { signedOut: 'Nicht angemeldet' },
  pages: {
    streaming: {
      title: 'Streaming',
      description:
        'Musik aus verschiedenen Quellen aufnehmen. Der Server arbeitet die Aufträge ab, auch wenn du die App schliesst.',
    },
    local: {
      title: 'Lokal',
      description: 'Die gemeinsame Bibliothek hören und bearbeiten.',
    },
    works: {
      title: 'Werke',
      description: 'Werke, Bearbeitungen und Medleys mit Noten.',
    },
    settings: {
      title: 'Einstellungen',
      description: 'Dieses Gerät und dein Konto.',
    },
    notFound: { title: 'Seite nicht gefunden', back: 'Zur Bibliothek' },
  },
};
