function Header() {
  return (
    <header className="h-16 bg-app/80 border-b border-border-subtle px-4 hidden md:flex items-center justify-end gap-3">
      <a
        href="/"
        className="text-xs text-fg-subtle hover:text-fg-muted flex items-center gap-1.5 transition-colors"
        title="Switch to the legacy dashboard"
      >
        <i className="fa-solid fa-arrow-left text-[10px]"></i>
        Back to v1
      </a>
    </header>
  )
}

export default Header
