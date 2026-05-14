function Header() {
  return (
    <header className="h-16 bg-gray-900/80 border-b border-gray-800 px-4 flex items-center justify-end">
      <a
        href="/"
        className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1.5"
        title="Switch to the legacy dashboard"
      >
        <i className="fa-solid fa-arrow-left text-[10px]"></i>
        Back to v1
      </a>
    </header>
  )
}

export default Header
