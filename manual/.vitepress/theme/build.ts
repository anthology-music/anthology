// Set by the build (pages.yml): the release tag of this manual (empty: the state of main), and the
// site root where versions.json lives.
export const manualVersion: string = import.meta.env.VITE_MANUAL_VERSION ?? '';
export const siteRoot: string = import.meta.env.VITE_MANUAL_SITE_ROOT ?? '/';
