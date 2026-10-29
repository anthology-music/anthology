import { defineConfig, type DefaultTheme } from 'vitepress';

// User manual (ADR 0023): English at the root, German under /de/, the same parts and pages in
// both languages (checked by scripts/check-pages.mjs).

export type Lang = 'en' | 'de';

interface Page {
  path: string;
  title: Record<Lang, string>;
}

export interface Part {
  dir: string;
  title: Record<Lang, string>;
  pages: Page[];
}

/** The four parts and their pages; every page exists in both languages. */
export const parts: Part[] = [
  {
    dir: 'general',
    title: { en: 'General', de: 'Allgemein' },
    pages: [
      { path: '', title: { en: 'What Anthology is', de: 'Was Anthology ist' } },
      { path: 'concepts', title: { en: 'Concepts', de: 'Grundbegriffe' } },
      { path: 'roles', title: { en: 'Roles and rights', de: 'Rollen und Rechte' } },
    ],
  },
  {
    dir: 'administration',
    title: { en: 'Installation and administration', de: 'Installation und Administration' },
    pages: [
      { path: '', title: { en: 'Overview', de: 'Überblick' } },
      { path: 'installation', title: { en: 'Installation', de: 'Installation' } },
      { path: 'configuration', title: { en: 'Configuration', de: 'Konfiguration' } },
      { path: 'first-steps', title: { en: 'First steps', de: 'Erste Schritte' } },
      { path: 'users', title: { en: 'Users and devices', de: 'Benutzer und Geräte' } },
      { path: 'import', title: { en: 'Importing a collection', de: 'Eine Sammlung importieren' } },
      { path: 'sources', title: { en: 'Source services', de: 'Quelldienste' } },
      { path: 'speakers', title: { en: 'Raumfeld speakers', de: 'Raumfeld-Lautsprecher' } },
      { path: 'maintenance', title: { en: 'Maintenance', de: 'Wartung' } },
      {
        path: 'backup-and-updates',
        title: { en: 'Backups and updates', de: 'Sicherung und Updates' },
      },
    ],
  },
  {
    dir: 'guide',
    title: { en: 'User guide', de: 'Benutzerhandbuch' },
    pages: [
      { path: '', title: { en: 'Overview', de: 'Überblick' } },
      { path: 'signing-in', title: { en: 'Signing in', de: 'Anmelden' } },
      { path: 'library', title: { en: 'Browsing the library', de: 'Die Bibliothek durchsuchen' } },
      { path: 'listening', title: { en: 'Listening', de: 'Hören' } },
      { path: 'speakers', title: { en: 'Playing on speakers', de: 'Auf Lautsprechern abspielen' } },
      {
        path: 'playlists',
        title: { en: 'Playlists, favorites and history', de: 'Playlists, Favoriten und Verlauf' },
      },
      { path: 'covers', title: { en: 'Covers and images', de: 'Cover und Bilder' } },
      { path: 'editing', title: { en: 'Editing tags', de: 'Tags bearbeiten' } },
      { path: 'review', title: { en: 'Review and conflicts', de: 'Prüfliste und Konflikte' } },
      { path: 'downloads', title: { en: 'Downloads', de: 'Downloads' } },
      { path: 'acquiring', title: { en: 'Acquiring music', de: 'Musik aufnehmen' } },
      { path: 'settings', title: { en: 'Settings', de: 'Einstellungen' } },
    ],
  },
  {
    dir: 'source-api',
    title: { en: 'Source service API', de: 'API für Quellen' },
    pages: [
      { path: '', title: { en: 'Overview', de: 'Überblick' } },
      { path: 'reference', title: { en: 'Interface reference', de: 'Referenz der Schnittstelle' } },
    ],
  },
];

const prefix = (lang: Lang) => (lang === 'en' ? '/' : '/de/');

function sidebar(lang: Lang): DefaultTheme.Sidebar {
  return Object.fromEntries(
    parts.map((part) => [
      `${prefix(lang)}${part.dir}/`,
      [
        {
          text: part.title[lang],
          items: part.pages.map((page) => ({
            text: page.title[lang],
            link: `${prefix(lang)}${part.dir}/${page.path}`,
          })),
        },
      ],
    ]),
  );
}

function nav(lang: Lang): DefaultTheme.NavItem[] {
  return parts.map((part) => ({
    text: part.title[lang],
    link: `${prefix(lang)}${part.dir}/`,
    activeMatch: `${prefix(lang)}${part.dir}/`,
  }));
}

const repository = 'https://github.com/anthology-music/anthology';

export default defineConfig({
  title: 'Anthology',
  // The version directory of a published build (e.g. /anthology/v0.1/), set by pages.yml.
  base: process.env.MANUAL_BASE ?? '/',
  cleanUrls: true,
  lastUpdated: false,
  srcExclude: ['README.md', 'walkthrough/**'],
  // The Source service API part includes docs/architecture/source-service-api.md.
  vite: { server: { fs: { allow: ['..'] } } },
  themeConfig: {
    socialLinks: [{ icon: 'github', link: repository }],
    search: { provider: 'local' },
  },
  locales: {
    root: {
      label: 'English',
      lang: 'en',
      description: 'User manual of Anthology, the self-hosted music application',
      themeConfig: {
        nav: nav('en'),
        sidebar: sidebar('en'),
        editLink: { pattern: `${repository}/edit/main/manual/:path`, text: 'Edit this page' },
      },
    },
    de: {
      label: 'Deutsch',
      lang: 'de',
      description: 'Handbuch von Anthology, der selbst betriebenen Musikanwendung',
      themeConfig: {
        nav: nav('de'),
        sidebar: sidebar('de'),
        editLink: {
          pattern: `${repository}/edit/main/manual/:path`,
          text: 'Diese Seite bearbeiten',
        },
        outline: { label: 'Auf dieser Seite' },
        docFooter: { prev: 'Zurück', next: 'Weiter' },
        darkModeSwitchLabel: 'Darstellung',
        sidebarMenuLabel: 'Menü',
        returnToTopLabel: 'Nach oben',
        langMenuLabel: 'Sprache',
      },
    },
  },
});
