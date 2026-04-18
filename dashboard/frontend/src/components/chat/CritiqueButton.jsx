export default function CritiqueButton({ messageId, hasCritique, loading, onClick }) {
  return (
    <button
      onClick={() => onClick(messageId)}
      disabled={loading}
      className={`text-xs px-2 py-1 rounded transition-colors ${
        hasCritique
          ? 'text-yellow-400 hover:text-yellow-300'
          : 'text-gray-500 hover:text-gray-400'
      } ${loading ? 'opacity-50 cursor-wait' : ''}`}
      title={hasCritique ? 'View / refresh critique' : 'Request critique'}
    >
      {loading ? (
        <><i className="fa-solid fa-spinner fa-spin mr-1"></i>Critiquing...</>
      ) : (
        <><i className="fa-solid fa-magnifying-glass mr-1"></i>{hasCritique ? 'Re-critique' : 'Critique'}</>
      )}
    </button>
  )
}
