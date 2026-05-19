// Shared app navigation, consumed by the desktop Sidebar and the
// md:hidden MobileNav drawer (issue #39) so the two never drift.
export const NAV_ITEMS = [
  { to: '/', end: true, icon: 'fa-server', label: 'Services' },
  { to: '/chat', end: false, icon: 'fa-comments', label: 'Chat' },
  { to: '/tools', end: false, icon: 'fa-toolbox', label: 'Tools' },
]
